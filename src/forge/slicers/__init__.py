"""Minimal slicer adapter boundary.

Unconfigured (`backend = "none"`) simply returns None — no dummy adapter class needed.
Add new slicers (e.g. orcaslicer.py, prusaslicer.py) by implementing the Slicer protocol.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from forge.config import SlicerConfig, load_config


class UnsafeGcode(ValueError):
    """Sliced G-code exceeded safety bounds."""


class Slicer(Protocol):
    name: str

    def available(self) -> bool: ...
    def plates(self) -> dict[str, str]: ...
    def slice_project(self, project_name: str, plate: str | None = None) -> Path: ...


def get_slicer(cfg: SlicerConfig | None = None) -> Slicer | None:
    """Return active Slicer instance, or None when backend == 'none'."""
    conf = cfg or load_config().slicer
    backend = (conf.backend or "none").lower()
    if backend in ("none", "", "off"):
        return None
    if backend in ("bambu", "bambu_studio"):
        from forge.slicers.bambu import BambuStudioSlicer

        return BambuStudioSlicer(conf)
    raise ValueError(f"Unknown slicer backend {backend!r}; supported: none, bambu")
