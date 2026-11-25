"""Tests for forge.layout, forge.validate, forge.mechanisms, forge.init, and forge.components."""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest
from build123d import Align, Axis, Box, Pos

from forge import components as comp_mod
from forge.init import init as forge_init
from forge.layout import arrange_plate, place_on_bed
from forge.mechanisms import (
    button_plunger,
    cantilever_strain,
    heatset_boss,
    light_pipe_channel,
    oring_groove,
    pcb_standoff,
    prism_xy,
    prism_yz,
    snap_cantilever,
    teardrop_hole,
    usbc_cutout,
)
from forge.validate import assert_clearance, assert_fdm_params, print_scan


def test_place_on_bed_and_arrange_plate():
    floating = Pos(50, -30, 12) * Box(20, 10, 5)
    placed = place_on_bed(floating, x=4.0, y=6.0)
    bb = placed.bounding_box()
    assert bb.min.X == pytest.approx(4.0, abs=1e-4)
    assert bb.min.Y == pytest.approx(6.0, abs=1e-4)
    assert bb.min.Z == pytest.approx(0.0, abs=1e-4)

    plate = arrange_plate({"a": Box(30, 20, 10), "b": Box(30, 20, 8)}, gap=8.0)
    assert plate["a"].bounding_box().min.Z == pytest.approx(0.0, abs=1e-4)
    assert plate["b"].bounding_box().min.X == pytest.approx(38.0, abs=1e-4)

    with pytest.raises(ValueError, match="build volume"):
        arrange_plate({"huge": Box(300, 20, 10)})


def test_assert_fdm_params_and_clearance():
    assert_fdm_params(wall=1.6, load_wall=2.0, floor=1.2, feature=0.8, bed_chamfer=0.4, overhang_deg=45, bridge=8)
    with pytest.raises(AssertionError, match="wall"):
        assert_fdm_params(wall=0.8)
    with pytest.raises(AssertionError, match="bed_chamfer"):
        assert_fdm_params(bed_chamfer=1.2)

    a = Box(10, 10, 10)
    b = Pos(10.5, 0, 0) * Box(10, 10, 10)
    dist = assert_clearance(a, b, min_mm=0.2, label="gap")
    assert dist == pytest.approx(0.5, abs=1e-3)

    with pytest.raises(AssertionError, match="clearance"):
        assert_clearance(a, b, min_mm=1.0)
    with pytest.raises(AssertionError, match="interference"):
        assert_clearance(a, Pos(5, 0, 0) * Box(10, 10, 10), min_mm=0.1)


def test_print_scan_detects_clean_island_overhang_and_thin():
    # Clean box on bed
    clean = place_on_bed(Box(12, 12, 6))
    res = print_scan(clean, "clean", pixel_mm=0.2, layer_h=0.4)
    assert res.ok, str(res)

    # Mid-air island
    island = place_on_bed(Box(10, 10, 2)) + Pos(0, 0, 4.0) * Box(4, 4, 2, align=(Align.CENTER, Align.CENTER, Align.MIN))
    res_island = print_scan(island, "island", pixel_mm=0.2, layer_h=0.4)
    assert res_island.islands > 0

    # Unsupported horizontal shelf (overhang)
    shelf = place_on_bed(Box(4, 10, 6)) + Pos(5, 0, 4) * Box(8, 10, 2, align=(Align.MIN, Align.CENTER, Align.MIN))
    res_oh = print_scan(shelf, "shelf", pixel_mm=0.2, layer_h=0.4)
    assert res_oh.overhangs > 0

    # Thin wall (< 0.8 mm feature_min)
    thin = place_on_bed(Box(0.4, 12, 4))
    res_thin = print_scan(thin, "thin", pixel_mm=0.1, layer_h=0.4)
    assert res_thin.thin_regions > 0


