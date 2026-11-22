"""Architectural invariants and open-source secret/leak guards."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from forge._paths import REPO_ROOT

FORBIDDEN_HUB_IMPORTS = {"forge", "build123d", "OCP", "scipy", "matplotlib"}

# Generic pattern checks — never embed real personal identifiers in tests.
FORBIDDEN_LEAK_REGEXES: list[tuple[str, re.Pattern[str]]] = [
    ("private key block", re.compile(r"BEGIN [A-Z ]*PRIVATE KEY")),
    ("GitHub token", re.compile(r"\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("cloud/API key", re.compile(r"\b(?:AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z\-_]{30,}|sk-[A-Za-z0-9]{24,})\b")),
    ("real Apple Team ID", re.compile(r"DEVELOPMENT_TEAM\s*=\s*(?!YOUR_TEAM_ID\b)[A-Z0-9]{10}\b")),
    ("hardcoded local home path", re.compile(r"(?:/Users/|/home/)[a-zA-Z0-9._-]+/")),
    ("hardcoded Notion link", re.compile(r"https?://(?:www\.|app\.)?notion\.(?:so|com)/")),
]

SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "out", "build", "dist", "node_modules"}
SKIP_EXTS = {".ttf", ".otf", ".png", ".jpg", ".jpeg", ".webp", ".glb", ".usdz", ".3mf", ".stl", ".step", ".pyc"}


def test_hub_never_imports_cad_or_workstation_packages():
    """Hard invariant: hub/ stays ~40 MB RAM and never imports forge, build123d, OCP, or scipy."""
    hub_dir = REPO_ROOT / "hub"
    py_files = [p for p in hub_dir.rglob("*.py") if "tests" not in p.parts]
    assert py_files, "Expected hub Python files"

    violations: list[str] = []
    for path in py_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in FORBIDDEN_HUB_IMPORTS:
                        violations.append(f"{path.relative_to(REPO_ROOT)}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                if root in FORBIDDEN_HUB_IMPORTS:
                    violations.append(f"{path.relative_to(REPO_ROOT)}: from {node.module} import ...")
    assert not violations, "Hub imported forbidden heavy package(s):\n" + "\n".join(violations)


def test_no_secrets_or_personal_paths_in_repo():
    """Ensure no API keys, private keys, real Apple Team IDs, or local home paths are committed."""
    hits: list[str] = []
    self_path = Path(__file__).resolve()

    for path in REPO_ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file() or path.suffix.lower() in SKIP_EXTS:
            continue
        if path.resolve() == self_path:
            continue
        if "hub/static/" in path.as_posix():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, rx in FORBIDDEN_LEAK_REGEXES:
            if rx.search(text):
                hits.append(f"{path.relative_to(REPO_ROOT)} matched {label}")
    assert not hits, "Found potential secret/personal leak:\n" + "\n".join(hits)
