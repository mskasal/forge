"""Export the Forge skill as a compact, self-contained system prompt for web/chat agents."""

from __future__ import annotations

import re

from forge import fdm
from forge._paths import SKILLS_DIR

SKILL_MD = SKILLS_DIR / "SKILL.md"
FORMATS = ("generic", "chatgpt", "gemini", "claude")

_HEADERS = {
    "generic": "# Forge CAD Assistant Instructions",
    "chatgpt": "# Custom GPT / ChatGPT Instructions — Forge (Build123d)",
    "gemini": "# Gemini Gem Instructions — Forge (Build123d)",
    "claude": "# Claude Project Instructions — Forge (Build123d)",
}


def _strip_frontmatter(text: str) -> str:
    return re.sub(r"\A---\n.*?\n---\n+", "", text, count=1, flags=re.DOTALL)


def export_skill(fmt: str = "generic") -> str:
    if fmt not in FORMATS:
        raise ValueError(f"Unknown format {fmt!r}; choose from {', '.join(FORMATS)}")
    body = _strip_frontmatter(SKILL_MD.read_text(encoding="utf-8")).strip()
    body = re.sub(r"\A# .*\n+", "", body, count=1)
    body = re.sub(r"\n## Progressive Disclosure References.*\Z", "", body, flags=re.DOTALL).strip()
    body = re.sub(r"\s*\(see \[references/[^\]]+\]\(references/[^)]+\)\)", "", body)
    body = re.sub(r"\[references/[^\]]+\]\(references/[^)]+\)", "the Forge reference docs", body)

    prof = fdm.DEFAULT
    fdm_block = (
        "## Default FDM Bounds (0.4 mm nozzle, 0.2 mm layer)\n"
        f"- Build volume: {' × '.join(f'{v:g}' for v in prof.build)} mm\n"
        f"- Wall min: {prof.wall_min} mm (load/screw ≥ {prof.wall_load} mm) · Floor/roof min: {prof.floor_min} mm\n"
        f"- Smallest feature: {prof.feature_min} mm · Text stroke ≥ {prof.text_stroke_min:g} mm, depth ≥ {prof.text_depth_min} mm\n"
        f"- Max overhang: {prof.overhang_max_deg:g}° · Max bridge: {prof.bridge_max:g} mm · "
        f"Bed chamfer: {prof.bed_chamfer_min}–{prof.bed_chamfer_max} mm\n"
        "- Reference per-side PLA tolerances: press 0.10/0.05 · tight 0.15/0.10 · "
        "easy 0.20/0.15 · loose 0.25/0.20 mm (round/square)"
    )

    extra = ""
    if fmt == "chatgpt":
        extra = (
            "\n\n## Chat / No-Local-Shell Note\n"
            "If you do not have local terminal access to run `forge`, output clean `params.py` and `<part>.py` "
            "files ready for the user to run locally with `forge run <part>.py --fast` and "
            "`forge push <name> --preview`."
        )

    return f"{_HEADERS[fmt]}\n\n{body}\n\n{fdm_block}{extra}\n"
