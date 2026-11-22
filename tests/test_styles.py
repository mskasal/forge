"""Tests for forge.styles catalog, geometry helpers, and FDM reference doc parity."""

from __future__ import annotations

import re

from forge import fdm, styles
from forge._paths import SKILLS_DIR


def test_all_registered_styles_validate_and_catalog_succeeds():
    found = styles.all_styles()
    assert set(found) >= {"instrument", "quiet", "plain", "desk"}
    for name, s in found.items():
        issues = styles.validate(s)
        assert not issues, f"style {name} invalid: {issues}"
    assert styles.print_catalog() == 0


def test_style_helpers_produce_valid_solids():
    s = styles.load("quiet")
    body = styles.shell(s, 60, 40, 20)
    assert body.is_valid and len(body.solids()) == 1

    gr = styles.grille(s, 20, 12, depth=3.0)
    assert gr.is_valid and gr.volume > 0

    lbl = styles.label(s, "FORGE")
    assert lbl.is_valid and lbl.volume > 0

    inst = styles.load("instrument")
    pan = styles.panel(inst, 30, 15)
    assert pan is not None and pan.is_valid and pan.volume > 0

    desk = styles.load("desk")
    rb = styles.ribs(desk, 30, 15)
    assert rb.is_valid and rb.volume > 0


def test_fdm_reference_doc_matches_code_defaults():
    doc = (SKILLS_DIR / "references" / "fdm-and-tolerances.md").read_text(encoding="utf-8")
    p = fdm.DEFAULT
    patterns = [
        rf"\b{p.nozzle:.1f}0?\s*mm\b",
        rf"\b{p.layer:.1f}0?\s*mm\b",
        rf"\b{p.wall_min:.1f}0?\s*mm\b",
        rf"\b{p.wall_load:.1f}0?\s*mm\b",
        rf"\b{p.floor_min:.1f}0?\s*mm\b",
        rf"\b{p.feature_min:.1f}0?\s*mm\b",
        rf"\b{p.text_stroke_min:g}(?:\.0)?\s*mm\b",
        rf"\b{p.text_depth_min:.1f}0?\s*mm\b",
        rf"\b{p.overhang_max_deg:g}°",
        rf"\b{p.bridge_max:g}\s*mm\b",
        rf"\b{p.bed_chamfer_min:g}–{p.bed_chamfer_max:g}\s*mm\b",
    ]
    for pat in patterns:
        assert re.search(pat, doc), f"Missing pattern {pat!r} in fdm-and-tolerances.md"
