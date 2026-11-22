"""Tests for forge.check: report.json, --fast, --part, --json, build-volume checks, and compact renders."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest
from build123d import Box, Pos

from forge import check as check_mod


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_full_check_writes_outputs_and_compact_render(tmp_path, monkeypatch):
    monkeypatch.setattr(check_mod, "OUT_DIR", tmp_path)
    monkeypatch.delenv("FORGE_FAST", raising=False)
    monkeypatch.delenv("FORGE_RENDER", raising=False)
    monkeypatch.delenv("FORGE_PART", raising=False)
    monkeypatch.delenv("FORGE_JSON", raising=False)

    params_file = tmp_path / "params.py"
    params_file.write_text("W = 20\n", encoding="utf-8")

    rep = check_mod.check(
        {"body": Box(20, 15, 10), "lid": Pos(30, 0, 0) * Box(20, 15, 4)},
        name="demo",
        params_file=params_file,
        assumptions=["PLA matte"],
    )
    assert rep.ok
    assert rep.exported is True
    assert rep.rendered is True
    assert rep.partial is False
    assert rep.params_hash is not None and len(rep.params_hash) == 12

    out = tmp_path / "demo"
    for fname in ("body.step", "body.stl", "lid.step", "lid.stl", "assembly.step", "render.png", "report.json"):
        assert (out / fname).is_file(), f"missing {fname}"

    w, h = _png_size(out / "render.png")
    assert (w, h) == (768, 640)

    data = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert data["schema"] == 1
    assert data["ok"] is True
    assert data["exported"] is True
    assert data["assumptions"] == ["PLA matte"]
    assert set(data["parts"]) == {"body", "lid"}


def test_fast_mode_skips_export_and_omits_render_line(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(check_mod, "OUT_DIR", tmp_path)
    monkeypatch.setenv("FORGE_FAST", "1")
    monkeypatch.delenv("FORGE_RENDER", raising=False)

    # Pre-seed a stale render.png; fast mode must NOT claim it rendered it.
    out = tmp_path / "fastdemo"
    out.mkdir()
    (out / "render.png").write_bytes(b"stale")

    rep = check_mod.check({"box": Box(10, 10, 10)}, name="fastdemo")
    stdout = capsys.readouterr().out
    assert rep.ok
    assert rep.fast is True
    assert rep.exported is False
    assert rep.rendered is False
    assert "render:" not in stdout
    assert not (out / "box.step").exists()
    assert not (out / "box.stl").exists()
    assert (out / "report.json").is_file()


def test_part_filter_and_unknown_part_warning(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(check_mod, "OUT_DIR", tmp_path)
    monkeypatch.setenv("FORGE_FAST", "1")
    monkeypatch.setenv("FORGE_PART", "lid")

    parts = {"body": Box(20, 20, 10), "lid": Pos(30, 0, 0) * Box(20, 20, 3)}
    rep = check_mod.check(parts, name="filtered")
    assert rep.partial is True
    assert list(rep.parts) == ["lid"]

    # Unknown part warns on stderr and checks all parts
    capsys.readouterr()
    monkeypatch.setenv("FORGE_PART", "ghost")
    rep2 = check_mod.check(parts, name="filtered")
    err = capsys.readouterr().err
    assert "FORGE_PART='ghost' not found" in err
    assert rep2.partial is False
    assert set(rep2.parts) == {"body", "lid"}


def test_json_output_mode_is_valid_single_line(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(check_mod, "OUT_DIR", tmp_path)
    monkeypatch.setenv("FORGE_FAST", "1")
    monkeypatch.setenv("FORGE_JSON", "1")

    check_mod.check({"box": Box(10, 10, 10)}, name="jsondemo")
    lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["name"] == "jsondemo"
    assert parsed["ok"] is True


def test_interference_and_custom_build_volume_flagged(tmp_path, monkeypatch):
    monkeypatch.setattr(check_mod, "OUT_DIR", tmp_path)
    monkeypatch.setenv("FORGE_FAST", "1")

    # Configure a compact 180 mm printer (e.g. A1 mini)
    cfg = tmp_path / "config.toml"
    cfg.write_text("[printer]\nbuild_volume = [180, 180, 180]\n", encoding="utf-8")
    monkeypatch.setenv("FORGE_CONFIG", str(cfg))

    rep = check_mod.check(
        {"big": Box(200, 10, 10), "overlap": Pos(5, 0, 0) * Box(20, 10, 10)},
        name="bad",
    )
    assert not rep.ok
    assert any("exceeds build volume" in p for p in rep.problems)
    assert any("intersects" in p for p in rep.problems)


def test_full_run_cleans_stale_files(tmp_path, monkeypatch):
    monkeypatch.setattr(check_mod, "OUT_DIR", tmp_path)
    monkeypatch.delenv("FORGE_FAST", raising=False)
    monkeypatch.setenv("FORGE_RENDER", "0")

    out = tmp_path / "clean"
    out.mkdir()
    stale = out / "old_part.stl"
    stale.write_text("stale", encoding="utf-8")
    keep = out / "notes.txt"
    keep.write_text("keep", encoding="utf-8")

    check_mod.check({"fresh": Box(10, 10, 10)}, name="clean")
    assert not stale.exists()
    assert keep.exists()
    assert (out / "fresh.stl").is_file()
