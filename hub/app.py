"""Forge Hub — Lightweight FastAPI version store, offline 3D web preview, and guarded multi-printer bridge.

Runs identically on localhost (`forge serve`), a Raspberry Pi, or Docker (~40 MB RAM).
Must NEVER import `forge`, `build123d`, `OCCT`, or `scipy`.
"""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel

from printers import IDLE_STATES, Printer, PrinterError, Refused, load_hub_config, load_registry
from printers.bambu_lan import inspect_3mf

log = logging.getLogger("uvicorn.error")

HERE = Path(__file__).resolve().parent
STATIC_DIR = (HERE / "static").resolve()

_HUB_CONF = load_hub_config()
_HUB_SECTION = _HUB_CONF.get("hub") or {}

DATA = Path(os.environ.get("FORGE_DATA") or _HUB_SECTION.get("data_dir") or "/var/lib/forge")
TOKENS = Path(os.environ.get("FORGE_TOKENS") or _HUB_SECTION.get("tokens_file") or "/etc/forge/tokens")
MAX_UPLOAD = int(os.environ.get("FORGE_MAX_UPLOAD", 200 * 1024 * 1024))

ALLOWED_NETS = [
    ipaddress.ip_network(n)
    for n in ("127.0.0.0/8", "::1/128", "192.168.0.0/16", "10.0.0.0/8", "fe80::/10")
]
PROXY_HEADERS = ("cf-connecting-ip", "cf-ray", "x-forwarded-for", "forwarded", "x-real-ip")
PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ALLOWED_EXT = {".step", ".stp", ".stl", ".3mf", ".png", ".glb", ".usdz", ".py"}
ALLOWED_EXACT = {"report.json", "assembly.json"}
CAPABILITIES = ["report", "multi_printer", "assembly", "revisions"]

OWNER = os.environ.get("FORGE_OWNER_ROLE") or str(_HUB_SECTION.get("owner_role") or "owner")
TRUSTED = {OWNER, "appletv"}
VIEWER = "web"  # read-only everywhere; only token accepted on remote preview
CODE_TRIES = 3

REMOTE_PEER = (os.environ.get("FORGE_REMOTE_PEER") or str(_HUB_SECTION.get("remote_peer") or "")).strip()
_P, _V = r"[a-z0-9][a-z0-9_-]{0,63}", r"(?:latest|v?\d+)"
REMOTE_ROUTES = [
    re.compile(p)
    for p in (
        r"/",
        r"/preview",
        r"/static/[A-Za-z0-9._/-]+\.js",
        r"/events",
        r"/me",
        r"/printer",
        r"/printers",
        r"/projects",
        rf"/projects/{_P}/versions/{_V}",
        rf"/projects/{_P}/versions/{_V}/summary",
        rf"/projects/{_P}/versions/{_V}/report",
        rf"/projects/{_P}/versions/{_V}/files/model\.glb",
        rf"/projects/{_P}/versions/{_V}/files/assembly\.json",
    )
]

REGISTRY = load_registry(DATA, _HUB_CONF)

app = FastAPI(title="Forge Hub", docs_url=None, redoc_url=None, openapi_url=None)

SUBSCRIBERS: set[asyncio.Queue] = set()
ACTIVE_SESSIONS: dict[str, int] = {}
SSE_PING = 15


def publish(event: dict) -> None:
    data = json.dumps(event, ensure_ascii=False)
    for q in list(SUBSCRIBERS):
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            pass


@app.middleware("http")
async def lan_only(request: Request, call_next):
    host = request.client.host if request.client else ""
    request.state.remote = bool(REMOTE_PEER) and host == REMOTE_PEER
    if request.state.remote:
        if (
            request.method != "GET"
            or not any(r.fullmatch(request.url.path) for r in REMOTE_ROUTES)
            or not request.headers.get("x-forwarded-email")
        ):
            return JSONResponse({"detail": "Remote access is read-only preview"}, status_code=403)
        return await call_next(request)
    try:
        ip = ipaddress.ip_address(host)
        if ip.version == 6 and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        allowed = any(ip in net for net in ALLOWED_NETS)
    except ValueError:
        allowed = False
    if not allowed or any(h in request.headers for h in PROXY_HEADERS):
        return JSONResponse({"detail": "LAN access only"}, status_code=403)
    return await call_next(request)