def test_mechanisms_geometry_and_bounds():
    for axis in (Axis.X, Axis.Y):
        td = teardrop_hole(3.0, 10.0, axis=axis)
        assert td.is_valid
        assert len(td.solids()) == 1
        bb = td.bounding_box()
        assert bb.max.Z == pytest.approx(3.0 * math.sqrt(2.0), abs=1e-2)
        assert bb.min.Z == pytest.approx(-3.0, abs=1e-2)

    so = pcb_standoff(6.0, 5.0, hole_d=2.5)
    assert so.is_valid and len(so.solids()) == 1
    so_pin = pcb_standoff(6.0, 5.0, pin_d=1.8, pin_h=2.0)
    assert so_pin.is_valid and so_pin.bounding_box().max.Z == pytest.approx(7.0, abs=1e-3)
    with pytest.raises(ValueError, match="standoff wall"):
        pcb_standoff(4.0, 5.0, hole_d=3.0)

    arm = snap_cantilever(14.0, 1.4, 4.0, 1.2)
    assert arm.is_valid and len(arm.solids()) == 1
    assert cantilever_strain(1.4, 1.2, 14.0) == pytest.approx(3 * 1.4 * 1.2 / (2 * 196.0))

    usb = usbc_cutout(3.0)
    assert usb.is_valid and usb.bounding_box().size.Z == pytest.approx(3.0, abs=1e-3)

    p1 = prism_xy([(0, 0), (10, 0), (10, 5), (0, 5)], z0=2.0, height=3.0)
    assert p1.bounding_box().min.Z == pytest.approx(2.0) and p1.bounding_box().max.Z == pytest.approx(5.0)
    p2 = prism_yz([(0, 0), (5, 0), (0, 5)], x0=1.0, width=4.0)
    assert p2.bounding_box().min.X == pytest.approx(1.0) and p2.bounding_box().max.X == pytest.approx(5.0)

    # Heat-set insert boss
    for thread in ("M2", "M2.5", "M3", "M4"):
        boss = heatset_boss(thread)
        assert boss.is_valid and len(boss.solids()) == 1
        assert boss.bounding_box().min.Z == pytest.approx(0.0, abs=1e-3)
    with pytest.raises(ValueError, match="unsupported heat-set thread"):
        heatset_boss("M99")
    with pytest.raises(ValueError, match="hole depth"):
        heatset_boss("M3", depth=2.0)
    with pytest.raises(ValueError, match="boss wall"):
        heatset_boss("M3", outer_d=5.0)

    # Tactile button plunger
    btn = button_plunger(14.0, 5.0, 1.0, travel=0.8, stem_d=3.0, stem_h=2.0)
    assert btn.is_valid and len(btn.solids()) == 1
    assert btn.bounding_box().max.Z == pytest.approx(3.0, abs=1e-3)
    with pytest.raises(ValueError, match="bending strain"):
        button_plunger(6.0, 5.0, 2.0, travel=2.0)

    # LED light-pipe channel
    lp = light_pipe_channel(3.2, bore_d=2.0, collar_d=4.0, collar_h=1.2)
    assert lp.is_valid and lp.bounding_box().size.Z == pytest.approx(3.25, abs=0.1)
    with pytest.raises(ValueError, match="collar_d"):
        light_pipe_channel(3.0, bore_d=2.0, collar_d=1.5)

    # O-ring / gasket groove
    og = oring_groove(inner_d=20.0, cord_d=2.0)
    assert og.is_valid and len(og.solids()) == 1
    assert og.bounding_box().min.Z == pytest.approx(0.0, abs=1e-3)
    with pytest.raises(ValueError, match="squeeze"):
        oring_groove(inner_d=20.0, cord_d=2.0, squeeze=0.5)


def test_forge_init_scaffolds_params_and_isolated_imports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    hw = forge_init(name="sensor-box", part="base", style="quiet")
    forge_init(name="sensor-box", part="lid", style="quiet")

    assert (hw / "HARDWARE.md").is_file()
    assert (hw / "components.md").is_file()
    assert (hw / "parts/base/params.py").is_file()
    assert (hw / "parts/base/base.py").is_file()
    assert (hw / "parts/lid/params.py").is_file()
    assert (hw / "parts/lid/lid.py").is_file()
    assert "out/" in (tmp_path / ".gitignore").read_text(encoding="utf-8")

    # Customize distinct params in each part to verify isolated sibling imports
    (hw / "parts/base/params.py").write_text("WALL = 2.0\nFLOOR = 1.6\nBED_CHAMFER = 0.4\nWIDTH = 50.0\nDEPTH = 30.0\nHEIGHT = 12.0\n", encoding="utf-8")
    (hw / "parts/lid/params.py").write_text("WALL = 2.4\nFLOOR = 1.6\nBED_CHAMFER = 0.4\nWIDTH = 54.0\nDEPTH = 34.0\nHEIGHT = 8.0\n", encoding="utf-8")

    loaded_widths = []
    for part in ("base", "lid"):
        path = hw / "parts" / part / f"{part}.py"
        spec = importlib.util.spec_from_file_location(f"test_{part}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        loaded_widths.append(mod.P.WIDTH)
    assert loaded_widths == [50.0, 54.0]


def test_components_library_builds_valid_envelopes():
    mods = comp_mod.all_components()
    assert "raspberry_pi_pico" in mods
    assert comp_mod.print_catalog() == 0
    pico = mods["raspberry_pi_pico"]
    assert not comp_mod.validate(pico)
    env = pico.body()
    assert env.is_valid
    assert env.bounding_box().size.X == pytest.approx(51.0, abs=0.1)
