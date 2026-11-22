"""Model verification, export, structured report.json, and compact 2x2 PNG render.

    from forge.check import check
    check({"body": body, "lid": lid}, name="enclosure")
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from build123d import Compound, Shape, export_step, export_stl  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

from forge import fdm  # noqa: E402

OUT_DIR = Path(os.environ.get("FORGE_OUT") or Path.cwd() / "out").resolve()
STALE_EXT = {".step", ".stp", ".stl", ".3mf", ".png", ".glb", ".usdz"}
STALE_FILES = {"report.json"}

# Intersection volumes below this threshold (mm³) are treated as numerical noise.
INTERFERENCE_TOL = 1e-3

# Compact 2x2 orthographic grid: 768x640 px (low multimodal token cost, crisp geometry).
RENDER_FIGSIZE = (9.6, 8.0)
RENDER_DPI = 80

VIEWS = [
    ("Isometric", 30, -60, None),
    ("Front (-Y)", 0, -90, "y"),
    ("Top (+Z)", 90, -90, "z"),
    ("Right (+X)", 0, 0, "x"),
]

COLORS = ["#e8a838", "#4a90d9", "#6abf69", "#d9534f", "#9b6fd1", "#5bc0be"]


def _env_flag(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return None
    low = raw.strip().lower()
    if low in ("1", "true", "yes", "on"):
        return True
    if low in ("0", "false", "no", "off"):
        return False
    return None


def _hash_file(path: Path | str | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


@dataclass
class Report:
    name: str
    out_dir: Path
    parts: dict[str, dict] = field(default_factory=dict)
    interferences: list[tuple[str, str, float]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    bbox: tuple[float, float, float] | None = None
    fast: bool = False
    exported: bool = True
    rendered: bool = False
    partial: bool = False
    assumptions: list[str] = field(default_factory=list)
    params_hash: str | None = None

    @property
    def ok(self) -> bool:
        return not self.problems

    def to_dict(self) -> dict:
        return {
            "schema": 1,
            "name": self.name,
            "ok": self.ok,
            "fast": self.fast,
            "exported": self.exported,
            "partial": self.partial,
            "bbox_mm": [round(v, 3) for v in self.bbox] if self.bbox else None,
            "parts": {
                pname: {
                    "size_mm": [round(v, 3) for v in info["size"]],
                    "volume_mm3": round(info["volume"], 3),
                    "solids": info["solids"],
                    "valid": info["valid"],
                }
                for pname, info in self.parts.items()
            },
            "interferences": [
                {"a": a, "b": b, "volume_mm3": round(v, 4)} for a, b, v in self.interferences
            ],
            "problems": list(self.problems),
            "assumptions": list(self.assumptions),
            "params_hash": self.params_hash,
        }

    def __str__(self) -> str:
        mode = " (fast)" if self.fast else ""
        lines = [f"== Check: {self.name}{mode} =="]
        for pname, info in self.parts.items():
            x, y, z = info["size"]
            lines.append(
                f"  {pname}: {x:.2f} × {y:.2f} × {z:.2f} mm, "
                f"volume {info['volume']:.1f} mm³, {info['solids']} solid(s), "
                f"valid={info['valid']}"
            )
        if self.interferences:
            for a, b, v in self.interferences:
                lines.append(f"  interference: {a} ∩ {b} = {v:.3f} mm³")
        else:
            lines.append("  interference: none")
        for p in self.problems:
            lines.append(f"  PROBLEM: {p}")
        if self.exported:
            lines.append(f"  outputs: {self.out_dir}")
        else:
            lines.append(f"  outputs: skipped (report: {self.out_dir / 'report.json'})")
        if self.rendered:
            lines.append(f"  render: {self.out_dir / 'render.png'}")
        lines.append("  RESULT: " + ("OK" if self.ok else "FAILED"))
        return "\n".join(lines)


def check(
    parts: dict[str, Shape] | Shape,
    name: str,
    expected_solids: dict[str, int] | None = None,
    render: bool = True,
    *,
    fast: bool | None = None,
    params_file: Path | str | None = None,
    assumptions: list[str] | None = None,
    check_build_volume: bool = True,
) -> Report:
    """Validate parts, export STEP/STL (unless fast), write report.json, and optionally render.

    Environment flags (set by `forge run`):
      - FORGE_FAST=1     skip STEP/STL export and PNG render
      - FORGE_RENDER=0|1 force-disable or force-enable render.png
      - FORGE_PART=<key> check only the named sub-part if present
      - FORGE_JSON=1     print a single compact JSON line
    """
    if isinstance(parts, Shape):
        parts = {name: parts}
    expected_solids = expected_solids or {}

    part_filter = os.environ.get("FORGE_PART", "").strip()
    partial = False
    if part_filter:
        if part_filter in parts:
            partial = len(parts) > 1
            parts = {part_filter: parts[part_filter]}
        else:
            print(
                f"Warning: FORGE_PART={part_filter!r} not found in {name!r} "
                f"({', '.join(parts)}); checking all parts.",
                file=sys.stderr,
            )

    fast_env = _env_flag("FORGE_FAST")
    fast_mode = fast if fast is not None else bool(fast_env)

    render_env = _env_flag("FORGE_RENDER")
    if render_env is not None:
        do_render = render_env
    elif fast_mode:
        do_render = False
    else:
        do_render = render

    out_dir = OUT_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)
    if not fast_mode:
        for old in out_dir.iterdir():
            if old.is_file() and (old.suffix.lower() in STALE_EXT or old.name in STALE_FILES):
                old.unlink()

    report = Report(
        name=name,
        out_dir=out_dir,
        fast=fast_mode,
        exported=not fast_mode,
        partial=partial,
        assumptions=list(assumptions or ()),
        params_hash=_hash_file(params_file),
    )

    build_lim = fdm.current().build
    mins = [float("inf")] * 3
    maxs = [float("-inf")] * 3
    for pname, shape in parts.items():
        bb = shape.bounding_box()
        mins = [min(mins[0], bb.min.X), min(mins[1], bb.min.Y), min(mins[2], bb.min.Z)]
        maxs = [max(maxs[0], bb.max.X), max(maxs[1], bb.max.Y), max(maxs[2], bb.max.Z)]
        solids = len(shape.solids())
        info = {
            "size": (bb.size.X, bb.size.Y, bb.size.Z),
            "volume": shape.volume,
            "solids": solids,
            "valid": shape.is_valid,
        }
        report.parts[pname] = info
        if not info["valid"]:
            report.problems.append(f"{pname}: invalid geometry")
        want = expected_solids.get(pname, 1)
        if solids != want:
            report.problems.append(
                f"{pname}: found {solids} solid(s), expected {want} (floating body or missing boolean)"
            )
        if info["volume"] <= 0:
            report.problems.append(f"{pname}: zero volume")
        if check_build_volume:
            for axis_name, val, lim in zip(("X", "Y", "Z"), info["size"], build_lim):
                if val > lim + 1e-6:
                    report.problems.append(
                        f"{pname}: {axis_name}={val:.1f} mm exceeds build volume (max {lim:g} mm)"
                    )
        if not fast_mode:
            export_step(shape, str(out_dir / f"{pname}.step"))
            export_stl(shape, str(out_dir / f"{pname}.stl"))

    if parts:
        report.bbox = (maxs[0] - mins[0], maxs[1] - mins[1], maxs[2] - mins[2])

    if not fast_mode and len(parts) > 1:
        export_step(Compound(list(parts.values())), str(out_dir / "assembly.step"))

    for (a, sa), (b, sb) in itertools.combinations(parts.items(), 2):
        common = sa & sb
        vol = common.volume if common is not None else 0.0
        if vol > INTERFERENCE_TOL:
            report.interferences.append((a, b, vol))
            report.problems.append(f"{a} intersects {b} ({vol:.3f} mm³)")

    if do_render and parts:
        render_views(parts, out_dir / "render.png", title=name)
        report.rendered = True

    (out_dir / "report.json").write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if _env_flag("FORGE_JSON"):
        print(json.dumps(report.to_dict(), ensure_ascii=False))
    else:
        print(report)
    return report


def render_views(
    parts: dict[str, Shape],
    path: Path,
    title: str = "",
    *,
    dpi: int | None = None,
) -> Path:
    """Render parts from 4 orthographic views into a single compact 2x2 PNG."""
    meshes = []
    for i, (pname, shape) in enumerate(parts.items()):
        bb = shape.bounding_box()
        tol = max(min(bb.size.X, bb.size.Y, bb.size.Z) / 100, 0.01)
        verts, tris = shape.tessellate(tol, 0.2)
        v = np.array([[p.X, p.Y, p.Z] for p in verts])
        t = np.array(tris)
        meshes.append((pname, v[t], COLORS[i % len(COLORS)]))

    allpts = np.concatenate([m[1].reshape(-1, 3) for m in meshes])
    lo, hi = allpts.min(axis=0), allpts.max(axis=0)
    span = np.maximum(hi - lo, 1e-6)
    light = np.array([0.4, -0.6, 0.7])
    light /= np.linalg.norm(light)

    if dpi is not None:
        use_dpi = max(20, int(dpi))
    else:
        try:
            use_dpi = max(20, int(os.environ.get("FORGE_RENDER_DPI") or RENDER_DPI))
        except ValueError:
            use_dpi = RENDER_DPI

    fig = plt.figure(figsize=RENDER_FIGSIZE, dpi=use_dpi)
    for k, (vtitle, elev, azim, depth_axis) in enumerate(VIEWS):
        ax = fig.add_subplot(2, 2, k + 1, projection="3d")
        ax.set_proj_type("ortho")
        for pname, tris, color in meshes:
            n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
            n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
            shade = 0.35 + 0.65 * np.abs(n @ light)
            base = np.array(matplotlib.colors.to_rgb(color))
            fc = np.clip(shade[:, None] * base, 0, 1)
            ax.add_collection3d(
                Poly3DCollection(tris, facecolors=fc, edgecolors="none", label=pname)
            )
        ax.set_xlim(lo[0], hi[0])
        ax.set_ylim(lo[1], hi[1])
        ax.set_zlim(lo[2], hi[2])
        ax.set_box_aspect(tuple(span))
        ax.view_init(elev=elev, azim=azim)
        for axis in "xyz":
            if axis == depth_axis:
                getattr(ax, f"set_{axis}ticks")([])
            else:
                getattr(ax, f"set_{axis}label")(axis.upper())
        ax.set_title(vtitle)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in meshes]
    fig.legend(handles, [m[0] for m in meshes], loc="lower center", ncol=len(meshes))
    size = " × ".join(f"{s:.1f}" for s in span)
    fig.suptitle(f"{title}  —  total {size} mm")
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    fig.savefig(path)
    plt.close(fig)
    return path
