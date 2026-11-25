"""Reusable FDM-safe mechanical building blocks (obeying active forge.fdm bounds)."""

from __future__ import annotations

import math

from build123d import (
    Align,
    Axis,
    Box,
    BuildPart,
    BuildSketch,
    Cone,
    Cylinder,
    Part,
    Plane,
    Polyline,
    Pos,
    RectangleRounded,
    Rot,
    chamfer,
    extrude,
    loft,
    make_face,
)

from forge import fdm


def prism_xy(points: list[tuple[float, float]], z0: float, height: float) -> Part:
    """Extrude a closed 2D (x, y) polygon from z0 along +Z by `height`."""
    face = Plane.XY * make_face(Polyline(*points, close=True))
    return Pos(0, 0, z0) * extrude(face, height, dir=(0, 0, 1))


def prism_yz(points: list[tuple[float, float]], x0: float, width: float) -> Part:
    """Extrude a closed 2D (y, z) polygon from x0 along +X by `width`."""
    face = Plane.YZ * make_face(Polyline(*points, close=True))
    return Pos(x0, 0, 0) * extrude(face, width, dir=(1, 0, 0))


def teardrop_hole(radius: float, depth: float, *, axis: Axis = Axis.X) -> Part:
    """Support-free horizontal hole cutter with a 45° top peak along +Z."""
    if radius <= 0 or depth <= 0:
        raise ValueError("radius and depth must be positive")
    c = radius * math.sqrt(0.5)
    peak = radius * math.sqrt(2.0)
    if axis == Axis.X:
        cyl = Cylinder(radius, depth, rotation=(0, 90, 0), align=(Align.CENTER, Align.CENTER, Align.MIN))
        roof = prism_yz([(-c, c), (0.0, peak), (c, c)], 0.0, depth)
        return cyl + roof
    if axis == Axis.Y:
        cyl = Cylinder(radius, depth, rotation=(-90, 0, 0), align=(Align.CENTER, Align.CENTER, Align.MIN))
        roof = Rot(0, 0, 90) * prism_yz([(-c, c), (0.0, peak), (c, c)], 0.0, depth)
        return cyl + roof
    raise ValueError("teardrop_hole axis must be Axis.X or Axis.Y")


def pcb_standoff(
    outer_d: float,
    height: float,
    *,
    hole_d: float | None = None,
    pin_d: float | None = None,
    pin_h: float = 2.0,
) -> Part:
    """Cylindrical PCB standoff resting on Z=0, centred in XY."""
    prof = fdm.current()
    if hole_d is not None and pin_d is not None:
        raise ValueError("specify either hole_d or pin_d, not both")
    if hole_d is not None and (outer_d - hole_d) / 2.0 < prof.wall_min - 1e-9:
        raise ValueError(
            f"standoff wall {(outer_d - hole_d) / 2:.2f} mm < FDM min {prof.wall_min} mm"
        )
    if pin_d is not None and pin_d < prof.feature_min - 1e-9:
        raise ValueError(f"pin_d {pin_d} mm < FDM min {prof.feature_min} mm")
    base = Cylinder(outer_d / 2.0, height, align=(Align.CENTER, Align.CENTER, Align.MIN))
    if hole_d is not None:
        base -= Cylinder(hole_d / 2.0, height + 0.1, align=(Align.CENTER, Align.CENTER, Align.MIN))
    elif pin_d is not None:
        pin = Cylinder(pin_d / 2.0, pin_h, align=(Align.CENTER, Align.CENTER, Align.MIN))
        top_ch = min(0.4, pin_d * 0.25, pin_h * 0.4)
        if top_ch >= 0.1:
            pin = chamfer(pin.edges().filter_by_position(Axis.Z, pin_h, pin_h), top_ch)
        base += Pos(0, 0, height) * pin
    return base


def cantilever_strain(thickness: float, deflection: float, length: float) -> float:
    """Maximum root bending strain for a rectangular cantilever arm: 3·t·δ / (2·L²)."""
    if length <= 0 or thickness <= 0:
        raise ValueError("length and thickness must be positive")
    return 3.0 * thickness * abs(deflection) / (2.0 * length * length)


