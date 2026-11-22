"""Bambu Lab LAN printer backend (FTPS 990 + MQTT TLS 8883) with strict safety guard().

Security invariants (non-negotiable):
  1. Every outbound MQTT message passes through a single `send()` -> `guard()` bottleneck.
  2. Only two commands are permitted: `pushing.pushall` (read-only status) and
     `print.project_file` (approved sliced print job). Temperature, fan, axis motion,
     raw G-code, calibration, settings, pause/stop, and firmware commands are refused.
  3. Automatic printer safety checks (`bed_leveling`, `flow_cali`, `vibration_cali`,
     `layer_inspect`) cannot be disabled.
  4. `check_3mf()` verifies target printer model, nozzle diameter, and hard upper
     nozzle/bed temperature caps before any file is uploaded.
  5. Printer self-signed TLS certificates are pinned on first sight per printer ID.
"""

from __future__ import annotations

import ftplib
import hashlib
import json
import os
import re
import socket
import ssl
import threading
import time
import zipfile
from pathlib import Path

import paho.mqtt.client as mqtt

from printers import IDLE_STATES, PrinterError, Refused

MQTT_PORT = 8883
FTP_PORT = 990

ALLOWED = {
    ("pushing", "pushall"),
    ("print", "project_file"),
}

PROJECT_FILE_KEYS = {
    "sequence_id",
    "command",
    "param",
    "url",
    "md5",
    "subtask_name",
    "file",
    "project_id",
    "profile_id",
    "task_id",
    "subtask_id",
    "bed_type",
    "timelapse",
    "use_ams",
    "ams_mapping",
    "bed_leveling",
    "flow_cali",
    "vibration_cali",
    "layer_inspect",
}
MUST_STAY_ON = ("bed_leveling", "flow_cali", "vibration_cali", "layer_inspect")
SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,64}\.3mf$")
PLATE_RE = re.compile(r"Metadata/plate_\d{1,2}\.gcode")
TEMP_RE = re.compile(r"^(M104|M109|M140|M190)\b[^;\n]*?\bS(\d+(?:\.\d+)?)", re.MULTILINE)


def guard(payload: dict) -> None:
    """Raise Refused unless `payload` strictly matches the two allowed commands."""
    if not isinstance(payload, dict) or len(payload) != 1:
        raise Refused("MQTT payload must contain exactly one top-level section")
    ((section, body),) = payload.items()
    if not isinstance(body, dict) or (section, body.get("command")) not in ALLOWED:
        cmd = body.get("command") if isinstance(body, dict) else body
        raise Refused(f"Disallowed printer command: {section}.{cmd}")
    if body["command"] == "pushall":
        if set(body) - {"sequence_id", "command"}:
            raise Refused("pushall accepts no extra fields")
        return
    extra = set(body) - PROJECT_FILE_KEYS
    if extra:
        raise Refused(f"Disallowed fields in project_file: {', '.join(sorted(extra))}")
    for k in MUST_STAY_ON:
        if body.get(k) is not True:
            raise Refused(f"{k} must stay enabled (printer safety check)")
    url, file_field, param = body.get("url", ""), body.get("file", ""), body.get("param", "")
    name = url[len("file:///sdcard/"):] if url.startswith("file:///sdcard/") else ""
    if not SAFE_NAME.match(name):
        raise Refused("url must be file:///sdcard/<safe-name>.3mf")
    if file_field and file_field != f"/{name}":
        raise Refused("file field must match url")
    if not isinstance(param, str) or not PLATE_RE.fullmatch(param):
        raise Refused("param must be Metadata/plate_N.gcode")


def send(client, serial: str, payload: dict) -> None:
    """Single outbound path to the printer: guard first, publish second."""
    guard(payload)
    client.publish(f"device/{serial}/request", json.dumps(payload))


def check_gcode(gcode: str, lim: dict[str, float]) -> None:
    for cmd, s in TEMP_RE.findall(gcode):
        kind = "nozzle" if cmd in ("M104", "M109") else "bed"
        if float(s) > lim[kind]:
            raise Refused(f"{cmd} S{s}: exceeds {kind} temperature cap {lim[kind]:g}°C")


