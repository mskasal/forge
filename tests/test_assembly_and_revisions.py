"""Tests for forge.assembly (`assembly.json`, GLB node matching) and forge.revisions."""

from __future__ import annotations

import io
import json
import struct
from pathlib import Path

from build123d import Box, Pos, export_step

from forge import assembly, convert, revisions


def _glb_node_names(glb_path: Path) -> set[str]:
    data = glb_path.read_bytes()
    chunk_len = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20 : 20 + chunk_len])
    return {n["name"] for n in gltf.get("nodes", []) if "name" in n}


def test_auto_assembly_and_glb_node_name_matching(tmp_path):
    body = Box(40, 30, 15)
    lid = Pos(0, 0, 16) * Box(40, 30, 4)
    export_step(body, str(tmp_path / "body.step"))
    export_step(lid, str(tmp_path / "lid.step"))

    out = convert.convert(tmp_path)
    names = {p.name for p in out}
    assert "model.glb" in names
    assert "assembly.json" in names

    spec = json.loads((tmp_path / "assembly.json").read_text(encoding="utf-8"))
    assert spec["version"] == 1
    assert spec["up_axis"] == "Z"
    assert [s["part"] for s in spec["steps"]] == ["body", "lid"]

    # Bottom part stays anchored, upper part lifts along +Z
    assert spec["steps"][0]["slide_mm"] == [0.0, 0.0, 0.0]
    assert spec["steps"][1]["slide_mm"][2] > 0

    # Both parts have plate transforms placing them on Z=0
    for step in spec["steps"]:
        assert "plate" in step
        assert len(step["plate"]["translate_mm"]) == 3
        assert len(step["plate"]["rot_deg"]) == 3

    # Every assembly step part name must exist as a named node inside model.glb
    glb_nodes = _glb_node_names(tmp_path / "model.glb")
    for step in spec["steps"]:
        assert step["part"] in glb_nodes


def test_explicit_write_assembly_preserves_custom_hinge_and_fills_plate(tmp_path):
    body = Box(50, 40, 20)
    lid = Pos(0, 0, 22) * Box(50, 40, 4)
    path = assembly.write_assembly(
        tmp_path,
        [
            assembly.AssemblyStep(part="body", step=1, label="Main body"),
            assembly.AssemblyStep(
                part="lid",
                step=2,
                label="Hinged lid",
                rotate_deg=(0.0, -90.0, 0.0),
                pivot_mm=(-25.0, 0.0, 20.0),
            ),
        ],
        parts={"body": body, "lid": lid},
        plate_rotations={"lid": (180.0, 0.0, 0.0)},
    )
    spec = json.loads(path.read_text(encoding="utf-8"))
    assert spec["steps"][1]["rotate_deg"] == [0.0, -90.0, 0.0]
    assert spec["steps"][1]["pivot_mm"] == [-25.0, 0.0, 20.0]
    assert spec["steps"][1]["plate"]["rot_deg"] == [180.0, 0.0, 0.0]

    # ensure_assembly must preserve author-written assembly.json
    kept = assembly.ensure_assembly(tmp_path, [("body", body), ("lid", lid)])
    assert kept == path
    assert json.loads(kept.read_text(encoding="utf-8"))["steps"][1]["label"] == "Hinged lid"


def test_wait_revision_claims_oldest_queued_item(monkeypatch):
    calls: list[tuple[str, str, dict | None]] = []

    def fake_request(method: str, path: str, body=None, ctype=None):
        payload = json.loads(body.decode()) if body else None
        calls.append((method, path, payload))
        if method == "GET" and path == "/projects/case/revisions":
            return {
                "project": "case",
                "session_connected": False,
                "revisions": [
                    {"id": "rev2", "project": "case", "prompt": "newer", "status": "queued"},
                    {"id": "rev1", "project": "case", "prompt": "older", "status": "queued"},
                ],
            }
        if method == "POST" and path == "/projects/case/revisions/rev1/status":
            return {"id": "rev1", "project": "case", "prompt": "older", "status": "running"}
        raise AssertionError(f"Unexpected call: {method} {path}")

    monkeypatch.setattr(revisions.hub, "_request", fake_request)
    rev = revisions.wait_revision("Case")
    assert rev["id"] == "rev1"
    assert rev["status"] == "running"
    assert calls[-1][2] == {"status": "running", "note": ""}


def test_wait_revision_receives_live_sse_event(monkeypatch):
    def fake_request(method: str, path: str, body=None, ctype=None):
        if method == "GET":
            return {"project": "case", "session_connected": False, "revisions": []}
        if method == "POST" and path == "/projects/case/revisions/abc123/status":
            return {"id": "abc123", "project": "case", "prompt": "thicker lid", "status": "running"}
        raise AssertionError(f"Unexpected call: {method} {path}")

    sse_payload = (
        b": connected\n\n"
        b'data: {"type": "revision", "revision": {"id": "abc123", "project": "case", "prompt": "thicker lid"}}\n\n'
    )

    class FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(revisions.hub, "_request", fake_request)
    monkeypatch.setattr(revisions.hub, "_hub_creds", lambda: ("http://127.0.0.1:8590", "tok"))
    monkeypatch.setattr(revisions.urllib.request, "urlopen", lambda req, timeout=None: FakeResp(sse_payload))

    rev = revisions.wait_revision("case", timeout=5.0)
    assert rev["id"] == "abc123"
    assert rev["prompt"] == "thicker lid"