def snap_cantilever(
    length: float,
    thickness: float,
    width: float,
    hook_depth: float,
    *,
    hook_tip: float = 0.8,
    lead_angle_deg: float = 45.0,
) -> Part:
    """Parametric cantilever snap-fit arm in XY extruded along Z=[0, width]."""
    prof = fdm.current()
    if thickness < prof.feature_min - 1e-9:
        raise ValueError(f"arm thickness {thickness} < FDM min {prof.feature_min} mm")
    if width < prof.feature_min - 1e-9:
        raise ValueError(f"arm width {width} < FDM min {prof.feature_min} mm")
    lead_len = hook_depth / math.tan(math.radians(lead_angle_deg))
    x_catch = length - lead_len - hook_tip
    if x_catch <= 0:
        raise ValueError("arm length is too short for the requested hook depth and lead-in")
    pts = [
        (0.0, 0.0),
        (length, 0.0),
        (length, thickness),
        (length - lead_len, thickness + hook_depth),
        (x_catch, thickness + hook_depth),
        (x_catch, thickness),
        (0.0, thickness),
    ]
    return prism_xy(pts, 0.0, width)


def usbc_cutout(
    wall_depth: float,
    *,
    width: float = 13.0,
    height: float = 7.0,
    corner_r: float = 0.8,
    flare: float = 0.8,
) -> Part:
    """USB-C overmold clearance cutter along Z=[0, wall_depth], centred in XY."""
    with BuildPart() as p:
        with BuildSketch():
            RectangleRounded(width, height, corner_r)
        extrude(amount=wall_depth)
        if flare > 0:
            if flare >= wall_depth:
                raise ValueError(f"flare ({flare}) must be smaller than wall_depth ({wall_depth})")
            with BuildSketch(Plane.XY.offset(wall_depth - flare)):
                RectangleRounded(width, height, corner_r)
            with BuildSketch(Plane.XY.offset(wall_depth)):
                RectangleRounded(width + 2 * flare, height + 2 * flare, corner_r + flare)
            loft()
    return p.part


# Standard Ruthex / CNC Kitchen brass heat-set insert dimensions: (hole_d, min_insert_len) in mm.
HEATSET_INSERTS: dict[str, tuple[float, float]] = {
    "M2": (3.2, 4.0),
    "M2.5": (4.0, 5.0),
    "M3": (4.0, 5.7),
    "M4": (5.6, 8.1),
}


