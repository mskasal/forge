"""Tests for forge.config, forge.fdm, forge.slicers, forge.convert, and forge.hub."""

from __future__ import annotations

import builtins
import json
import os
import stat
from pathlib import Path

import pytest
from build123d import Box, export_step

from forge import check as check_mod
from forge import config as config_mod
from forge import convert as convert_mod
from forge import fdm
from forge import hub as hub_mod
from forge.slicers import UnsafeGcode, get_slicer
from forge.slicers.bambu import check_gcode, limits


def test_config_precedence_and_write_hub_config_permissions(tmp_path, monkeypatch):
    user_toml = tmp_path / "user.toml"
    proj_toml = tmp_path / "forge.toml"

    # Defaults when no files exist
    monkeypatch.delenv("FORGE_HUB_URL", raising=False)
    monkeypatch.delenv("FORGE_HUB_TOKEN", raising=False)
    monkeypatch.delenv("FORGE_SLICER", raising=False)
    cfg = config_mod.load_config(user_path=user_toml, project_path=proj_toml)
    assert cfg.hub.url == "http://127.0.0.1:8590"
    assert cfg.slicer.backend == "none"
    assert cfg.printer.build_volume == (256.0, 256.0, 256.0)

    # write_hub_config enforces 0600
    config_mod.write_hub_config("http://192.168.1.50:8590/", "secret-token", path=user_toml)
    assert stat.S_IMODE(os.stat(user_toml).st_mode) == 0o600
    cfg2 = config_mod.load_config(user_path=user_toml, project_path=proj_toml)
    assert cfg2.hub.url == "http://192.168.1.50:8590"
    assert cfg2.hub.token == "secret-token"

    # Project forge.toml overrides printer/slicer, NEVER hub secrets
    proj_toml.write_text(
        '[hub]\ntoken = "evil"\n[printer]\nbuild_volume = [180, 180, 180]\nnozzle_mm = 0.6\n[slicer]\nbackend = "bambu"\n',
        encoding="utf-8",
    )
    cfg3 = config_mod.load_config(user_path=user_toml, project_path=proj_toml)
    assert cfg3.hub.token == "secret-token"
    assert cfg3.printer.build_volume == (180.0, 180.0, 180.0)
    assert cfg3.printer.nozzle_mm == 0.6
    assert cfg3.slicer.backend == "bambu"

    # Env vars override both
    monkeypatch.setenv("FORGE_HUB_TOKEN", "env-token")
    monkeypatch.setenv("FORGE_SLICER", "none")
    cfg4 = config_mod.load_config(user_path=user_toml, project_path=proj_toml)
    assert cfg4.hub.token == "env-token"
    assert cfg4.slicer.backend == "none"


def test_fdm_current_scales_with_nozzle(tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[printer]\nbuild_volume = [180, 180, 180]\nnozzle_mm = 0.6\nlayer_mm = 0.3\n", encoding="utf-8")
    monkeypatch.setenv("FORGE_CONFIG", str(cfg))
    prof = fdm.current()
    assert prof.build == (180.0, 180.0, 180.0)
    assert prof.nozzle == 0.6
    assert prof.wall_min == 1.8
    assert prof.feature_min == 1.2
    assert prof.floor_min == 1.5


def test_get_slicer_none_and_bambu_gcode_safety():
    assert get_slicer(config_mod.SlicerConfig(backend="none")) is None
    assert get_slicer(config_mod.SlicerConfig(backend="bambu")).name == "bambu"
    with pytest.raises(ValueError, match="Unknown slicer backend"):
        get_slicer(config_mod.SlicerConfig(backend="unknown-slicer"))

    lim = limits({}, {"nozzle_temperature_range_high": ["230"], "textured_plate_temp": ["65"]})
    assert lim == {"nozzle": 230.0, "bed": 65.0}
    check_gcode("M104 S220 ; ok\nM140 S60 ; ok\n", lim)
    with pytest.raises(UnsafeGcode):
        check_gcode("M109 S260\n", lim)
    with pytest.raises(UnsafeGcode):
        check_gcode("M190 S85\n", lim)


def test_convert_gracefully_skips_usdz_without_pxr(tmp_path, monkeypatch):
    export_step(Box(10, 10, 10), str(tmp_path / "part.step"))
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pxr" or name.startswith("pxr."):
            raise ImportError("no pxr")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    outputs = convert_mod.convert(tmp_path)
    assert outputs == [tmp_path / "model.glb"]
    assert (tmp_path / "model.glb").stat().st_size > 0
    assert not (tmp_path / "model.usdz").exists()


def test_hub_push_guards_and_auto_preview_when_no_slicer(tmp_path, monkeypatch):
    monkeypatch.setattr(hub_mod, "OUT_DIR", tmp_path)
    monkeypatch.setattr(check_mod, "OUT_DIR", tmp_path)
    monkeypatch.setenv("FORGE_SLICER", "none")

    proj = tmp_path / "widget"
    proj.mkdir()
    export_step(Box(10, 10, 10), str(proj / "body.step"))
    (proj / "stale.gcode.3mf").write_bytes(b"old-slice")

    # Guard: --fast report refuses push unless --force
    (proj / "report.json").write_text(json.dumps({"ok": True, "exported": False, "partial": False}), encoding="utf-8")
    with pytest.raises(SystemExit, match="--fast"):
        hub_mod.push("widget")

    # Guard: --part report refuses push unless --force
    (proj / "report.json").write_text(json.dumps({"ok": True, "exported": True, "partial": True}), encoding="utf-8")
    with pytest.raises(SystemExit, match="--part"):
        hub_mod.push("widget")

    # Guard: failing check refuses push unless --force
    (proj / "report.json").write_text(
        json.dumps({"ok": False, "exported": True, "partial": False, "problems": ["overlap"]}),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="overlap"):
        hub_mod.push("widget")

    # Valid report + slicer=none -> auto-preview, excludes stale .gcode.3mf, uploads report.json when supported
    (proj / "report.json").write_text(json.dumps({"ok": True, "exported": True, "partial": False}), encoding="utf-8")
    uploaded: dict = {}

    def fake_upload(project, files, note):
        uploaded["project"] = project
        uploaded["names"] = [f.name for f in files]
        uploaded["note"] = note
        return {"project": project, "version": 1, "files": [{"name": f.name} for f in files]}

    monkeypatch.setattr(hub_mod, "upload", fake_upload)
    monkeypatch.setattr(hub_mod, "hub_capabilities", lambda: {"report"})
    monkeypatch.setattr(hub_mod, "convert", lambda folder, color: [folder / "model.glb"])
    (proj / "model.glb").write_bytes(b"glb")

    meta = hub_mod.push("widget", note="v1 preview")
    assert meta["version"] == 1
    assert "stale.gcode.3mf" not in uploaded["names"]
    assert "report.json" in uploaded["names"]
    assert "model.glb" in uploaded["names"]

    # Older Hub without "report" capability skips report.json
    monkeypatch.setattr(hub_mod, "hub_capabilities", lambda: set())
    hub_mod.push("widget", note="v2")
    assert "report.json" not in uploaded["names"]
