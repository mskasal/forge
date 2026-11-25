"""OrcaSlicer CLI slicer backend (macOS & Linux) with G-code temperature safety verification."""

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
from forge.slicers.bambu import DEFAULT_PLATE, PLATES, check_gcode, flatten, limits

MAC_APP = Path("/Applications/OrcaSlicer.app")
MAC_CLI = MAC_APP / "Contents/MacOS/OrcaSlicer"
MAC_PROFILES = MAC_APP / "Contents/Resources/profiles/BBL"


def _find_cli() -> Path | None:
    override = os.environ.get("FORGE_ORCA_CLI")
    if override and Path(override).is_file():
        return Path(override)
    if MAC_CLI.is_file():
        return MAC_CLI
    for name in ("orca-slicer", "OrcaSlicer", "orcaslicer"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def _find_profiles(cli_path: Path | None) -> Path | None:
    override = os.environ.get("FORGE_ORCA_PROFILES")
    if override and Path(override).is_dir():
        return Path(override)
    if MAC_PROFILES.is_dir():
        return MAC_PROFILES
    candidates = [
        Path.home() / ".config/OrcaSlicer/system/BBL",
        Path.home() / ".var/app/io.github.softfever.OrcaSlicer/config/OrcaSlicer/system/BBL",
        Path("/usr/share/OrcaSlicer/profiles/BBL"),
        Path("/usr/share/orca-slicer/profiles/BBL"),
    ]
    if cli_path is not None:
        candidates.extend(
            [
                cli_path.parent.parent / "Resources/profiles/BBL",
                cli_path.parent.parent / "share/OrcaSlicer/profiles/BBL",
                cli_path.parent.parent / "share/orca-slicer/profiles/BBL",
            ]
        )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


class OrcaSlicer:
    name = "orca"

    def __init__(self, cfg: SlicerConfig | None = None):
        self.cfg = cfg or SlicerConfig(backend="orca")

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
            sys.exit(
                "OrcaSlicer CLI or profiles not found. Install OrcaSlicer, set FORGE_ORCA_CLI / "
                "FORGE_ORCA_PROFILES, or set slicer.backend = 'none'."
            )

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
