"""plate-and-pins — tolerance-test. Spec: SPEC.md (next to this file).

Run from the project root:  forge run hardware/parts/plate-and-pins/plate-and-pins.py
Upload when the check is OK: forge push tolerance-test --preview -m "what changed"

Every value is `design`: the test part fits no real object.
"""

from build123d import Align, Axis, Box, BuildPart, Cylinder, Locations, Mode, Pos, chamfer

from forge.check import check

CLEARANCES = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]  # design — per side, mm

ROUND_D = 4.0  # design — round pin nominal diameter
SQUARE_W = 5.0  # design — square pin nominal side
PITCH = 7.5  # design — hole centre spacing
PLATE_T = 3.0  # design — plate thickness = fit depth (15 layers)
MARGIN = 3.5  # design — plate edge margin; wall between holes >= 1.9 mm
ROW_GAP = 7.5  # design — distance between the two hole rows
MARK = 3.0  # design — cut corner marking hole 1
BED_CHAMFER = 0.4  # design — bed-edge chamfer (elephant foot)

PIN_H = 6.0  # design — pin height; > PLATE_T so it pushes through
PIN_TIP = 0.4  # design — pin tip chamfer, eases entry
TAB_L, TAB_W, TAB_T = 20.0, 9.0, 2.0  # design — pin grip tab

n = len(CLEARANCES)
PLATE_L = (n - 1) * PITCH + 2 * MARGIN + SQUARE_W
PLATE_W = ROW_GAP + 2 * MARGIN + SQUARE_W
xs = [(i - (n - 1) / 2) * PITCH for i in range(n)]

with BuildPart() as plate:
    Box(PLATE_L, PLATE_W, PLATE_T, align=(Align.CENTER, Align.CENTER, Align.MIN))
    # Direction mark: cut the vertical edge at hole 1 (-X, +Y)
    corner = plate.edges().filter_by(Axis.Z).sort_by(Axis.X)[:2].sort_by(Axis.Y)[-1]
    chamfer(corner, MARK)
    chamfer(plate.edges().filter_by_position(Axis.Z, 0, 0), BED_CHAMFER)
    for x, c in zip(xs, CLEARANCES):
        with Locations((x, ROW_GAP / 2, PLATE_T / 2)):
            Cylinder(ROUND_D / 2 + c, PLATE_T, mode=Mode.SUBTRACT)
        with Locations((x, -ROW_GAP / 2, PLATE_T / 2)):
            Box(SQUARE_W + 2 * c, SQUARE_W + 2 * c, PLATE_T, mode=Mode.SUBTRACT)

with BuildPart() as pins:
    Box(TAB_L, TAB_W, TAB_T, align=(Align.CENTER, Align.CENTER, Align.MIN))
    chamfer(pins.edges().filter_by_position(Axis.Z, 0, 0), BED_CHAMFER)
    with Locations((-TAB_L / 4, 0, TAB_T)):
        Cylinder(ROUND_D / 2, PIN_H, align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations((TAB_L / 4, 0, TAB_T)):
        Box(SQUARE_W, SQUARE_W, PIN_H, align=(Align.CENTER, Align.CENTER, Align.MIN))
    chamfer(pins.edges().filter_by_position(Axis.Z, TAB_T + PIN_H, TAB_T + PIN_H), PIN_TIP)

if __name__ == "__main__":
    check({"plate": plate.part, "pins": Pos(0, -(PLATE_W / 2 + TAB_W / 2 + 5), 0) * pins.part},
          name="tolerance-test")
