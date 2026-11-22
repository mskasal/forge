"""forge init: scaffold a project's hardware/ docs and modular params.py + <part>.py."""

from __future__ import annotations

import datetime as dt
import re
import subprocess
import unicodedata
from pathlib import Path

from forge._paths import TEMPLATES_DIR


def slug(text: str) -> str:
    """Hub-safe lowercase ASCII slug."""
    text = unicodedata.normalize("NFKD", text.replace("ı", "i").replace("İ", "I"))
    text = text.encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:40] or "project"


def project_root() -> Path:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd()


def _write(path: Path, template: str, values: dict[str, str]) -> None:
    if path.exists():
        print(f"  exists, kept: {path}")
        return
    text = (TEMPLATES_DIR / template).read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"  created: {path}")


def _ignore_out(root: Path) -> None:
    gitignore = root / ".gitignore"
    lines = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    if not any(line.strip().rstrip("/") in ("out", "/out") for line in lines):
        with gitignore.open("a", encoding="utf-8") as f:
            f.write(("\n" if lines and lines[-1] else "") + "# forge model output\nout/\n")
        print(f"  added out/ to {gitignore}")


def _add_part_row(card: Path, part: str, forge_name: str) -> None:
    text = card.read_text(encoding="utf-8")
    if f"| {part} |" in text:
        return
    marker = "| --- | --- | --- | --- | --- |\n"
    if marker in text:
        text = text.replace(marker, marker + f"| {part} | draft | `{forge_name}` | — | |\n", 1)
        card.write_text(text, encoding="utf-8")


def _set_style(card: Path, style: str) -> None:
    text = card.read_text(encoding="utf-8")
    line = next((l for l in text.splitlines() if l.startswith("- **Design language:**")), None)
    if line and line != f"- **Design language:** {style}":
        card.write_text(text.replace(line, f"- **Design language:** {style}", 1), encoding="utf-8")
        print(f"  design language: {style}")


def init(name: str | None = None, part: str | None = None, style: str | None = None) -> Path:
    root = project_root()
    hw = root / "hardware"
    card = hw / "HARDWARE.md"
    project = slug(name) if name else None
    if project is None and card.exists():
        m = re.match(r"# (.+?) — hardware", card.read_text(encoding="utf-8"))
        project = slug(m.group(1)) if m else None
    project = project or slug(root.name)
    if style:
        from forge import styles

        try:
            styles.get(style)
        except KeyError as e:
            raise SystemExit(e.args[0]) from None
    values = {
        "project": project,
        "date": dt.date.today().isoformat(),
        "style": style or "_to be chosen — run `forge styles`_",
    }

    print(f"Forge hardware docs in {hw}")
    _write(card, "HARDWARE.md", values)
    if style:
        _set_style(card, style)
    _write(hw / "components.md", "components.md", values)
    (hw / "parts").mkdir(parents=True, exist_ok=True)
    _ignore_out(root)

    if part:
        p = slug(part)
        forge_name = f"{project}-{p}"
        values |= {"part": p, "forge_name": forge_name}
        _write(hw / "parts" / p / "SPEC.md", "SPEC.md", values)
        _write(hw / "parts" / p / "params.py", "params.py", values)
        _write(hw / "parts" / p / f"{p}.py", "part.py", values)
        _add_part_row(card, p, forge_name)
    print("Next: fill in HARDWARE.md and components.md, clarify SPEC.md, get owner approval.")
    return hw