def load_tokens() -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    if TOKENS.exists():
        for line in TOKENS.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and ":" in line:
                name, tok = line.split(":", 1)
                if tok.strip():
                    tokens.append((name.strip(), tok.strip()))
    return tokens


def auth(request: Request) -> str:
    header = request.headers.get("authorization", "")
    given = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if given:
        for name, tok in load_tokens():
            if hmac.compare_digest(given.encode(), tok.encode()):
                if getattr(request.state, "remote", False) and name != VIEWER:
                    raise HTTPException(403, "Only the read-only 'web' token is accepted remotely")
                return name
    if getattr(request.state, "remote", False):
        log.warning(
            "remote 401: %s (%s)",
            "invalid token" if given else "missing Authorization",
            request.url.path,
        )
    raise HTTPException(401, "Invalid token", headers={"WWW-Authenticate": "Bearer"})


def writer(who: str = Depends(auth)) -> str:
    if who == VIEWER:
        raise HTTPException(403, "The 'web' token is read-only")
    return who


def trusted(who: str = Depends(auth)) -> str:
    if who not in TRUSTED:
        raise HTTPException(403, "Print codes are visible only to the owner and Apple TV")
    return who


def project_dir(project: str) -> Path:
    if not PROJECT_RE.match(project):
        raise HTTPException(400, "Project name must be lowercase ASCII, digits, '-' or '_' (max 64)")
    return DATA / "models" / project


def versions(pdir: Path) -> list[int]:
    if not pdir.is_dir():
        return []
    return sorted(int(d.name[1:]) for d in pdir.iterdir() if re.fullmatch(r"v\d+", d.name))


def version_dir(project: str, version: str) -> Path:
    pdir = project_dir(project)
    vs = versions(pdir)
    if version == "latest":
        if not vs:
            raise HTTPException(404, "No versions found")
        n = vs[-1]
    else:
        m = re.fullmatch(r"v?(\d+)", version)
        if not m or int(m.group(1)) not in vs:
            raise HTTPException(404, "Version not found")
        n = int(m.group(1))
    return pdir / f"v{n}"


def read_meta(vdir: Path) -> dict:
    return json.loads((vdir / "meta.json").read_text(encoding="utf-8"))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def index():
    return RedirectResponse("/preview")


@app.get("/preview")
def preview():
    return FileResponse(HERE / "preview.html", media_type="text/html")


@app.get("/static/{asset_path:path}")
def static_asset(asset_path: str):
    """Serve locally bundled Three.js assets (100% offline LAN preview)."""
    target = (STATIC_DIR / asset_path).resolve()
    if not str(target).startswith(str(STATIC_DIR) + os.sep) or not target.is_file():
        raise HTTPException(404, "Static asset not found")
    media = "application/javascript" if target.suffix == ".js" else "application/octet-stream"
    return FileResponse(target, media_type=media)


@app.get("/me")
def me(request: Request, who: str = Depends(auth)):
    return {"name": who, "remote": request.state.remote, "can_print": who != VIEWER}


@app.get("/capabilities")
def capabilities(_: str = Depends(auth)):
    return {"capabilities": CAPABILITIES}


@app.get("/events")
async def events(
    request: Request,
    role: str | None = None,
    project: str | None = None,
    who: str = Depends(auth),
):
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    SUBSCRIBERS.add(q)
    session_proj: str | None = None
    if role == "session" and project and PROJECT_RE.match(project) and who != VIEWER:
        session_proj = project
        ACTIVE_SESSIONS[session_proj] = ACTIVE_SESSIONS.get(session_proj, 0) + 1
        publish({"type": "session", "project": session_proj, "connected": True})

    async def stream():
        try:
            yield ": connected\n\n"
            while not await request.is_disconnected():
                try:
                    data = await asyncio.wait_for(q.get(), timeout=SSE_PING)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            SUBSCRIBERS.discard(q)
            if session_proj is not None:
                rem = max(0, ACTIVE_SESSIONS.get(session_proj, 1) - 1)
                if rem == 0:
                    ACTIVE_SESSIONS.pop(session_proj, None)
                else:
                    ACTIVE_SESSIONS[session_proj] = rem
                publish({"type": "session", "project": session_proj, "connected": rem > 0})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/projects")
