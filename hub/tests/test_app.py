"""Tests for Forge Hub FastAPI endpoints, static Three.js serving, LAN-only and remote read-only guards."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HUB_DIR = Path(__file__).resolve().parents[1]
if str(HUB_DIR) not in sys.path:
    sys.path.insert(0, str(HUB_DIR))


@pytest.fixture
def hub_client(tmp_path, monkeypatch):
    tokens = tmp_path / "tokens"
    tokens.write_text("owner:tok-owner\nappletv:tok-tv\nagent:tok-agent\nweb:tok-web\n", encoding="utf-8")
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("FORGE_TOKENS", str(tokens))
    monkeypatch.delenv("FORGE_HUB_CONFIG", raising=False)
    monkeypatch.delenv("FORGE_REMOTE_PEER", raising=False)

    import app as hub_app

    hub_app = importlib.reload(hub_app)
    client = TestClient(hub_app.app, client=("127.0.0.1", 50000))
    return hub_app, client


def _auth(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


def test_health_auth_capabilities_and_offline_static_assets(hub_client):
    _, client = hub_client
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/projects").status_code == 401
    assert client.get("/projects", headers=_auth("wrong")).status_code == 401

    caps = client.get("/capabilities", headers=_auth("tok-owner"))
    assert caps.status_code == 200
    assert set(caps.json()["capabilities"]) >= {"report", "multi_printer", "assembly", "revisions"}

    # Vendored Three.js assets served offline, path traversal blocked
    r_three = client.get("/static/three.module.min.js")
    assert r_three.status_code == 200
    assert "javascript" in r_three.headers["content-type"]

    r_utils = client.get("/static/addons/utils/BufferGeometryUtils.js")
    assert r_utils.status_code == 200

    assert client.get("/static/../app.py").status_code == 404
    assert client.get("/static/missing.js").status_code == 404


def test_upload_report_json_allowed_and_arbitrary_json_blocked(hub_client):
    _, client = hub_client

    # Arbitrary .json and meta.json must be rejected
    for bad in ("meta.json", "evil.json", "script.sh"):
        r = client.post(
            "/projects/demo/versions",
            headers=_auth("tok-owner"),
            files=[("files", (bad, b"{}", "application/json"))],
            data={"note": "bad"},
        )
        assert r.status_code == 400, f"expected 400 for {bad}"

    # Web token is read-only even on LAN
    r_ro = client.post(
        "/projects/demo/versions",
        headers=_auth("tok-web"),
        files=[("files", ("model.glb", b"glb", "model/gltf-binary"))],
        data={"note": "blocked"},
    )
    assert r_ro.status_code == 403

    # Valid upload including model.glb and report.json succeeds
    rep = {"schema": 1, "name": "demo", "ok": True, "parts": {"body": {"size_mm": [20, 20, 10]}}}
    r_ok = client.post(
        "/projects/demo/versions",
        headers=_auth("tok-owner"),
        files=[
            ("files", ("model.glb", b"fake-glb", "model/gltf-binary")),
            ("files", ("report.json", json.dumps(rep).encode(), "application/json")),
        ],
        data={"note": "v1"},
    )
    assert r_ok.status_code == 201
    meta = r_ok.json()
    assert meta["version"] == 1
    assert {f["name"] for f in meta["files"]} == {"model.glb", "report.json"}

    r_rep = client.get("/projects/demo/versions/latest/report", headers=_auth("tok-web"))
    assert r_rep.status_code == 200
    assert r_rep.json()["name"] == "demo"

    r_glb = client.get("/projects/demo/versions/v1/files/model.glb", headers=_auth("tok-web"))
    assert r_glb.status_code == 200
    assert r_glb.content == b"fake-glb"


def test_lan_only_blocks_proxy_headers_and_non_lan_ips(hub_client):
    hub_app, client = hub_client
    r_proxy = client.get("/health", headers={"X-Forwarded-For": "1.2.3.4"})
    assert r_proxy.status_code == 403

    wan_client = TestClient(hub_app.app, client=("8.8.8.8", 50000))
    assert wan_client.get("/health").status_code == 403


def test_remote_read_only_enforces_web_token_identity_and_route_allowlist(tmp_path, monkeypatch):
    tokens = tmp_path / "tokens"
    tokens.write_text("owner:tok-owner\nweb:tok-web\n", encoding="utf-8")
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("FORGE_TOKENS", str(tokens))
    monkeypatch.setenv("FORGE_REMOTE_PEER", "172.20.0.5")

    import app as hub_app

    hub_app = importlib.reload(hub_app)

    # Upload a version locally first
    lan = TestClient(hub_app.app, client=("127.0.0.1", 50000))
    assert lan.post(
        "/projects/case/versions",
        headers=_auth("tok-owner"),
        files=[
            ("files", ("model.glb", b"glbdata", "model/gltf-binary")),
            ("files", ("part.step", b"ISO-10303-21;", "application/octet-stream")),
            ("files", ("report.json", b'{"ok": true}', "application/json")),
            ("files", ("assembly.json", b'{"version": 1, "steps": []}', "application/json")),
        ],
        data={"note": "v1"},
    ).status_code == 201

    remote = TestClient(hub_app.app, client=("172.20.0.5", 44321))
    email_hdr = {"X-Forwarded-Email": "user@example.com"}

    # Missing X-Forwarded-Email -> 403 even on /preview
    assert remote.get("/preview").status_code == 403

    # Allowed remote read-only routes with web token + X-Forwarded-Email
    assert remote.get("/preview", headers=email_hdr).status_code == 200
    assert remote.get("/static/three.module.min.js", headers=email_hdr).status_code == 200
    assert remote.get("/projects", headers={**email_hdr, **_auth("tok-web")}).status_code == 200
    assert remote.get("/printers", headers={**email_hdr, **_auth("tok-web")}).status_code == 200
    assert remote.get("/projects/case/versions/latest/report", headers={**email_hdr, **_auth("tok-web")}).status_code == 200
    assert remote.get("/projects/case/versions/latest/files/model.glb", headers={**email_hdr, **_auth("tok-web")}).status_code == 200
    assert remote.get("/projects/case/versions/v1/files/assembly.json", headers={**email_hdr, **_auth("tok-web")}).status_code == 200

    # Owner token MUST be rejected remotely (403)
    assert remote.get("/projects", headers={**email_hdr, **_auth("tok-owner")}).status_code == 403

    # Non-allowlisted files (STEP), print codes, revisions, and all POSTs MUST be rejected remotely (403)
    assert remote.get("/projects/case/versions/latest/files/part.step", headers={**email_hdr, **_auth("tok-web")}).status_code == 403
    assert remote.get("/projects/case/versions/latest/print", headers={**email_hdr, **_auth("tok-web")}).status_code == 403
    assert remote.post("/projects/case/versions/latest/print", headers={**email_hdr, **_auth("tok-web")}).status_code == 403
    assert remote.post("/projects/case/versions", headers={**email_hdr, **_auth("tok-web")}).status_code == 403
    assert remote.get("/projects/case/revisions", headers={**email_hdr, **_auth("tok-web")}).status_code == 403
    assert remote.post(
        "/projects/case/revisions",
        headers={**email_hdr, **_auth("tok-owner")},
        json={"prompt": "remote attempt"},
    ).status_code == 403


def test_revisions_queue_lan_permissions_and_lifecycle(hub_client):
    _, client = hub_client

    # web (read-only) and agent cannot submit revisions; only trusted (owner/appletv) can
    assert client.post(
        "/projects/demo/revisions",
        headers=_auth("tok-web"),
        json={"prompt": "nope"},
    ).status_code == 403
    assert client.post(
        "/projects/demo/revisions",
        headers=_auth("tok-agent"),
        json={"prompt": "nope"},
    ).status_code == 403

    # appletv submits a voice-dictated revision
    r_create = client.post(
        "/projects/demo/revisions",
        headers=_auth("tok-tv"),
        json={"prompt": "Make lid 2 mm thicker", "version": 1, "source": "appletv"},
    )
    assert r_create.status_code == 201
    rev = r_create.json()
    assert rev["status"] == "queued"
    assert rev["by"] == "appletv"
    assert rev["session_connected"] is False

    # agent lists queued revisions and marks running -> done
    r_list = client.get("/projects/demo/revisions", headers=_auth("tok-agent"))
    assert r_list.status_code == 200
    assert len(r_list.json()["revisions"]) == 1

    r_run = client.post(
        f"/projects/demo/revisions/{rev['id']}/status",
        headers=_auth("tok-agent"),
        json={"status": "running"},
    )
    assert r_run.status_code == 200
    assert r_run.json()["status"] == "running"

    r_done = client.post(
        f"/projects/demo/revisions/{rev['id']}/status",
        headers=_auth("tok-agent"),
        json={"status": "done", "result_version": 2, "note": "Lid +2 mm"},
    )
    assert r_done.status_code == 200
    assert r_done.json()["status"] == "done"
    assert r_done.json()["result_version"] == 2
