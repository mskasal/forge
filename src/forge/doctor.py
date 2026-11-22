"""forge doctor: inspect workstation packages, agent skill links, slicer, and Hub connectivity."""

from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

from forge._paths import CONFIG_FILE, REPO_ROOT, SKILLS_DIR, TEMPLATES_DIR
from forge.config import load_config
from forge.slicers import get_slicer

SKILL_TARGETS = [
    ("Claude", Path.home() / ".claude" / "skills" / "forge"),
    ("Gemini / Antigravity", Path.home() / ".gemini" / "config" / "skills" / "forge"),
    ("Open Agent Skills (.agents)", Path.home() / ".agents" / "skills" / "forge"),
    ("Codex", Path.home() / ".codex" / "skills" / "forge"),
]

problems = 0


def ok(text: str) -> None:
    print(f"  ✓ {text}")


def bad(text: str, fix: str) -> None:
    global problems
    problems += 1
    print(f"  ✗ {text}\n      → {fix}")


def note(text: str) -> None:
    print(f"  · {text}")


def python_and_packages() -> None:
    print("Workstation: Python & packages")
    v = sys.version_info
    if v >= (3, 11):
        ok(f"Python {v.major}.{v.minor}.{v.micro} ({sys.executable})")
    else:
        bad(f"Python {v.major}.{v.minor}", "Install Python 3.11+ and re-run ./install.sh")
    for module, label in [
        ("build123d", "build123d"),
        ("matplotlib", "matplotlib (2x2 render)"),
        ("scipy", "scipy (print_scan)"),
    ]:
        try:
            m = importlib.import_module(module)
            ok(f"{label} {getattr(m, '__version__', '')}".rstrip())
        except ImportError:
            bad(f"{label} missing", f"{REPO_ROOT}/.venv/bin/pip install -e '{REPO_ROOT}[hub,dev]'")
    try:
        importlib.import_module("pxr")
        ok("usd-core (Apple TV USDZ export)")
    except ImportError:
        note("usd-core not installed (optional; needed only for Apple TV USDZ: pip install 'forge-cad[appletv]')")
    from forge.styles import all_styles

    ok(f"design languages: {', '.join(sorted(all_styles()))}")


def commands_and_skills() -> None:
    print("Workstation: CLI & agent skills")
    found = shutil.which("forge")
    expected_cli = (REPO_ROOT / ".venv/bin/forge").resolve()
    if found and (not expected_cli.exists() or Path(found).resolve() == expected_cli):
        ok(f"forge CLI: {found}")
    elif found:
        bad(f"forge points elsewhere: {found}", f"Re-run {REPO_ROOT}/install.sh")
    else:
        bad("forge command not on PATH", f"Run {REPO_ROOT}/install.sh and add ~/.local/bin to PATH")

    expected_skill = SKILLS_DIR.resolve()
    linked, stale, missing_targets = [], [], []
    for label, path in SKILL_TARGETS:
        if (path / "SKILL.md").is_file():
            if path.resolve() == expected_skill:
                linked.append(label)
            else:
                stale.append((label, path))
        else:
            missing_targets.append(label)
    if linked:
        ok(f"skills linked: {', '.join(linked)}")
    for label, path in stale:
        bad(f"{label} skill points elsewhere: {path.resolve()}", f"Re-run {REPO_ROOT}/install.sh")
    if not linked and not stale:
        bad("no agent skill symlink found", f"Run {REPO_ROOT}/install.sh")
    elif missing_targets:
        note(f"optional targets not linked ({', '.join(missing_targets)}) → {REPO_ROOT}/install.sh")

    missing = [
        t for t in ("HARDWARE.md", "components.md", "SPEC.md", "params.py", "part.py")
        if not (TEMPLATES_DIR / t).is_file()
    ]
    if missing:
        bad(f"missing forge init templates: {', '.join(missing)}", f"Check {TEMPLATES_DIR}")
    else:
        ok("forge init templates (incl. params.py)")


def slicer_check() -> None:
    print("Workstation: slicer")
    cfg = load_config().slicer
    slicer = get_slicer(cfg)
    if slicer is None:
        ok("slicer backend: none (preview-only push mode; configure [slicer] in config.toml to enable slicing)")
        return
    if slicer.available():
        ok(f"slicer backend: {slicer.name} (ready)")
    else:
        bad(f"slicer backend {slicer.name!r} unavailable", "Install Bambu Studio or set slicer.backend = 'none'")


def _get(url: str, token: str, path: str, timeout: float = 10):
    req = urllib.request.Request(url + path, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def hub_and_printers() -> None:
    print("Hub & printers")
    cfg_file = Path(os.environ.get("FORGE_CONFIG") or CONFIG_FILE)
    if cfg_file.is_file() and (os.stat(cfg_file).st_mode & 0o077):
        bad(f"{cfg_file} permissions too open", f"chmod 600 {cfg_file}")
    hub_cfg = load_config().hub
    if not hub_cfg.url or not hub_cfg.token:
        note("Hub not configured yet → run `forge serve` to start a local Hub automatically")
        return
    try:
        projects = _get(hub_cfg.url, hub_cfg.token, "/projects")
        ok(f"Hub reachable ({hub_cfg.url}, {len(projects)} project(s))")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            bad("Hub token rejected (401)", f"Check [hub] token in {cfg_file}")
        else:
            bad(f"Hub returned HTTP {e.code}", "Check Hub logs")
        return
    except (urllib.error.URLError, TimeoutError) as e:
        note(f"Hub unreachable ({hub_cfg.url}): {getattr(e, 'reason', e)} — start locally with `forge serve`")
        return
    try:
        printers = _get(hub_cfg.url, hub_cfg.token, "/printers", timeout=12)
        if not printers:
            ok("printers: none configured (preview-only mode)")
        else:
            for p in printers:
                state = p.get("gcode_state") or p.get("error") or "?"
                ok(f"printer {p.get('id')} ({p.get('name', '?')}): {state}")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        note(f"Could not query /printers: {e}")
    note(f"web preview: {hub_cfg.url}/preview")


def main() -> int:
    global problems
    problems = 0
    print(f"Forge doctor ({REPO_ROOT})\n")
    python_and_packages()
    commands_and_skills()
    slicer_check()
    hub_and_printers()
    print()
    if problems:
        print(f"{problems} issue(s) found; follow the → fixes above.")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
