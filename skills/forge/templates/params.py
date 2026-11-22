"""Parameters for {{part}} ({{project}}).

Edit measurements, clearances and feature flags here — keep geometry code in {{part}}.py.
Every real-object dimension must cite its source (components.md, datasheet, or caliper date).
"""

from __future__ import annotations

from forge.validate import assert_fdm_params

# --- Real components (from ../../components.md or forge.components) ----------
# Example:
#   BATT_D = 18.4  # components.md#battery — datasheet: <url>

# --- Design choices & tolerances ---------------------------------------------
WALL = 2.0  # design — >= FDM wall min (1.2 mm; load-bearing >= 2.0 mm)
FLOOR = 1.6  # design — >= FDM floor min (1.0 mm)
BED_CHAMFER = 0.4  # design — 0.4–0.6 mm chamfer on bed edges
FIT = 0.20  # design — reference tolerance (easy slide, round / loose, square)

# --- Assumptions (explicitly approved by the owner; empty when all verified) -
ASSUMPTIONS: list[str] = []


def validate_params() -> None:
    """Fast pre-geometry checks (<1 ms). Add layout/clearance asserts here."""
    assert_fdm_params(wall=WALL, floor=FLOOR, bed_chamfer=BED_CHAMFER)
