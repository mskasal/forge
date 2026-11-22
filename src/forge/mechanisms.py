"""Reusable FDM-safe mechanical building blocks (obeying active forge.fdm bounds)."""

from __future__ import annotations

import math

from build123d import (
    Align,
    Axis,
    BuildPart,
    BuildSketch,
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