def list_projects(_: str = Depends(auth)):
    root = DATA / "models"
    out = []
    if root.is_dir():
        for p in sorted(root.iterdir()):
            vs = versions(p)
            if vs:
                out.append({"name": p.name, "latest": vs[-1], "versions": len(vs)})
    return out


@app.get("/projects/{project}/versions")
def list_versions(project: str, _: str = Depends(auth)):
    pdir = project_dir(project)
    return [read_meta(pdir / f"v{n}") for n in versions(pdir)]


@app.post("/projects/{project}/versions", status_code=201)
async def upload(
    project: str,
    files: list[UploadFile] = File(...),
    note: str = Form(""),
    who: str = Depends(writer),
):
    pdir = project_dir(project)
    names = [f.filename or "" for f in files]
    for name in names:
        ok_name = FILE_RE.match(name) and (
            Path(name).suffix.lower() in ALLOWED_EXT or name in ALLOWED_EXACT
        )
        if not ok_name:
            raise HTTPException(400, f"Disallowed file: {name!r}")
    if len(set(names)) != len(names):
        raise HTTPException(400, "Duplicate filename in upload")

    pdir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".upload-", dir=pdir))
    try:
        total = 0
        entries = []
        for f in files:
            h = hashlib.sha256()
            size = 0
            with open(tmp / f.filename, "wb") as out:
                while chunk := await f.read(1024 * 1024):
                    size += len(chunk)
                    total += len(chunk)
                    if total > MAX_UPLOAD:
                        raise HTTPException(413, "Upload exceeds size limit")
                    h.update(chunk)
                    out.write(chunk)
            entries.append({"name": f.filename, "size": size, "sha256": h.hexdigest()})

        with open(pdir / ".lock", "w", encoding="utf-8") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            n = (versions(pdir) or [0])[-1] + 1
            meta = {
                "project": project,
                "version": n,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "note": note,
                "uploaded_by": who,
                "files": entries,
            }
            (tmp / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.rename(pdir / f"v{n}")
        publish({"type": "version", "project": project, "version": n, "note": note})
        return meta
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)


@app.get("/projects/{project}/versions/{version}")
def get_version(project: str, version: str, _: str = Depends(auth)):
    return read_meta(version_dir(project, version))


@app.get("/projects/{project}/versions/{version}/files/{name}")
def get_file(project: str, version: str, name: str, _: str = Depends(auth)):
    vdir = version_dir(project, version)
    listed = {f["name"] for f in read_meta(vdir)["files"]}
    if name not in listed or not (vdir / name).is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(vdir / name, filename=name)


@app.get("/projects/{project}/versions/{version}/report")
def get_report(project: str, version: str, _: str = Depends(auth)):
    vdir = version_dir(project, version)
    listed = {f["name"] for f in read_meta(vdir)["files"]}
    path = vdir / "report.json"
    if "report.json" not in listed or not path.is_file():
        raise HTTPException(404, "No report.json for this version")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise HTTPException(422, f"Corrupt report.json: {e}") from e


# --- Multi-printer & guarded print dispatch ---

def sliced_file(vdir: Path) -> Path:
    names = [f["name"] for f in read_meta(vdir)["files"] if f["name"].endswith(".gcode.3mf")]
    if len(names) != 1:
        raise HTTPException(409, "No sliced .gcode.3mf file in this version")
    return vdir / names[0]


def code_file(vdir: Path) -> Path:
    d = DATA / "print-codes"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{vdir.parent.name}-{vdir.name}.json"


