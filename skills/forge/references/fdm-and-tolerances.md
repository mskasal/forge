# Default FDM Rules & Reference Tolerances

Single source in code: `src/forge/fdm.py` (automated tests verify exact parity with `fdm.DEFAULT`).
Baseline profile: 0.4 mm nozzle, 0.20 mm layer height, 256 × 256 × 256 mm build volume (overridable via `config.toml`).

## FDM rules

These count as `design` sources; do not break them without a documented reason in `SPEC.md`.

- **Build volume:** 256 × 256 × 256 mm (override in `[printer] build_volume` for smaller/larger printers).
- **Walls:** at least 1.2 mm (3 perimeters). Load-bearing / screw walls 2.0 mm or more.
- **Floor / roof:** at least 1.0 mm (5 layers).
- **Smallest feature:** 0.8 mm. Embossed/engraved text: stroke ≥ 1 mm, depth ≥ 0.6 mm.
- **Overhangs:** up to 45° from vertical without support. Chamfer flatter faces or rotate the part. Supports are a last resort.
- **Bridges:** up to ~10 mm between supports.
- **Horizontal holes:** use `forge.mechanisms.teardrop_hole()` or chamfered tops; flat roofs sag.
- **Bed edge:** 0.4–0.6 mm chamfer (not a fillet) on edges that sit on the bed.
- **Orientation:** largest flat face on the bed. Layer bonds are weak; orient loads along layers. Models print as positioned in code (Z up, bottom on Z=0 — use `forge.layout.arrange_plate`).
- **Heat-set inserts / screws:** hole size from the insert/screw datasheet, never guessed.

## Reference tolerances (PLA, 0.4 mm nozzle, 0.20 mm layers)

Source: `skills/forge/examples/tolerance-test/` (vertical holes/pins). Values are **per side**; add twice to a diameter or width. Print the tolerance coupon on your own printer/filament to calibrate.

| Fit class | Round (pin/hole) | Square / rectangular |
| --- | --- | --- |
| Press fit (hammered in) | 0.10 mm | 0.05 mm |
| Tight slide (by hand, doesn't fall out) | 0.15 mm | 0.10 mm |
| Easy slide (goes in easily, no play) | 0.20 mm | 0.15 mm |
| Loose / lid | 0.25 mm | 0.20 mm |

Example: hole for a Ø4 mm pin (easy slide) = `4 + 2 × 0.20 = Ø4.40 mm`.