def heatset_boss(
    thread: str = "M3",
    depth: float | None = None,
    *,
    outer_d: float | None = None,
    wall: float | None = None,
    lead_in: float = 0.4,
) -> Part:
    """Cylindrical brass heat-set insert boss resting on Z=0, centred in XY."""
    key = thread.upper()
    if key not in HEATSET_INSERTS:
        raise ValueError(f"unsupported heat-set thread {thread!r}; options: {', '.join(HEATSET_INSERTS)}")
    prof = fdm.current()
    hole_d, min_len = HEATSET_INSERTS[key]
    hole_depth = depth if depth is not None else min_len + 1.0
    if hole_depth < min_len - 1e-9:
        raise ValueError(f"{key} insert needs at least {min_len} mm hole depth (got {hole_depth} mm)")
    wall_t = wall if wall is not None else max(prof.wall_min, 1.6)
    od = outer_d if outer_d is not None else hole_d + 2.0 * wall_t
    actual_wall = (od - hole_d) / 2.0
    if actual_wall < prof.wall_min - 1e-9:
        raise ValueError(f"heat-set boss wall {actual_wall:.2f} mm < FDM min {prof.wall_min} mm")
    boss_h = hole_depth + prof.floor_min
    boss = Cylinder(od / 2.0, boss_h, align=(Align.CENTER, Align.CENTER, Align.MIN))
    bore = Pos(0, 0, prof.floor_min) * Cylinder(
        hole_d / 2.0, hole_depth + 0.1, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )
    boss -= bore
    if lead_in > 0:
        if lead_in >= actual_wall:
            raise ValueError(f"lead_in ({lead_in} mm) must be smaller than boss wall ({actual_wall:.2f} mm)")
        cone = Pos(0, 0, boss_h - lead_in) * Cone(
            hole_d / 2.0,
            hole_d / 2.0 + lead_in,
            lead_in + 0.05,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
        boss -= cone
    return boss


def button_plunger(
    length: float,
    width: float,
    thickness: float,
    *,
    travel: float = 0.8,
    stem_d: float = 3.0,
    stem_h: float = 2.0,
    max_strain: float = 0.025,
) -> Part:
    """Cantilever living-hinge tactile button resting on Z=0 along +X with actuator stem on +Z."""
    prof = fdm.current()
    if thickness < prof.feature_min - 1e-9:
        raise ValueError(f"button arm thickness {thickness} mm < FDM min {prof.feature_min} mm")
    if width < prof.feature_min - 1e-9:
        raise ValueError(f"button arm width {width} mm < FDM min {prof.feature_min} mm")
    if stem_d < prof.feature_min - 1e-9:
        raise ValueError(f"button stem_d {stem_d} mm < FDM min {prof.feature_min} mm")
    if length <= stem_d:
        raise ValueError("button arm length must exceed stem_d")
    strain = cantilever_strain(thickness, travel, length)
    if strain > max_strain:
        raise ValueError(
            f"button bending strain {strain:.4f} exceeds max {max_strain:.4f}; increase length or reduce thickness/travel"
        )
    arm = Box(length, width, thickness, align=(Align.MIN, Align.CENTER, Align.MIN))
    stem = Pos(length - stem_d / 2.0, 0.0, thickness) * Cylinder(
        stem_d / 2.0, stem_h, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )
    return arm + stem


def light_pipe_channel(
    wall_depth: float,
    *,
    bore_d: float = 2.0,
    collar_d: float | None = None,
    collar_h: float = 1.5,
    chamfer_out: float = 0.4,
) -> Part:
    """SMD LED light-pipe / diffuser channel cutter along Z=[0, wall_depth], centred in XY."""
    prof = fdm.current()
    if wall_depth <= 0:
        raise ValueError("wall_depth must be positive")
    if bore_d < prof.feature_min - 1e-9:
        raise ValueError(f"bore_d {bore_d} mm < FDM min {prof.feature_min} mm")
    cutter = Cylinder(bore_d / 2.0, wall_depth, align=(Align.CENTER, Align.CENTER, Align.MIN))
    if collar_d is not None:
        if collar_d <= bore_d:
            raise ValueError("collar_d must be larger than bore_d")
        if collar_h <= 0 or collar_h >= wall_depth:
            raise ValueError("collar_h must be between 0 and wall_depth")
        cutter += Cylinder(collar_d / 2.0, collar_h, align=(Align.CENTER, Align.CENTER, Align.MIN))
    if chamfer_out > 0:
        if chamfer_out >= wall_depth:
            raise ValueError("chamfer_out must be smaller than wall_depth")
        cutter += Pos(0, 0, wall_depth - chamfer_out) * Cone(
            bore_d / 2.0,
            bore_d / 2.0 + chamfer_out,
            chamfer_out + 0.05,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
    return cutter


def oring_groove(
    inner_d: float,
    cord_d: float,
    *,
    squeeze: float = 0.22,
    fill: float = 0.78,
) -> Part:
    """Annular face O-ring / gasket groove cutter resting on Z=0, centred in XY."""
    prof = fdm.current()
    if inner_d <= 0:
        raise ValueError("inner_d must be positive")
    if cord_d < prof.feature_min - 1e-9:
        raise ValueError(f"cord_d {cord_d} mm < FDM min {prof.feature_min} mm")
    if not (0.10 <= squeeze <= 0.35):
        raise ValueError("squeeze must be between 0.10 and 0.35")
    if not (0.50 <= fill <= 0.90):
        raise ValueError("fill must be between 0.50 and 0.90")
    depth = cord_d * (1.0 - squeeze)
    area = math.pi * (cord_d / 2.0) ** 2
    width = max(cord_d * 1.15, area / (depth * fill))
    outer_r = inner_d / 2.0 + width
    inner_r = inner_d / 2.0
    outer = Cylinder(outer_r, depth, align=(Align.CENTER, Align.CENTER, Align.MIN))
    inner = Cylinder(inner_r, depth + 0.1, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return outer - inner
