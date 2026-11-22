"""Tests for Bambu LAN guard(), check_3mf(), multi-printer concurrent polling, and guarded print dispatch."""

from __future__ import annotations

import importlib
import io
import json
import sys
import threading
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HUB_DIR = Path(__file__).resolve().parents[1]
if str(HUB_DIR) not in sys.path:
    sys.path.insert(0, str(HUB_DIR))

from printers import PrinterError, PrinterRegistry, Refused
from printers.bambu_lan import MUST_STAY_ON, check_3mf, guard, send


def _make_3mf(
    *,
    model: str = "Bambu Lab A1",
    nozzle: str = "0.4",
    bed_type: str = "Textured PEI Plate",
    gcode: str = "M104 S220\nM140 S60\nG28\n",
    prediction: int = 1800,
    weight: float = 25.5,
) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "Metadata/project_settings.config",
            json.dumps({"printer_model": model, "nozzle_diameter": [nozzle], "curr_bed_type": bed_type}),
        )
        z.writestr(
            "Metadata/slice_info.config",
            f'<config><header><metadata key="prediction" value="{prediction}"/>'
            f'<metadata key="weight" value="{weight}"/></header></config>',
        )
        z.writestr("Metadata/plate_1.gcode", gcode)
    return buf.getvalue()


class _FakePrinter:
    backend = "bambu_lan"

    def __init__(
        self,
        pid: str,
        name: str,
        *,
        model: str = "Bambu Lab A1",
        nozzle: str = "0.4",
        state: str = "IDLE",
        delay: float = 0.0,
        offline: bool = False,
    ):
        self.id = pid
        self.name = name
        self.model = model
        self.nozzle = nozzle
        self.state = state
        self.delay = delay
        self.offline = offline
        self.lock = threading.Lock()
        self.started: list[tuple[str, str]] = []

    def read_status(self, timeout: float = 5.0) -> dict:
        if self.delay:
            time.sleep(self.delay)
        if self.offline:
            raise PrinterError("connection timed out")
        return {"gcode_state": self.state, "nozzle_temper": 25.0, "bed_temper": 24.0}

    def check_file(self, path: Path) -> dict:
        return check_3mf(path, expected_model=self.model, expected_nozzle=self.nozzle)

    def start_print(self, path: Path, remote_name: str, title: str) -> dict:
        info = self.check_file(path)
        self.started.append((remote_name, title))
        return info


def test_bambu_guard_allowlist_and_safety_flags():
    # Allowed: pushall
    guard({"pushing": {"sequence_id": "0", "command": "pushall"}})
    with pytest.raises(Refused):
        guard({"pushing": {"sequence_id": "0", "command": "pushall", "extra": 1}})

    # Allowed: project_file with all safety flags enabled
    valid_pf = {
        "print": {
            "sequence_id": "0",
            "command": "project_file",
            "param": "Metadata/plate_1.gcode",
            "url": "file:///sdcard/forge_demo_v1.gcode.3mf",
            "file": "/forge_demo_v1.gcode.3mf",
            **{k: True for k in MUST_STAY_ON},
        }
    }
    guard(valid_pf)

    # Disabling ANY safety flag must be refused
    for k in MUST_STAY_ON:
        bad = {"print": {**valid_pf["print"], k: False}}
        with pytest.raises(Refused, match=k):
            guard(bad)

    # Raw gcode, pause, stop, calibration, extra fields must be refused
    for bad in (
        {"print": {"command": "gcode_line", "param": "M104 S300"}},
        {"print": {"command": "stop"}},
        {"print": {"command": "pause"}},
        {"print": {**valid_pf["print"], "url": "file:///sdcard/../evil.3mf"}},
        {"print": {**valid_pf["print"], "param": "Metadata/plate_1.gcode; rm -rf /"}},
    ):
        with pytest.raises(Refused):
            guard(bad)

    # send() enforces guard() before touching mqtt client
    published = []

    class FakeClient:
        def publish(self, topic, payload):
            published.append((topic, payload))

    send(FakeClient(), "SER123", {"pushing": {"sequence_id": "0", "command": "pushall"}})
    assert len(published) == 1
    with pytest.raises(Refused):
        send(FakeClient(), "SER123", {"print": {"command": "gcode_line", "param": "G28"}})
    assert len(published) == 1


def test_check_3mf_enforces_model_nozzle_and_temp_caps(tmp_path):
    good = tmp_path / "a1.gcode.3mf"
    good.write_bytes(_make_3mf(model="Bambu Lab A1", nozzle="0.4"))
    info = check_3mf(good, expected_model="Bambu Lab A1", expected_nozzle="0.4")
    assert info["printer_model"] == "Bambu Lab A1"

    # Model mismatch refused
    with pytest.raises(Refused, match="target printer"):
        check_3mf(good, expected_model="Bambu Lab A1 mini", expected_nozzle="0.4")

    # Nozzle mismatch refused
    with pytest.raises(Refused, match="nozzle"):
        check_3mf(good, expected_model="Bambu Lab A1", expected_nozzle="0.6")

    # Excessive temperature refused
    hot = tmp_path / "hot.gcode.3mf"
    hot.write_bytes(_make_3mf(gcode="M104 S280\n"))
    with pytest.raises(Refused, match="nozzle temperature cap"):
        check_3mf(hot, expected_model="Bambu Lab A1", expected_nozzle="0.4")


