"""HTTP client for the Forge Hub (local `forge serve` or always-on Pi/Docker server)."""

from __future__ import annotations

import json
import mimetypes
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from forge.check import OUT_DIR
from forge.config import load_config
from forge.convert import convert
from forge.slicers import get_slicer

UPLOAD_EXT = {".step", ".stp", ".stl", ".3mf", ".png", ".glb", ".usdz"}


def _hub_creds() -> tuple[str, str]:
    cfg = load_config().hub
    if not cfg.url or not cfg.token:
        sys.exit(
            "Hub credentials not configured. Run `forge serve` to start a local Hub "
            "(which writes ~/.config/forge/config.toml), or set FORGE_HUB_URL and FORGE_HUB_TOKEN."
        )
    return cfg.url.rstrip("/"), cfg.token


def _request(method: str, path: str, body: bytes | None = None, ctype: str | None = None):
    url, token = _hub_creds()
    req = urllib.request.Request(url + path, data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if ctype:
        req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"Hub error {e.code}: {e.read().decode(errors='replace')}")
    except urllib.error.URLError as e:
        sys.exit(f"Could not reach Hub ({url}): {e.reason}")


def hub_capabilities() -> set[str]:
    """Query Hub /capabilities; return empty set on older hubs or connection failures."""
    cfg = load_config().hub
    if not cfg.url or not cfg.token:
        return set()
    req = urllib.request.Request(cfg.url.rstrip("/") + "/capabilities", method="GET")
    req.add_header("Authorization", f"Bearer {cfg.token}")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
            return set(data.get("capabilities") or ())
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError, TimeoutError):
        return set()


def upload(project: str, files: list[Path], note: str = "") -> dict:
    boundary = uuid.uuid4().hex
    parts = []
    for f in files:
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="files"; '
            f'filename="{f.name}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
            + f.read_bytes()
            + b"\r\n"
        )
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="note"\r\n\r\n'.encode()
        + note.encode()
        + b"\r\n"
    )
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    return _request(
        "POST", f"/projects/{project}/versions", body, f"multipart/form-data; boundary={boundary}"
    )


def _check_report(folder: Path, *, force: bool = False) -> dict | None:
    path = folder / "report.json"
    if not path.is_file():
        return None
    try:
        rep = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    if not force:
        if rep.get("exported") is False:
            sys.exit("Last run used --fast (no STEP/STL exported); run a full `forge run` before pushing.")
        if rep.get("partial") is True:
            sys.exit("Last run was filtered with --part; run `forge run` with all parts before pushing.")
        if rep.get("ok") is False:
            problems = "; ".join(rep.get("problems") or []) or "check failed"
            sys.exit(f"Check failed ({problems}); fix and re-run `forge run` (or pass --force).")
    return rep


def push(
    name: str,
    note: str = "",
    color: str | None = None,
    plate: str | None = None,
    *,
    preview: bool = False,
    force: bool = False,
) -> dict:
    """Convert STEP outputs to GLB/(USDZ), optionally slice, and upload a new Hub version.

    When `preview=True` or no slicer is configured (`slicer.backend = "none"`), slicing is
    skipped automatically and stale `.gcode.3mf` files are excluded.
    """
    folder = OUT_DIR / name
    if not folder.is_dir():
        sys.exit(f"{folder} does not exist; run `forge run` first.")
    _check_report(folder, force=force)
    convert(folder, color)

    slicer = None if preview else get_slicer()
    sliced_label = ""
    if slicer is not None:
        slicer.slice_project(name, plate)
        use_plate = plate or load_config().slicer.default_plate
        sliced_label = slicer.plates().get(use_plate, use_plate)
    else:
        preview = True

    files = sorted(
        p for p in folder.glob("*")
        if p.suffix.lower() in UPLOAD_EXT
        and not (preview and p.name.endswith(".gcode.3mf"))
    )
    caps = hub_capabilities()
    report_path = folder / "report.json"
    if report_path.is_file() and "report" in caps:
        files.append(report_path)
    asm_path = folder / "assembly.json"
    if asm_path.is_file() and "assembly" in caps:
        files.append(asm_path)
    if not files:
        sys.exit(f"No uploadable files found in {folder}; run `forge run` first.")

    meta = upload(name.lower(), files, note)
    if preview:
        print(f"Uploaded (preview): {meta['project']} v{meta['version']} ({len(meta['files'])} files, unsliced)")
    else:
        print(f"Uploaded: {meta['project']} v{meta['version']} ({len(meta['files'])} files, {sliced_label})")
    return meta


def list_projects(project: str | None = None) -> None:
    if project:
        for m in _request("GET", f"/projects/{project}/versions"):
            files = ", ".join(f["name"] for f in m["files"])
            print(f"v{m['version']}  {m['created_at']}  {m['note'] or '-'}  [{files}]")
    else:
        for p in _request("GET", "/projects"):
            print(f"{p['name']}: latest v{p['latest']} ({p['versions']} versions)")