def inspect_3mf(path: Path) -> dict:
    """Read metadata from a sliced .gcode.3mf without enforcing a specific printer target."""
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        raise Refused("Not a valid 3MF archive") from e
    with z:
        plates = sorted(n for n in z.namelist() if PLATE_RE.fullmatch(n))
        if len(plates) != 1:
            raise Refused(f"Expected exactly 1 sliced plate (found {len(plates)})")
        try:
            conf = json.loads(z.read("Metadata/project_settings.config"))
        except (KeyError, ValueError) as e:
            raise Refused("Missing or corrupt Metadata/project_settings.config") from e
        nozzle_raw = conf.get("nozzle_diameter")
        nozzle = str(nozzle_raw[0] if isinstance(nozzle_raw, list) and nozzle_raw else (nozzle_raw or ""))
        info: dict = {
            "param": plates[0],
            "printer_model": str(conf.get("printer_model") or ""),
            "nozzle": nozzle,
            "bed_type": str(conf.get("curr_bed_type") or ""),
            "gcode": z.read(plates[0]).decode(errors="replace"),
        }
        try:
            slice_info = z.read("Metadata/slice_info.config").decode(errors="replace")
            for key in ("prediction", "weight"):
                m = re.search(rf'key="{key}" value="([\d.]+)"', slice_info)
                if m:
                    info[key] = float(m.group(1))
        except KeyError:
            pass
    return info


def check_3mf(
    path: Path,
    *,
    expected_model: str = "Bambu Lab A1",
    expected_nozzle: str = "0.4",
    temp_max: dict[str, float] | None = None,
) -> dict:
    """Validate a sliced .gcode.3mf against target printer model, nozzle, and temperature caps."""
    lim = temp_max or {"nozzle": 240.0, "bed": 65.0}
    info = inspect_3mf(path)
    if info["printer_model"] != expected_model:
        raise Refused(
            f"Sliced for {info['printer_model']!r}, but target printer is {expected_model!r}"
        )
    if info["nozzle"] != expected_nozzle:
        raise Refused(
            f"Sliced for nozzle {info['nozzle']!r}, but target printer has {expected_nozzle!r}"
        )
    check_gcode(info.pop("gcode"), lim)
    return info


def _tls_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # verified via SHA-256 certificate pinning
    return ctx


class _ImplicitFTPS(ftplib.FTP_TLS):
    """Bambu LAN uses implicit TLS on port 990 with TLS session reuse on the data channel."""

    def __init__(self):
        super().__init__(context=_tls_context(), timeout=30)
        self._sock = None

    @property
    def sock(self):
        return self._sock

    @sock.setter
    def sock(self, value):
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value)
        self._sock = value

    def ntransfercmd(self, cmd, rest=None):
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(conn, session=self.sock.session)
        return conn, size