def new_code(vdir: Path) -> str:
    code = f"{secrets.randbelow(10**6):06d}"
    code_file(vdir).write_text(json.dumps({"code": code, "fails": 0}), encoding="utf-8")
    return code


def read_code(vdir: Path) -> dict:
    f = code_file(vdir)
    if not f.exists():
        new_code(vdir)
    return json.loads(f.read_text(encoding="utf-8"))


def _resolve_target_printer(printer_id: str | None) -> Printer:
    if len(REGISTRY) == 0:
        raise HTTPException(409, "No printers configured on Hub")
    if printer_id is None:
        if len(REGISTRY) > 1:
            raise HTTPException(
                400,
                f"Multiple printers configured ({', '.join(REGISTRY.ids())}); specify printer_id",
            )
        p = REGISTRY.get()
    else:
        p = REGISTRY.get(printer_id)
    if p is None:
        raise HTTPException(404, f"Unknown printer_id: {printer_id!r}")
    return p


def _print_info(vdir: Path, printer: Printer | None = None) -> dict:
    path = sliced_file(vdir)
    try:
        if printer is not None:
            info = printer.check_file(path)
        else:
            info = inspect_3mf(path)
            info.pop("gcode", None)
    except Refused as e:
        raise HTTPException(422, f"Sliced file refused: {e}") from e
    return {
        "file": path.name,
        "minutes": round(info.get("prediction", 0) / 60),
        "grams": info.get("weight"),
        "bed_type": info.get("bed_type"),
        "printer_model": info.get("printer_model"),
        "nozzle": info.get("nozzle"),
    }


def _require_idle(printer: Printer) -> None:
    try:
        status = printer.read_status(timeout=8.0)
    except PrinterError as e:
        raise HTTPException(503, f"Printer {printer.id!r} unreachable: {e}") from e
    if "error" in status:
        raise HTTPException(503, f"Printer {printer.id!r} unreachable: {status['error']}")
    state = status.get("gcode_state")
    if state not in IDLE_STATES:
        raise HTTPException(409, f"Printer {printer.id!r} is busy ({state})")


@app.get("/printers")
def list_printers(_: str = Depends(auth)):
    return REGISTRY.status_all(ttl=5.0, timeout=5.0)


@app.get("/printer")
def default_printer_status(_: str = Depends(auth)):
    p = REGISTRY.get()
    if p is None:
        return {"error": "No printers configured"}
    return REGISTRY.status_one(p, ttl=5.0, timeout=5.0)


@app.get("/projects/{project}/versions/{version}/summary")
def get_summary(project: str, version: str, _: str = Depends(auth)):
    vdir = version_dir(project, version)
    try:
        info = _print_info(vdir, printer=None)
        return {**info, "printable": True}
    except HTTPException as e:
        if e.status_code in (409, 422):
            return {"printable": False, "reason": e.detail}
        raise


class PrintBody(BaseModel):
    code: str | None = None
    printer_id: str | None = None


@app.get("/projects/{project}/versions/{version}/print")
def get_print(
    project: str,
    version: str,
    printer_id: str | None = None,
    _: str = Depends(trusted),
):
    vdir = version_dir(project, version)
    if printer_id is not None:
        target = REGISTRY.get(printer_id)
        if target is None:
            raise HTTPException(404, f"Unknown printer_id: {printer_id!r}")
    else:
        target = REGISTRY.get() if len(REGISTRY) == 1 else None
    return {**_print_info(vdir, printer=target), "code": read_code(vdir)["code"]}


