"""Tests for multi-agent skills, export_skill, and forge doctor symlink verification."""

from __future__ import annotations

import re

import pytest

from forge import doctor, export_skill
from forge._paths import REPO_ROOT, SKILLS_DIR


def test_skill_md_frontmatter_length_and_links():
    skill_md = SKILLS_DIR / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    assert text.startswith("---\nname: forge\n")
    lines = text.splitlines()
    assert len(lines) <= 130, f"SKILL.md too long ({len(lines)} lines > 130)"

    for rel in re.findall(r"\]\((references/[^)]+)\)", text):
        assert (SKILLS_DIR / rel).is_file(), f"Broken SKILL.md reference link: {rel}"

    for entry_file in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
        assert (REPO_ROOT / entry_file).is_file(), f"Missing {entry_file}"


def test_export_skill_formats_are_clean_and_self_contained():
    for fmt in export_skill.FORMATS:
        out = export_skill.export_skill(fmt)
        assert not out.startswith("---")
        assert "(references/" not in out
        assert "Default FDM Bounds" in out
    with pytest.raises(ValueError):
        export_skill.export_skill("invalid-format")


def test_doctor_detects_stale_skill_symlink(tmp_path, monkeypatch, capsys):
    good = tmp_path / "good"
    good.symlink_to(SKILLS_DIR)
    other = tmp_path / "other_skill"
    other.mkdir()
    (other / "SKILL.md").write_text("stale", encoding="utf-8")
    stale = tmp_path / "stale"
    stale.symlink_to(other)

    monkeypatch.setattr(doctor, "SKILL_TARGETS", [("Good", good), ("Stale", stale)])
    monkeypatch.setattr(doctor.shutil, "which", lambda _: str(REPO_ROOT / ".venv/bin/forge"))
    doctor.problems = 0
    doctor.commands_and_skills()
    out = capsys.readouterr().out
    assert "skills linked: Good" in out
    assert "Stale skill points elsewhere" in out
    assert doctor.problems >= 1
