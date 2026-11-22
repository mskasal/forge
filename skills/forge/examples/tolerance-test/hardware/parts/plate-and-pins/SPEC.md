# plate-and-pins — spec

- **Project:** tolerance-test (see ../../HARDWARE.md)
- **Forge name:** `tolerance-test`
- **Status:** verified

## What it does

A test plate with two rows of holes, each a little wider than the last, and two pins
(round and square) at nominal size. Pushing each pin into each hole shows which clearance
gives a press fit, a slide, or a loose fit on this printer and filament.

## What goes in / on it

Nothing real: the pins and holes only fit each other. All values are `design`.

| Value | mm | Source |
| --- | --- | --- |
| Clearance per side, holes 1–6 | 0.05, 0.10, 0.15, 0.20, 0.25, 0.30 | design |
| Round pin Ø / square pin side | 4.0 / 5.0 | design |
| Plate 49.5 × 19.5 × 3 (fit depth 3 = 15 layers) | | design |
| Pin height 6, tip chamfer 0.4 | | design |
| Hole pitch 7.5, wall between holes ≥ 1.9 | | design — FDM wall ≥ 1.2 |

## Layout

- Top row: 6 round holes (for the Ø4 pin). Bottom row: 6 square holes (for the 5 × 5 pin).
- No text labels (small text prints badly). The **cut corner marks hole 1**; holes get
  wider to the right.
- Pins stand on a 20 × 9 × 2 mm grip tab.

## Assembly

- **Closing:** none; pins are pushed in by hand from the plate's top face.
- **Fit class:** what this part measures.
- **Service:** —

## Print

- **Material:** PLA Matte
- **Orientation:** both flat faces on the bed, no rotation; holes and pins vertical.
- **Supports:** none. 0.4 mm chamfer on bed edges.

## Acceptance criteria

- [x] One print under 20 minutes (17 min)
- [x] Every pin/hole pair can be classed (won't go / press / tight slide / easy slide / loose)
- [x] Results turned into a per-side tolerance table for round and square fits

## Suggestions (not yet accepted)

- A horizontal-hole and heat-set-insert test, once the insert/screw is chosen.

## Assumptions

None.

## Versions and prints

| Version | Date | Change | Printed | Result |
| --- | --- | --- | --- | --- |
| v1 | 2026-11-01 | first version | yes, 17 min, PLA Matte | see results below |

### Results — v1, 2026-11-01

Pins not measured with calipers. Owner's description per hole (clearance per side):

| Hole | 1 (0.05) | 2 (0.10) | 3 (0.15) | 4 (0.20) | 5 (0.25) | 6 (0.30) |
| --- | --- | --- | --- | --- | --- | --- |
| Round Ø4 | only with a lot of force | hard but easier | goes in, tight | very easy | very easy, maybe loose | wobbles |
| Square 5×5 | hard | easy, solid | very easy | very easy, maybe loose | very easy, maybe loose | quite loose |

Square holes fit about 0.05 mm looser than round ones: round holes print as polygons and
come out slightly smaller. Hence separate round / square values in the tolerance table:

| Fit | Round | Square |
| --- | --- | --- |
| Press fit | 0.10 | 0.05 |
| Tight slide | 0.15 | 0.10 |
| Easy slide | 0.20 | 0.15 |
| Loose / lid | 0.25 | 0.20 |
