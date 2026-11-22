"""Single path resolver for Forge repo/package assets.

Avoids scattered Path(__file__).parent.parent assumptions across modules.
"""

from __future__ import annotations

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent.parent
SKILLS_DIR = REPO_ROOT / "skills" / "forge"
TEMPLATES_DIR = SKILLS_DIR / "templates"
HUB_DIR = REPO_ROOT / "hub"
CONFIG_DIR = Path.home() / ".config" / "forge"
CONFIG_FILE = CONFIG_DIR / "config.toml"
LOCAL_DATA_DIR = Path.home() / ".local" / "share" / "forge"
