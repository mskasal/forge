"""Print-plate placement and shelf-packing helpers (Z=0 bed, active build volume).

    from forge.layout import arrange_plate, place_on_bed
    plate = arrange_plate({"body": body, "lid": lid}, rotations={"lid": (180, 0, 0)})
"""

from __future__ import annotations

from build123d import Pos, Rot, Shape

from forge import fdm


def place_on_bed(
    shape: Shape,
    x: float = 0.0,
    y: float = 0.0,
    rot: tuple[float, float, float] | None = None,
) -> Shape:
    """Rotate `shape` if requested and place its bounding box at (x, y, z=0)."""
    if rot is not None:
        rx, ry, rz = rot
        shape = Rot(rx, ry, rz) * shape
    bb = shape.bounding_box()
    return Pos(x - bb.min.X, y - bb.min.Y, -bb.min.Z) * shape


def arrange_plate(
    parts: dict[str, Shape],
    *,
    gap: float = 8.0,
    rotations: dict[str, tuple[float, float, float]] | None = None,
    max_width: float | None = None,
    check_build_volume: bool = True,
) -> dict[str, Shape]:
    """Shelf-pack multiple parts on Z=0 with `gap` mm spacing.

    Raises ValueError if the packed layout exceeds the configured printer build volume.
    """
    if gap < 0:
        raise ValueError(f"gap must be >= 0, got {gap}")
    rotations = rotations or {}
    build_lim = fdm.current().build
    limit_x = max_width if max_width is not None else max(build_lim[0] - 16.0, 1.0)

    placed: dict[str, Shape] = {}
    cur_x = 0.0
    cur_y = 0.0
    row_h = 0.0
    max_x = 0.0
    max_y = 0.0
    max_z = 0.0

    for name, shape in parts.items():
        oriented = place_on_bed(shape, 0.0, 0.0, rotations.get(name))
        bb = oriented.bounding_box()
        w, d, h = bb.size.X, bb.size.Y, bb.size.Z
        if cur_x > 0.0 and cur_x + w > limit_x:
            cur_x = 0.0
            cur_y += row_h + gap
            row_h = 0.0
        positioned = Pos(cur_x, cur_y, 0.0) * oriented
        placed[name] = positioned
        max_x = max(max_x, cur_x + w)
        max_y = max(max_y, cur_y + d)
        max_z = max(max_z, h)
        cur_x += w + gap
        row_h = max(row_h, d)

    if check_build_volume and placed:
        for axis_name, val, lim in zip(("X", "Y", "Z"), (max_x, max_y, max_z), build_lim):
            if val > lim + 1e-6:
                raise ValueError(
                    f"print plate exceeds build volume on {axis_name}: {val:.1f} > {lim:g} mm"
                )
    return placed
