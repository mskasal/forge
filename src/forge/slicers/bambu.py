"""Bambu Studio CLI slicer backend with G-code temperature safety verification."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from forge.check import OUT_DIR
from forge.config import SlicerConfig
from forge.slicers import UnsafeGcode

MAC_APP = Path("/Applications/BambuStudio.app")
MAC_CLI = MAC_APP / "Contents/MacOS/BambuStudio"
MAC_PROFILES = MAC_APP / "Contents/Resources/profiles/BBL"

PLATES = {
    "textured": "Textured PEI Plate",
    "smooth": "High Temp Plate",
}
DEFAULT_PLATE = "textured"

TEMP_RE = re.compile(r"^(M104|M109|M140|M190)\b[^;\n]*?\bS(\d+(?:\.\d+)?)", re.MULTILINE)


def _find_cli() -> Path | None:
    override = os.environ.get("FORGE_BAMBU_CLI")
    if override and Path(override).is_file():
        return Path(override)
    if MAC_CLI.is_file():
        return MAC_CLI
    for name in ("bambu-studio", "BambuStudio"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def _find_profiles(cli_path: Path | None) -> Path | None:
    override = os.environ.get("FORGE_BAMBU_PROFILES")
    if override and Path(override).is_dir():
        return Path(override)
    if MAC_PROFILES.is_dir():
        return MAC_PROFILES
    if cli_path is not None:
        for candidate in (
            cli_path.parent.parent / "Resources/profiles/BBL",
            cli_path.parent.parent / "share/bambu-studio/profiles/BBL",
            Path.home() / ".config/BambuStudio/system/BBL",
        ):
            if candidate.is_dir():
                return candidate
    return None


def _index(profiles_root: Path, kind: str) -> dict[str, Path]:
    idx: dict[str, Path] = {}
    for p in (profiles_root / kind).rglob("*.json"):
        try:
            idx[json.loads(p.read_text(encoding="utf-8"))["name"]] = p
        except (KeyError, ValueError, OSError):
            continue
    return idx


def flatten(profiles_root: Path, kind: str, name: str, idx: dict[str, Path] | None = None) -> dict:
    """Resolve Bambu Studio profile inheritance (`inherits` + `include`) into a flat dict."""
    idx = idx or _index(profiles_root, kind)
    own = json.loads(idx[name].read_text(encoding="utf-8"))
    conf = flatten(profiles_root, kind, own["inherits"], idx) if own.get("inherits") else {}
    for inc in own.get("include", []):
        conf.update(
            {
                k: v
                for k, v in json.loads(idx[inc].read_text(encoding="utf-8")).items()
                if k not in ("name", "instantiation")
            }
        )
    conf.update(own)
    conf.pop("inherits", None)
    conf.pop("include", None)
    return conf


def limits(machine: dict, filament: dict) -> dict[str, float]:
    """Derive upper temperature safety limits directly from official Bambu profiles."""
    def num(v):
        return max(float(x) for x in (v if isinstance(v, list) else [v]))

    bed_keys = (
        "hot_plate_temp",
        "hot_plate_temp_initial_layer",
        "textured_plate_temp",
        "textured_plate_temp_initial_layer",
        "cool_plate_temp",
        "cool_plate_temp_initial_layer",
        "eng_plate_temp",
        "eng_plate_temp_initial_layer",
    )
    return {
        "nozzle": num(filament["nozzle_temperature_range_high"]),
        "bed": max(num(filament[k]) for k in bed_keys if k in filament),
    }


def check_gcode(gcode: str, lim: dict[str, float]) -> None:
    """Refuse G-code containing any nozzle or bed temperature above profile bounds."""
    for cmd, s in TEMP_RE.findall(gcode):
        t = float(s)
        kind = "nozzle" if cmd in ("M104", "M109") else "bed"
        if t > lim[kind]:
            raise UnsafeGcode(f"{cmd} S{s}: exceeds {kind} limit {lim[kind]:g}°C")


class BambuStudioSlicer:
    name = "bambu"

    def __init__(self, cfg: SlicerConfig | None = None):
        self.cfg = cfg or SlicerConfig(backend="bambu")

    def available(self) -> bool:
        cli = _find_cli()
        return cli is not None and _find_profiles(cli) is not None

    def plates(self) -> dict[str, str]:
        return dict(PLATES)

    def slice_project(self, project_name: str, plate: str | None = None) -> Path:
        use_plate = plate or self.cfg.default_plate or DEFAULT_PLATE
        if use_plate not in PLATES:
            sys.exit(f"Unknown build plate {use_plate!r}; options: {', '.join(PLATES)}")
        folder = OUT_DIR / project_name
        stls = sorted(p for p in folder.glob("*.stl") if p.stem != "assembly")
        if not stls:
            sys.exit(f"No STL files found in {folder}; run `forge run` first.")

        cli = _find_cli()
        profiles = _find_profiles(cli)
        if cli is None or profiles is None:
            sys.exit("Bambu Studio CLI or profiles not found. Install Bambu Studio or set slicer.backend = 'none'.")

        machine = flatten(profiles, "machine", self.cfg.machine)
        process = flatten(profiles, "process", self.cfg.process) | {"curr_bed_type": PLATES[use_plate]}
        filament = flatten(profiles, "filament", self.cfg.filament)
        out = folder / f"{project_name}.gcode.3mf"

        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for kind, conf in (("machine", machine), ("process", process), ("filament", filament)):
                p = Path(tmp) / f"{kind}.json"
                p.write_text(json.dumps(conf), encoding="utf-8")
                paths.append(p)
            cmd = [
                str(cli),
                "--debug", "1",
                "--orient", "0",
                "--arrange", "1",
                "--load-settings", f"{paths[0]};{paths[1]}",
                "--load-filaments", str(paths[2]),
                "--slice", "0",
                "--export-3mf", str(out),
                *map(str, stls),
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=tmp)

        if r.returncode != 0 or not out.exists():
            sys.exit(f"Slicing failed (exit {r.returncode}):\n{r.stdout[-2000:]}{r.stderr[-2000:]}")

        with zipfile.ZipFile(out) as z:
            gcodes = [n for n in z.namelist() if re.fullmatch(r"Metadata/plate_\d+\.gcode", n)]
            try:
                if not gcodes:
                    raise UnsafeGcode("No G-code found inside 3MF")
                lim = limits(machine, filament)
                for n in gcodes:
                    check_gcode(z.read(n).decode(errors="replace"), lim)
            except UnsafeGcode:
                out.unlink()
                raise
        return out