def test_multi_printer_registry_polls_in_parallel_and_isolates_offline():
    p1 = _FakePrinter("a1", "Studio A1", delay=0.15)
    p2 = _FakePrinter("mini", "Desk Mini", model="Bambu Lab A1 mini", delay=0.15, offline=True)
    reg = PrinterRegistry([p1, p2])

    t0 = time.monotonic()
    statuses = reg.status_all(ttl=5.0)
    elapsed = time.monotonic() - t0
    assert elapsed < 0.28, f"Expected parallel polling, took {elapsed:.2f}s"
    assert len(statuses) == 2
    assert statuses[0]["id"] == "a1" and statuses[0]["gcode_state"] == "IDLE"
    assert statuses[1]["id"] == "mini" and "error" in statuses[1]


def _setup_app(tmp_path, monkeypatch, printers):
    tmp_path.mkdir(parents=True, exist_ok=True)
    tokens = tmp_path / "tokens"
    tokens.write_text("owner:tok-owner\nappletv:tok-tv\nagent:tok-agent\nweb:tok-web\n", encoding="utf-8")
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("FORGE_TOKENS", str(tokens))
    monkeypatch.delenv("FORGE_HUB_CONFIG", raising=False)
    monkeypatch.delenv("FORGE_REMOTE_PEER", raising=False)

    import app as hub_app

    hub_app = importlib.reload(hub_app)
    hub_app.REGISTRY = PrinterRegistry(printers)
    client = TestClient(hub_app.app, client=("127.0.0.1", 50000))
    return hub_app, client


def test_zero_printer_mode_and_multi_printer_print_dispatch(tmp_path, monkeypatch):
    # 0-printer mode
    _, client0 = _setup_app(tmp_path / "zero", monkeypatch, [])
    hdr_owner = {"Authorization": "Bearer tok-owner"}
    hdr_agent = {"Authorization": "Bearer tok-agent"}
    assert client0.get("/printers", headers=hdr_owner).json() == []
    assert client0.post(
        "/projects/p/versions",
        headers=hdr_owner,
        files=[("files", ("p.gcode.3mf", _make_3mf(), "application/octet-stream"))],
    ).status_code == 201
    assert client0.post("/projects/p/versions/v1/print", headers=hdr_owner).status_code == 409

    # 2-printer mode: A1 (0.4) + A1 mini (0.6)
    p_a1 = _FakePrinter("a1", "Studio A1", model="Bambu Lab A1", nozzle="0.4")
    p_mini = _FakePrinter("mini", "Desk Mini", model="Bambu Lab A1 mini", nozzle="0.6")
    _, client = _setup_app(tmp_path / "multi", monkeypatch, [p_a1, p_mini])

    assert client.post(
        "/projects/box/versions",
        headers=hdr_owner,
        files=[("files", ("box.gcode.3mf", _make_3mf(model="Bambu Lab A1", nozzle="0.4"), "application/octet-stream"))],
    ).status_code == 201

    # Missing printer_id with 2 printers -> 400
    assert client.post("/projects/box/versions/v1/print", headers=hdr_owner, json={}).status_code == 400

    # Wrong printer (A1 file sent to A1 mini) -> 422 BEFORE consuming code
    code_resp = client.get("/projects/box/versions/v1/print?printer_id=a1", headers=hdr_owner)
    assert code_resp.status_code == 200
    code = code_resp.json()["code"]
    assert client.post(
        "/projects/box/versions/v1/print",
        headers=hdr_agent,
        json={"code": code, "printer_id": "mini"},
    ).status_code == 422

    # Busy printer -> 409 BEFORE consuming code
    p_a1.state = "RUNNING"
    assert client.post(
        "/projects/box/versions/v1/print",
        headers=hdr_agent,
        json={"code": code, "printer_id": "a1"},
    ).status_code == 409

    # Idle printer + valid code -> 200 and rotates code
    p_a1.state = "IDLE"
    r_ok = client.post(
        "/projects/box/versions/v1/print",
        headers=hdr_agent,
        json={"code": code, "printer_id": "a1"},
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["started"] is True
    assert r_ok.json()["printer_id"] == "a1"
    assert len(p_a1.started) == 1

    # Reusing the same code must fail with 403
    assert client.post(
        "/projects/box/versions/v1/print",
        headers=hdr_agent,
        json={"code": code, "printer_id": "a1"},
    ).status_code == 403

    # Unknown printer_id in GET /print -> 404
    assert client.get("/projects/box/versions/v1/print?printer_id=nope", headers=hdr_owner).status_code == 404