class BambuLanPrinter:
    backend = "bambu_lan"

    def __init__(
        self,
        *,
        id: str,
        name: str,
        host: str,
        serial: str,
        access_code: str,
        model: str = "Bambu Lab A1",
        nozzle: str = "0.4",
        max_nozzle_temp: float = 240.0,
        max_bed_temp: float = 65.0,
        data_dir: Path,
        use_ams: bool = False,
    ):
        self.id = id
        self.name = name
        self.host = host
        self.serial = serial
        self.access_code = access_code
        self.model = model
        self.nozzle = nozzle
        self.temp_max = {"nozzle": max_nozzle_temp, "bed": max_bed_temp}
        self.data_dir = data_dir
        self.use_ams = use_ams
        self.lock = threading.Lock()

    def _require_creds(self) -> None:
        missing = [
            k for k, v in (("host", self.host), ("serial", self.serial), ("access_code", self.access_code))
            if not v
        ]
        if missing:
            raise PrinterError(f"Printer {self.id!r} missing config: {', '.join(missing)}")

    def _pin_path(self, port: int) -> Path:
        d = self.data_dir / "certs"
        d.mkdir(parents=True, exist_ok=True)
        suffix = "mqtt" if port == MQTT_PORT else "ftps"
        return d / f"{self.id}-{suffix}.sha256"

    def check_pin(self, port: int, der: bytes) -> None:
        fp = hashlib.sha256(der).hexdigest()
        pin = self._pin_path(port)
        if not pin.exists():
            pin.write_text(fp + "\n", encoding="utf-8")
        elif pin.read_text(encoding="utf-8").strip() != fp:
            raise PrinterError(
                f"Certificate changed for printer {self.id!r} (port {port}); connection refused. "
                f"If expected after a firmware update, delete {pin} and retry."
            )

    def _pin_mqtt(self) -> None:
        try:
            with socket.create_connection((self.host, MQTT_PORT), timeout=8) as sock:
                with _tls_context().wrap_socket(sock) as tls:
                    self.check_pin(MQTT_PORT, tls.getpeercert(binary_form=True))
        except OSError as e:
            raise PrinterError(f"Could not reach printer {self.id!r} ({self.host}): {e}") from e

    def _mqtt_session(self, on_ready, timeout: float) -> dict:
        self._require_creds()
        self._pin_mqtt()
        report: dict = {}
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"forge-{self.id}-{os.getpid()}-{time.monotonic_ns()}",
        )
        client.username_pw_set("bblp", self.access_code)
        client.tls_set_context(_tls_context())

        def on_connect(c, _u, _f, reason, _p):
            if reason.is_failure:
                report["error"] = f"connection refused: {reason}"
                return
            c.subscribe(f"device/{self.serial}/report")
            on_ready(c, self.serial)

        def on_message(_c, _u, msg):
            data = json.loads(msg.payload)
            if "print" in data and "gcode_state" in data["print"]:
                report.update(data["print"])

        client.on_connect = on_connect
        client.on_message = on_message
        try:
            client.connect(self.host, MQTT_PORT, keepalive=30)
        except OSError as e:
            raise PrinterError(f"Could not reach printer {self.id!r} ({self.host}): {e}") from e
        client.loop_start()
        end = time.monotonic() + timeout
        while time.monotonic() < end and not report:
            time.sleep(0.15)
        time.sleep(0.3)
        client.loop_stop()
        client.disconnect()
        if not report:
            report["error"] = "timeout waiting for printer status"
        return report

    def read_status(self, timeout: float = 5.0) -> dict:
        return self._mqtt_session(
            lambda c, serial: send(c, serial, {"pushing": {"sequence_id": "0", "command": "pushall"}}),
            timeout=timeout,
        )

    def check_file(self, path: Path) -> dict:
        return check_3mf(
            path,
            expected_model=self.model,
            expected_nozzle=self.nozzle,
            temp_max=self.temp_max,
        )

    def _upload_ftps(self, path: Path, remote: str) -> None:
        if not SAFE_NAME.match(remote):
            raise Refused(f"Unsafe remote filename: {remote!r}")
        ftp = _ImplicitFTPS()
        try:
            ftp.connect(self.host, FTP_PORT)
            self.check_pin(FTP_PORT, ftp.sock.getpeercert(binary_form=True))
            ftp.login("bblp", self.access_code)
            ftp.prot_p()
            with open(path, "rb") as f:
                ftp.voidcmd("TYPE I")
                with ftp.transfercmd(f"STOR {remote}") as conn:
                    while chunk := f.read(65536):
                        conn.sendall(chunk)
                ftp.voidresp()
        except (OSError, ftplib.Error) as e:
            raise PrinterError(f"FTPS upload failed for {self.id!r}: {e}") from e
        finally:
            try:
                ftp.quit()
            except Exception:
                ftp.close()

    def start_print(self, path: Path, remote_name: str, title: str) -> dict:
        info = self.check_file(path)
        status = self.read_status(timeout=8.0)
        if "error" in status:
            raise PrinterError(status["error"])
        if status.get("gcode_state") not in IDLE_STATES:
            raise PrinterError(f"Printer {self.id!r} is busy ({status.get('gcode_state')})")
        if status.get("sdcard") is False:
            raise PrinterError(f"Printer {self.id!r} has no SD card")
        payload = {
            "print": {
                "sequence_id": "0",
                "command": "project_file",
                "param": info["param"],
                "url": f"file:///sdcard/{remote_name}",
                "file": f"/{remote_name}",
                "subtask_name": title,
                "md5": hashlib.md5(path.read_bytes()).hexdigest(),
                "project_id": "0",
                "profile_id": "0",
                "task_id": "0",
                "subtask_id": "0",
                "bed_type": "auto",
                "timelapse": False,
                "use_ams": self.use_ams,
                "ams_mapping": [0],
                **{k: True for k in MUST_STAY_ON},
            }
        }
        guard(payload)
        self._upload_ftps(path, remote_name)
        after = self._mqtt_session(lambda c, serial: send(c, serial, payload), timeout=15.0)
        if "error" in after:
            raise PrinterError(after["error"])
        return info
