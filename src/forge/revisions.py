"""Session-bound revision loop client (`forge wait-revision` / `forge revision-status`).

Connects an active AI coding-agent chat session on the workstation to the Hub's
LAN-only revision queue (e.g. voice-dictated requests from Apple TV Siri Remote).
Never triggers prints — only receives revision prompts and updates their status.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from forge import hub


def update_status(
    project: str,
    rev_id: str,
    status: str,
    *,
    result_version: int | None = None,
    note: str = "",
) -> dict:
    """Update a revision request's status on the Hub."""
    payload: dict = {"status": status, "note": note}
    if result_version is not None:
        payload["result_version"] = result_version
    return hub._request(
        "POST",
        f"/projects/{project}/revisions/{rev_id}/status",
        json.dumps(payload).encode("utf-8"),
        "application/json",
    )


def _claim_queued(project: str) -> dict | None:
    """Return and claim the oldest queued revision for `project`, if any."""
    data = hub._request("GET", f"/projects/{project}/revisions")
    revs = data.get("revisions") or []
    queued = [r for r in revs if r.get("status") == "queued"]
    if not queued:
        return None
    # Hub returns newest first; claim oldest queued item first.
    target = queued[-1]
    return update_status(project, target["id"], "running")


def wait_revision(project: str, *, timeout: float | None = None) -> dict:
    """Wait for the next revision request for `project` (queued or live SSE) and mark it running."""
    proj = project.lower()
    existing = _claim_queued(proj)
    if existing is not None:
        return existing

    url, token = hub._hub_creds()
    qs = urllib.parse.urlencode({"project": proj, "role": "session"})
    stream_url = f"{url}/events?{qs}"
    deadline = (time.monotonic() + timeout) if timeout is not None else None

    while True:
        remaining = None if deadline is None else max(0.5, deadline - time.monotonic())
        if deadline is not None and time.monotonic() >= deadline:
            sys.exit(f"Timed out waiting for a revision on {proj!r}.")
        req = urllib.request.Request(stream_url, method="GET")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "text/event-stream")
        try:
            with urllib.request.urlopen(req, timeout=remaining or 60) as resp:
                for raw in resp:
                    if deadline is not None and time.monotonic() >= deadline:
                        sys.exit(f"Timed out waiting for a revision on {proj!r}.")
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data: "):
                        continue
                    try:
                        ev = json.loads(line[6:])
                    except ValueError:
                        continue
                    if ev.get("type") != "revision":
                        continue
                    rev = ev.get("revision") or {}
                    if rev.get("project") == proj and rev.get("id"):
                        return update_status(proj, rev["id"], "running")
        except (TimeoutError, urllib.error.URLError):
            if deadline is not None and time.monotonic() >= deadline:
                sys.exit(f"Timed out waiting for a revision on {proj!r}.")
            # Brief reconnect backoff; also re-check queue in case a revision arrived during reconnect
            time.sleep(1.0)
            existing = _claim_queued(proj)
            if existing is not None:
                return existing
        except urllib.error.HTTPError as e:
            sys.exit(f"Hub error {e.code}: {e.read().decode(errors='replace')}")
