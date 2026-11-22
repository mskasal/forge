"""Geometry helpers applying a Forge design language."""

from __future__ import annotations

import math

from build123d import (
    Align,
    Axis,
    Box,
    BuildPart,
    BuildSketch,
    Cylinder,
    Locations,
    Part,
    Pos,
    RectangleRounded,
    Rot,
    SlotCenterToCenter,
    Text,
    chamfer,
    extrude,
    fillet,
)

from forge.styles import Style


def shell(s: Style, length: float, width: float, height: float) -> Part:
    """Solid block with base on Z=0, centred in XY, with the language's edge treatment."""
    with BuildPart() as p:
        Box(length, width, height, align=(Align.CENTER, Align.CENTER, Align.MIN))
        if s.corner_r:
            fillet(p.edges().filter_by(Axis.Z), s.corner_r)
        top = p.edges().filter_by_position(Axis.Z, height, height)
        if s.top_edge == "fillet":
            fillet(top, s.top_edge_size)
        else:
            chamfer(top, s.top_edge_size)
        chamfer(p.edges().filter_by_position(Axis.Z, 0, 0), s.bed_chamfer)
    return p.part


def grille(s: Style, length: float, width: float, depth: float) -> Part:
    """Cutter: language holes or slots filling length × width, top at Z=0."""
    pitch = s.grille_pitch
    with BuildPart() as p:
        if s.grille == "slots":
            n = max(1, math.floor((width - s.grille_size) / pitch) + 1)
            slot = min(s.slot_len, length)
            ys = [(i - (n - 1) / 2) * pitch for i in range(n)]
            with BuildSketch():
                for y in ys:
                    with Locations((0, y)):
                        SlotCenterToCenter(slot - s.grille_size, s.grille_size)
            extrude(amount=-depth)
        else:
            nx = max(1, math.floor((length - s.grille_size) / pitch) + 1)
            ny = max(1, math.floor((width - s.grille_size) / pitch) + 1)
            pts = [
                ((i - (nx - 1) / 2) * pitch, (j - (ny - 1) / 2) * pitch)
                for i in range(nx)
                for j in range(ny)
            ]
            with Locations(*pts):
                Cylinder(s.grille_size / 2, depth, align=(Align.CENTER, Align.CENTER, Align.MAX))
    return p.part


def ribs(s: Style, length: float, width: float) -> Part:
    """Cutter: vertical grooves across `length`, each `width` long, top at Z=0."""
    if not s.rib_depth:
        raise ValueError(f"design language {s.name!r} uses no ribs")
    n = max(1, math.floor((length - s.rib_width) / s.rib_pitch) + 1)
    with BuildPart() as p:
        with Locations(*[((i - (n - 1) / 2) * s.rib_pitch, 0) for i in range(n)]):
            Box(s.rib_width, width, s.rib_depth, align=(Align.CENTER, Align.CENTER, Align.MAX))
    return p.part


def label(s: Style, text: str, size: float | None = None) -> Part:
    """Cutter: engraved text in the language's font and case, top at Z=0, centred."""
    if not s.text_size:
        raise ValueError(f"design language {s.name!r} uses no text")
    size = size or s.text_size
    if size < s.text_size:
        raise ValueError(f"text size {size} < {s.text_size} (stroke would be under FDM minimum)")
    if s.text_case == "upper":
        text = text.upper()
    elif s.text_case == "lower":
        text = text.lower()
    with BuildPart() as p:
        with BuildSketch():
            Text(text, size, font_path=str(s.font_path), align=(Align.CENTER, Align.CENTER))
        extrude(amount=-s.text_depth)
    return p.part


def panel(s: Style, length: float, width: float) -> Part | None:
    """Cutter: inset rounded panel (`s.panel_recess` deep), or None if flush."""
    if not s.panel_recess:
        return None
    with BuildPart() as p:
        with BuildSketch():
            RectangleRounded(length, width, max(s.corner_r, 0.5))
        extrude(amount=-s.panel_recess)
    return p.part


def specimen(s: Style) -> Part:
    """Small tile showcasing a language's edges, grille, label, panel, and ribs."""
    g = s.grid
    length = 20 * g if g < 5 else 12 * g if g < 10 else 7 * g
    width = round(length * 0.6 / g) * g
    height = 4 * g if g < 5 else 2 * g if g < 10 else g
    body = shell(s, length, width, height)
    top = Pos(0, 0, height)
    inner = length - 2 * max(s.corner_r, g)
    body -= top * Pos(-inner / 4, width * 0.2, 0) * grille(s, inner / 2 - g, width * 0.35, 1.2)
    text_top = top * Pos(0, -width * 0.2, 0)
    if (inset := panel(s, inner, width * 0.4)) is not None:
        body -= text_top * inset
        text_top = text_top * Pos(0, 0, -s.panel_recess)
    if s.text_size:
        body -= text_top * label(s, "forge")
    if s.rib_depth:
        span = width - 2 * max(s.corner_r, s.rib_pitch)
        face_h = height - 2 * max(s.top_edge_size, s.bed_chamfer) - 2
        for x, rot in ((length / 2, 90), (-length / 2, -90)):
            body -= Pos(x, 0, height / 2) * Rot(0, rot, 0) * Rot(0, 0, 90) * ribs(s, span, face_h)
    return body