@app.post("/projects/{project}/versions/{version}/print")
def post_print(
    project: str,
    version: str,
    body: PrintBody | None = Body(default=None),
    who: str = Depends(writer),
):
    code = body.code if body else None
    printer_id = body.printer_id if body else None
    vdir = version_dir(project, version)
    path = sliced_file(vdir)
    target = _resolve_target_printer(printer_id)
    if not target.lock.acquire(blocking=False):
        raise HTTPException(409, f"Another print request is already in progress on {target.id!r}")
    try:
        REGISTRY.invalidate(target.id)
        _require_idle(target)
        # Validate target model/nozzle/temperature caps before consuming the print code
        try:
            target.check_file(path)
        except Refused as e:
            raise HTTPException(422, f"Sliced file refused: {e}") from e

        if who not in TRUSTED:
            stored = read_code(vdir)
            if not code or not hmac.compare_digest(code.encode(), stored["code"].encode()):
                stored["fails"] += 1
                if stored["fails"] >= CODE_TRIES:
                    new_code(vdir)
                else:
                    code_file(vdir).write_text(json.dumps(stored), encoding="utf-8")
                raise HTTPException(403, "Invalid or missing print code")

        meta = read_meta(vdir)
        remote = f"forge_{meta['project']}_v{meta['version']}.gcode.3mf"
        title = f"{meta['project']} v{meta['version']}"
        try:
            info = target.start_print(path, remote, title)
        except Refused as e:
            raise HTTPException(422, f"Sliced file refused: {e}") from e
        except PrinterError as e:
            raise HTTPException(503, str(e)) from e

        new_code(vdir)
        entry = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "project": meta["project"],
            "version": meta["version"],
            "printer_id": target.id,
            "by": who,
        }
        with open(DATA / "print-log.jsonl", "a", encoding="utf-8") as logf:
            logf.write(json.dumps(entry, ensure_ascii=False) + "\n")
        publish({"type": "print", **entry})
        return {"started": True, **entry, "minutes": round(info.get("prediction", 0) / 60)}
    finally:
        target.lock.release()


# --- LAN-only revision queue (Apple TV / owner -> active workstation chat session) ---

MAX_REVISIONS_PER_PROJECT = 50


def _revisions_file(project: str) -> Path:
    project_dir(project)  # validates PROJECT_RE
    d = DATA / "revisions"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{project}.json"


def _read_revisions(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except ValueError:
        return []


class RevisionCreateBody(BaseModel):
    prompt: str
    version: int | None = None
    source: str = "appletv"


class RevisionStatusBody(BaseModel):
    status: Literal["queued", "running", "done", "failed"]
    result_version: int | None = None
    note: str = ""


@app.post("/projects/{project}/revisions", status_code=201)
def create_revision(project: str, body: RevisionCreateBody, who: str = Depends(trusted)):
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(400, "Revision prompt must not be empty")
    if len(prompt) > 2000:
        raise HTTPException(400, "Revision prompt too long (max 2000 chars)")
    path = _revisions_file(project)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    entry = {
        "id": secrets.token_hex(6),
        "project": project,
        "version": body.version,
        "prompt": prompt,
        "source": body.source[:32],
        "by": who,
        "status": "queued",
        "created_at": now,
        "updated_at": now,
        "result_version": None,
        "note": "",
    }
    with open(path.with_suffix(".lock"), "w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        items = _read_revisions(path)
        items.insert(0, entry)
        items = items[:MAX_REVISIONS_PER_PROJECT]
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    publish({"type": "revision", "revision": entry})
    return {**entry, "session_connected": ACTIVE_SESSIONS.get(project, 0) > 0}


@app.get("/projects/{project}/revisions")
def list_revisions(project: str, _: str = Depends(writer)):
    path = _revisions_file(project)
    return {
        "project": project,
        "session_connected": ACTIVE_SESSIONS.get(project, 0) > 0,
        "revisions": _read_revisions(path),
    }


@app.post("/projects/{project}/revisions/{rev_id}/status")
def update_revision_status(
    project: str,
    rev_id: str,
    body: RevisionStatusBody,
    _: str = Depends(writer),
):
    path = _revisions_file(project)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    updated = None
    with open(path.with_suffix(".lock"), "w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        items = _read_revisions(path)
        for item in items:
            if item.get("id") == rev_id:
                item["status"] = body.status
                item["updated_at"] = now
                if body.result_version is not None:
                    item["result_version"] = body.result_version
                if body.note:
                    item["note"] = body.note[:500]
                updated = item
                break
        if updated is None:
            raise HTTPException(404, f"Revision not found: {rev_id!r}")
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    publish({"type": "revision_status", "revision": updated})
    return updated
