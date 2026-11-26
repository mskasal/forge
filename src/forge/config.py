"""Unified workstation configuration (~/.config/forge/config.toml + optional ./forge.toml).

Precedence (highest to lowest):
  1. Environment variables (FORGE_HUB_URL, FORGE_HUB_TOKEN, FORGE_SLICER, ...)
  2. Project-local ./forge.toml (printer/slicer overrides only — secrets never live in repo)
  3. User config ~/.config/forge/config.toml (chmod 600)
  4. Built-in defaults (local hub http://127.0.0.1:8590, slicer="none", 256 mm build volume)
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from forge._paths import CONFIG_FILE


@dataclass(frozen=True)
class HubConfig:
    url: str = "http://127.0.0.1:8590"
    token: str = ""


@dataclass(frozen=True)
class PrinterProfile:
    build_volume: tuple[float, float, float] = (256.0, 256.0, 256.0)
    nozzle_mm: float = 0.4
    layer_mm: float = 0.2


@dataclass(frozen=True)
class SlicerConfig:
    backend: str = "none"  # "none" | "bambu"
    machine: str = "Bambu Lab A1 0.4 nozzle"
    process: str = "0.20mm Standard @BBL A1"
    filament: str = "Bambu PLA Matte @BBL A1"
    default_plate: str = "textured"


@dataclass(frozen=True)
class ForgeConfig:
    hub: HubConfig = field(default_factory=HubConfig)
    printer: PrinterProfile = field(default_factory=PrinterProfile)
    slicer: SlicerConfig = field(default_factory=SlicerConfig)


def _read_toml(path: Path) -> dict:
    try:
        if not path.is_file():
            return {}
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def load_config(
    user_path: Path | None = None,
    project_path: Path | None = None,
) -> ForgeConfig:
    """Load effective ForgeConfig from user TOML, optional project TOML, and env vars."""
    u_file = user_path if user_path is not None else Path(os.environ.get("FORGE_CONFIG") or CONFIG_FILE)
    p_file = project_path if project_path is not None else (Path.cwd() / "forge.toml")

    user_data = _read_toml(u_file)
    proj_data = _read_toml(p_file)

    u_hub = user_data.get("hub") or {}
    u_prn = {**(user_data.get("printer") or {}), **(proj_data.get("printer") or {})}
    u_slc = {**(user_data.get("slicer") or {}), **(proj_data.get("slicer") or {})}

    hub_url = os.environ.get("FORGE_HUB_URL") or u_hub.get("url") or "http://127.0.0.1:8590"
    hub_token = os.environ.get("FORGE_HUB_TOKEN") or u_hub.get("token") or ""

    bv_raw = u_prn.get("build_volume")
    if isinstance(bv_raw, (list, tuple)) and len(bv_raw) == 3:
        bv = (float(bv_raw[0]), float(bv_raw[1]), float(bv_raw[2]))
    else:
        bv = (256.0, 256.0, 256.0)

    printer = PrinterProfile(
        build_volume=bv,
        nozzle_mm=float(u_prn.get("nozzle_mm", 0.4)),
        layer_mm=float(u_prn.get("layer_mm", 0.2)),
    )

    slicer = SlicerConfig(
        backend=os.environ.get("FORGE_SLICER") or str(u_slc.get("backend", "none")).lower(),
        machine=str(u_slc.get("machine", "Bambu Lab A1 0.4 nozzle")),
        process=str(u_slc.get("process", "0.20mm Standard @BBL A1")),
        filament=str(u_slc.get("filament", "Bambu PLA Matte @BBL A1")),
        default_plate=str(u_slc.get("default_plate", "textured")),
    )

    return ForgeConfig(
        hub=HubConfig(url=str(hub_url).rstrip("/"), token=str(hub_token)),
        printer=printer,
        slicer=slicer,
    )


def write_hub_config(url: str, token: str, path: Path | None = None) -> Path:
    """Write or update [hub] in ~/.config/forge/config.toml with chmod 600."""
    target = path if path is not None else Path(os.environ.get("FORGE_CONFIG") or CONFIG_FILE)
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_toml(target)
    existing.setdefault("hub", {})
    existing["hub"]["url"] = url.rstrip("/")
    existing["hub"]["token"] = token

    lines: list[str] = []
    for section, values in existing.items():
        if not isinstance(values, dict):
            continue
        lines.append(f"[{section}]")
        for k, v in values.items():
            if isinstance(v, str):
                escaped = v.replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'{k} = "{escaped}"')
            elif isinstance(v, bool):
                lines.append(f"{k} = {'true' if v else 'false'}")
            elif isinstance(v, (list, tuple)):
                items = ", ".join(str(x) for x in v)
                lines.append(f"{k} = [{items}]")
            else:
                lines.append(f"{k} = {v}")
        lines.append("")

    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines).rstrip() + "\n")
    finally:
        os.chmod(target, 0o600)
    return target
