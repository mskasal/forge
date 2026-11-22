"""Minimal multi-printer registry and protocol for Forge Hub.

Zero printers configured = empty registry (preview-only mode, no dummy backend needed).
All printer backends MUST enforce strict command allowlists and per-printer model/nozzle checks.
"""

from __future__ import annotations

import os
import threading
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Protocol

IDLE_STATES = {"IDLE", "FINISH", "FAILED"}


class Refused(PermissionError):
    """A command or sliced file was refused by printer safety rules."""


class PrinterError(RuntimeError):
    """Printer is unreachable, busy, or misconfigured."""


class Printer(Protocol):
    id: str
    name: str
    backend: str
    model: str
    nozzle: str
    lock: threading.Lock

    def read_status(self, timeout: float = 5.0) -> dict: ...
    def check_file(self, path: Path) -> dict: ...
    def start_print(self, path: Path, remote_name: str, title: str) -> dict: ...


class PrinterRegistry:
    """Manages 0..N configured printers with independent 5s status caches and parallel polling."""

    def __init__(self, printers: list[Printer] | None = None):
        self._printers: dict[str, Printer] = {p.id: p for p in (printers or [])}
        self._order: list[str] = [p.id for p in (printers or [])]
        self._cache: dict[str, tuple[float, dict]] = {}
        self._cache_lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._order)

    def ids(self) -> list[str]:
        return list(self._order)

    def get(self, printer_id: str | None = None) -> Printer | None:
        if not self._order:
            return None
        if printer_id is None:
            return self._printers[self._order[0]]
        return self._printers.get(printer_id)

    def invalidate(self, printer_id: str | None = None) -> None:
        with self._cache_lock:
            if printer_id is None:
                self._cache.clear()
            else:
                self._cache.pop(printer_id, None)

    def status_one(self, printer: Printer, *, ttl: float = 5.0, timeout: float = 5.0) -> dict:
        now = time.monotonic()
        with self._cache_lock:
            cached = self._cache.get(printer.id)
            if cached and now - cached[0] < ttl:
                return dict(cached[1])
        try:
            raw = printer.read_status(timeout=timeout)
        except PrinterError as e:
            raw = {"error": str(e)}
        keys = (
            "gcode_state",
            "mc_percent",
            "layer_num",
            "total_layer_num",
            "mc_remaining_time",
            "nozzle_temper",
            "nozzle_target_temper",
            "bed_temper",
            "bed_target_temper",
            "subtask_name",
            "wifi_signal",
            "spd_lvl",
            "print_error",
            "error",
        )
        data = {
            "id": printer.id,
            "name": printer.name,
            "backend": printer.backend,
            "model": printer.model,
            "nozzle": printer.nozzle,
            **{k: raw.get(k) for k in keys if k in raw},
        }
        with self._cache_lock:
            self._cache[printer.id] = (time.monotonic(), data)
        return dict(data)

    def status_all(self, *, ttl: float = 5.0, timeout: float = 5.0) -> list[dict]:
        """Poll all configured printers concurrently so one offline printer never stalls others."""
        if not self._order:
            return []
        printers = [self._printers[pid] for pid in self._order]
        if len(printers) == 1:
            return [self.status_one(printers[0], ttl=ttl, timeout=timeout)]
        with ThreadPoolExecutor(max_workers=min(len(printers), 8)) as pool:
            return list(pool.map(lambda p: self.status_one(p, ttl=ttl, timeout=timeout), printers))


def load_hub_config(path: Path | None = None) -> dict:
    cfg_path = path or (Path(os.environ["FORGE_HUB_CONFIG"]) if os.environ.get("FORGE_HUB_CONFIG") else None)
    if cfg_path is None or not cfg_path.is_file():
        return {}
    return tomllib.loads(cfg_path.read_text(encoding="utf-8"))


def load_registry(data_dir: Path, hub_conf: dict | None = None) -> PrinterRegistry:
    """Build a PrinterRegistry from [[printers]] entries in hub.toml."""
    conf = hub_conf or {}
    entries = conf.get("printers") or []
    printers: list[Printer] = []
    seen: set[str] = set()
    for raw in entries:
        pid = str(raw.get("id") or "").strip()
        if not pid or pid in seen:
            raise ValueError(f"Invalid or duplicate printer id: {pid!r}")
        seen.add(pid)
        backend = str(raw.get("backend", "bambu_lan")).lower()
        if backend == "bambu_lan":
            from printers.bambu_lan import BambuLanPrinter

            access_code = str(raw.get("access_code") or "")
            if not access_code and raw.get("access_code_env"):
                access_code = os.environ.get(str(raw["access_code_env"]), "")
            if not access_code and raw.get("access_code_file"):
                p = Path(str(raw["access_code_file"]))
                if p.is_file():
                    access_code = p.read_text(encoding="utf-8").strip()
            printers.append(
                BambuLanPrinter(
                    id=pid,
                    name=str(raw.get("name") or pid),
                    host=str(raw.get("host") or ""),
                    serial=str(raw.get("serial") or ""),
                    access_code=access_code,
                    model=str(raw.get("model") or "Bambu Lab A1"),
                    nozzle=str(raw.get("nozzle") or "0.4"),
                    max_nozzle_temp=float(raw.get("max_nozzle_temp", 240.0)),
                    max_bed_temp=float(raw.get("max_bed_temp", 65.0)),
                    data_dir=data_dir,
                    use_ams=bool(raw.get("use_ams", False)),
                )
            )
        else:
            raise ValueError(f"Unknown printer backend {backend!r} for printer {pid!r}")
    return PrinterRegistry(printers)
