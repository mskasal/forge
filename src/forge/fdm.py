"""FDM printability rules as numbers (default: 0.4 mm nozzle, 0.2 mm layers, 256 mm build volume).

Single source of truth for code: design-language tokens and parameter checks validate
against these bounds. `skills/forge/references/fdm-and-tolerances.md` mirrors these
numbers in prose; `tests/test_styles.py` verifies exact parity.
"""

from __future__ import annotations

from dataclasses import dataclass

from forge.config import load_config


@dataclass(frozen=True)
class FDMProfile:
    nozzle: float = 0.4
    layer: float = 0.2
    build: tuple[float, float, float] = (256.0, 256.0, 256.0)
    wall_min: float = 1.2  # 3 perimeters
    wall_load: float = 2.0  # load-bearing / screw walls
    floor_min: float = 1.0  # 5 layers, floor and roof
    feature_min: float = 0.8  # 2 * nozzle
    text_stroke_min: float = 1.0  # engraved/embossed line width
    text_depth_min: float = 0.6
    overhang_max_deg: float = 45.0  # from vertical, support-free
    bridge_max: float = 10.0
    bed_chamfer_min: float = 0.4  # chamfer, not fillet, on bed-contact edges
    bed_chamfer_max: float = 0.6


DEFAULT = FDMProfile()

# Top-level default constants for concise imports (`from forge import fdm; fdm.WALL_MIN`)
NOZZLE = DEFAULT.nozzle
LAYER = DEFAULT.layer
BUILD = DEFAULT.build
WALL_MIN = DEFAULT.wall_min
WALL_LOAD = DEFAULT.wall_load
FLOOR_MIN = DEFAULT.floor_min
FEATURE_MIN = DEFAULT.feature_min
TEXT_STROKE_MIN = DEFAULT.text_stroke_min
TEXT_DEPTH_MIN = DEFAULT.text_depth_min
OVERHANG_MAX_DEG = DEFAULT.overhang_max_deg
BRIDGE_MAX = DEFAULT.bridge_max
BED_CHAMFER_MIN = DEFAULT.bed_chamfer_min
BED_CHAMFER_MAX = DEFAULT.bed_chamfer_max


def current() -> FDMProfile:
    """Return active FDMProfile reflecting user/project config.toml overrides."""
    cfg = load_config().printer
    nozzle = cfg.nozzle_mm
    layer = cfg.layer_mm
    return FDMProfile(
        nozzle=nozzle,
        layer=layer,
        build=cfg.build_volume,
        wall_min=round(max(DEFAULT.wall_min, 3.0 * nozzle), 2),
        wall_load=max(DEFAULT.wall_load, round(5.0 * nozzle, 2)),
        floor_min=round(max(DEFAULT.floor_min, 5.0 * layer), 2),
        feature_min=round(max(DEFAULT.feature_min, 2.0 * nozzle), 2),
        text_stroke_min=max(DEFAULT.text_stroke_min, round(2.5 * nozzle, 2)),
        text_depth_min=max(DEFAULT.text_depth_min, round(3.0 * layer, 2)),
    )
