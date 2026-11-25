"""Tests for headless Blender studio rendering, OrcaSlicer discovery, and Antigravity plugin.json."""

from __future__ import annotations

import json

import pytest

from forge import render as render_mod
from forge._paths import REPO_ROOT
from forge.config import SlicerConfig
from forge.slicers import get_slicer
from forge.slicers.orca import _find_cli, _find_profiles


def test_antigravity_plugin_manifest_valid():
    manifest_path = REPO_ROOT / "plugin.json"
    assert manifest_path.is_file()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["name"] == "forge"
    assert (REPO_ROOT / data["logo"]).is_file()
    assert 1 <= len(data["suggestedPrompts"]) <= 3


def test_orca_slicer_env_discovery(tmp_path, monkeypatch):
    fake_cli = tmp_path / "orca-slicer"
    fake_cli.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_profiles = tmp_path / "profiles"
    fake_profiles.mkdir()

    monkeypatch.setenv("FORGE_ORCA_CLI", str(fake_cli))
    monkeypatch.setenv("FORGE_ORCA_PROFILES", str(fake_profiles))
    assert _find_cli() == fake_cli
    assert _find_profiles(fake_cli) == fake_profiles
    slicer = get_slicer(SlicerConfig(backend="orca"))
    assert slicer is not None
    assert slicer.available() is True
    assert "textured" in slicer.plates()


def test_render_helpers_and_script_generation(tmp_path, monkeypatch):
    assert render_mod.hex_to_rgba("#ff0080") == pytest.approx((1.0, 0.0, 128 / 255.0, 1.0))
    with pytest.raises(ValueError, match="Expected #RRGGBB"):
        render_mod.hex_to_rgba("red")

    (tmp_path / "body.stl").write_bytes(b"solid\n")
    (tmp_path / "lid.stl").write_bytes(b"solid\n")
    (tmp_path / "assembly.stl").write_bytes(b"solid\n")
    stls = render_mod.collect_stls(tmp_path)
    assert [p.name for p in stls] == ["body.stl", "lid.stl"]

    script = render_mod.build_blender_script(
        {
            "stls": [str(p) for p in stls],
            "rgba": [0.2, 0.2, 0.2, 1.0],
            "exploded": True,
            "explode_gap_mm": 18.0,
            "turntable": False,
            "transparent": True,
            "engine": "cycles",
            "samples": 32,
            "width": 1280,
            "height": 720,
            "frames": 36,
            "output": str(tmp_path / "studio.png"),
            "frames_dir": str(tmp_path / "frames"),
        }
    )
    compile(script, "<blender_script>", "exec")
    assert "stl_import" in script
    assert "METAL" in script and "HIP" in script

    monkeypatch.setattr(render_mod, "find_blender", lambda: None)
    with pytest.raises(SystemExit, match="Blender not found"):
        render_mod.render_studio("demo")
