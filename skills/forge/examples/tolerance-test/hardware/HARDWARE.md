# tolerance-test — hardware

<!-- Worked example: a real part, designed, printed, and measured to calibrate PLA tolerances. -->

- **Purpose:** measure how much clearance a pin needs in a hole on the A1 to press fit,
  slide or sit loose, so every later part uses measured tolerances instead of guesses.
- **Used where:** on the desk, once. The result is the tolerance table in the forge skill.
- **Created:** 2026-11-01

## Parts

| Part | Status | Forge name | Latest | Notes |
| --- | --- | --- | --- | --- |
| plate-and-pins | verified | `tolerance-test` | v1 | one print, 17 min, ~2.7 cm³ |

<!-- Status: draft → approved → designed → printed vN → verified (see each SPEC.md). -->

## Project-wide constraints

- Printer: Bambu A1, 0.4 mm nozzle, 0.20mm Standard, Textured PEI.
- Material: PLA Matte (tolerances depend on material).
- Under 20 minutes of printing.

## Open questions

- Horizontal holes (in side walls) and screws / heat-set inserts: not covered; a separate
  small test once the screw / insert and its datasheet are chosen.
