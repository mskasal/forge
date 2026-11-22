"""Unified design-language library and geometry helpers.

    from forge.styles import load, shell, grille, label, panel, ribs
    s = load("quiet")
    body = shell(s, 80, 50, 20)
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from forge import fdm

FONTS = Path(__file__).resolve().parent / "fonts"


@dataclass(frozen=True)
class Style:
    name: str
    intent: str
    fits: tuple[str, ...]
    inspired_by: tuple[str, ...]
    corner_r: float
    top_edge: str  # "chamfer" | "fillet"
    top_edge_size: float
    bed_chamfer: float
    wall: float
    floor: float
    grid: float
    grille: str  # "holes" | "slots"
    grille_size: float
    grille_pitch: float
    slot_len: float
    panel_recess: float
    text_font: str
    text_size: float
    text_depth: float
    text_case: str  # "upper" | "lower" | "as-is"
    body_color: str
    preview_color: str
    accent: str = ""
    rib_width: float = 0.0
    rib_pitch: float = 0.0
    rib_depth: float = 0.0
    grille_depth: float = 0.0
    notes: tuple[str, ...] = field(default=())

    @property
    def font_path(self) -> Path:
        return FONTS / self.text_font


@cache
def stroke_ratio(font: str) -> float:
    """Thinnest stroke / font size, measured on the font's hyphen."""
    from build123d import BuildSketch, Text

    with BuildSketch() as s:
        Text("-", 10.0, font_path=str(FONTS / font))
    return s.sketch.bounding_box().size.Y / 10.0


def all_styles() -> dict[str, Style]:
    out: dict[str, Style] = {}
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_") or info.name == "helpers":
            continue
        mod = importlib.import_module(f"{__name__}.{info.name}")
        if isinstance(getattr(mod, "STYLE", None), Style):
            out[info.name] = mod.STYLE
    return out


def get(name: str) -> Style:
    styles = all_styles()
    if name not in styles:
        raise KeyError(f"Unknown design language {name!r}; known: {', '.join(sorted(styles))}")
    return styles[name]


load = get


def validate(s: Style) -> list[str]:
    """Return FDM violations in a design language's tokens; empty list means valid."""
    p: list[str] = []

    def need(ok: bool, msg: str) -> None:
        if not ok:
            p.append(f"{s.name}: {msg}")

    need(s.wall >= fdm.WALL_MIN, f"wall {s.wall} < {fdm.WALL_MIN}")
    need(s.floor >= fdm.FLOOR_MIN, f"floor {s.floor} < {fdm.FLOOR_MIN}")
    need(
        fdm.BED_CHAMFER_MIN <= s.bed_chamfer <= fdm.BED_CHAMFER_MAX,
        f"bed chamfer {s.bed_chamfer} outside {fdm.BED_CHAMFER_MIN}–{fdm.BED_CHAMFER_MAX}",
    )
    need(s.top_edge in ("chamfer", "fillet"), f"top_edge {s.top_edge!r}")
    need(s.top_edge_size < s.wall, "top edge must be smaller than wall")
    need(s.grille in ("holes", "slots"), f"grille {s.grille!r}")
    need(s.grille_size >= fdm.FEATURE_MIN, f"grille size {s.grille_size} < {fdm.FEATURE_MIN}")
    need(
        s.grille_pitch - s.grille_size >= fdm.FEATURE_MIN,
        f"wall between grille openings {s.grille_pitch - s.grille_size:.2f} < {fdm.FEATURE_MIN}",
    )
    need(
        s.panel_recess == 0 or s.panel_recess >= 2 * fdm.LAYER,
        f"panel recess {s.panel_recess} < {2 * fdm.LAYER} (2 layers)",
    )
    if s.rib_depth:
        need(s.rib_width >= fdm.FEATURE_MIN, f"rib width {s.rib_width} < {fdm.FEATURE_MIN}")
        need(
            s.rib_pitch - s.rib_width >= fdm.FEATURE_MIN,
            f"land between ribs {s.rib_pitch - s.rib_width:.2f} < {fdm.FEATURE_MIN}",
        )
        need(s.rib_depth >= 2 * fdm.LAYER, f"rib depth {s.rib_depth} < {2 * fdm.LAYER} (2 layers)")
        need(
            s.wall - s.rib_depth >= fdm.WALL_MIN,
            f"wall under ribs {s.wall - s.rib_depth:.2f} < {fdm.WALL_MIN}",
        )
    if s.grille_depth:
        need(
            s.wall - s.grille_depth >= fdm.WALL_MIN,
            f"wall under blind grille {s.wall - s.grille_depth:.2f} < {fdm.WALL_MIN}",
        )
    need(s.text_case in ("upper", "lower", "as-is"), f"text_case {s.text_case!r}")
    if s.text_size:
        need(s.font_path.is_file(), f"font missing: {s.font_path}")
        if s.font_path.is_file():
            stroke = s.text_size * stroke_ratio(s.text_font)
            need(
                stroke >= fdm.TEXT_STROKE_MIN,
                f"text stroke {stroke:.2f} < {fdm.TEXT_STROKE_MIN} (raise text_size)",
            )
        need(s.text_depth >= fdm.TEXT_DEPTH_MIN, f"text depth {s.text_depth} < {fdm.TEXT_DEPTH_MIN}")
    need((Path(__file__).parent / f"{s.name}.md").is_file(), f"styles/{s.name}.md missing")
    return p


def print_catalog() -> int:
    """Print and validate all registered design languages. Returns CLI exit code."""
    problems: list[str] = []
    for name, s in sorted(all_styles().items()):
        print(f"{name}: {s.intent}")
        print(f"    fits: {', '.join(s.fits)}")
        print(
            f"    form: corners R{s.corner_r}, top {s.top_edge} {s.top_edge_size}, "
            f"bed chamfer {s.bed_chamfer}, wall {s.wall}, floor {s.floor}, grid {s.grid}"
        )
        grille_desc = f"{s.grille} {s.grille_size} @ {s.grille_pitch}"
        if s.grille == "slots":
            grille_desc += f" × {s.slot_len}"
        if s.grille_depth:
            grille_desc += f" (blind {s.grille_depth}, open only where needed)"
        print(f"    interface: grille {grille_desc}, panel recess {s.panel_recess or 'none'}")
        if s.rib_depth:
            print(f"    texture: ribs {s.rib_width} @ {s.rib_pitch}, {s.rib_depth} deep")
        if s.text_size:
            stroke = s.text_size * stroke_ratio(s.text_font) if s.font_path.is_file() else 0
            print(
                f"    text: {s.text_font} {s.text_size} ({s.text_case}), "
                f"stroke {stroke:.2f}, engraved {s.text_depth}"
            )
        else:
            print("    text: none")
        print(f"    colour: {s.body_color}" + (f", accent {s.accent} (separate part)" if s.accent else ""))
        problems += validate(s)
    for p in problems:
        print(f"PROBLEM: {p}")
    return 1 if problems else 0


# Re-export geometry helpers from unified forge.styles namespace
from forge.styles.helpers import grille, label, panel, ribs, shell, specimen  # noqa: E402, F401
