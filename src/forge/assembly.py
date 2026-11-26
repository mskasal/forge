"""Assembly animation & print-plate transform metadata (`assembly.json`).

Generates a lightweight, CAD-space (Z-up, mm) JSON manifest consumed identically by:
- Forge Hub Web Preview (Three.js, `model.glb`)
- Forge Apple TV app (RealityKit, `model.usdz`)
- Optional Blender assembly renderer

CAD scripts can author explicit steps with `write_assembly(...)`, or let `forge push`
auto-generate a bottom-up Z-axis assembly + `arrange_plate()` bed layout automatically.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from build123d import Rot, Shape

from forge import fdm

ASSEMBLY_FILENAME = "assembly.json"


@dataclass(frozen=True)
class AssemblyStep:
    """One part's assembly motion and optional print-plate placement (Z-up, mm)."""

    part: str
    step: int = 1
    label: str | None = None
    slide_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotate_deg: tuple[float, float, float] = (0.0, 0.0, 0.0)
    pivot_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    plate: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "part": self.part,
            "label": self.label or self.part.replace("_", " ").replace("-", " ").title(),
            "step": int(self.step),
            "slide_mm": [round(float(v), 3) for v in self.slide_mm],
            "rotate_deg": [round(float(v), 3) for v in self.rotate_deg],
            "pivot_mm": [round(float(v), 3) for v in self.pivot_mm],
        }
        if self.plate is not None:
            out["plate"] = self.plate
        return out


def compute_plate_transforms(
    parts: dict[str, Shape],
    *,
    gap: float = 8.0,
    rotations: dict[str, tuple[float, float, float]] | None = None,
    max_width: float | None = None,
    center_xy: bool = True,
) -> dict[str, dict[str, list[float]]]:
    """Compute rigid Z-up mm transforms placing each part on the Z=0 print plate.

    Matches `forge.layout.arrange_plate()` shelf packing and returns per-part
    `{"translate_mm": [tx, ty, tz], "rot_deg": [rx, ry, rz]}` relative to world origin.
    """
    if gap < 0:
        raise ValueError(f"gap must be >= 0, got {gap}")
    rotations = rotations or {}
    build_lim = fdm.current().build
    limit_x = max_width if max_width is not None else max(build_lim[0] - 16.0, 1.0)

    raw: dict[str, tuple[list[float], list[float]]] = {}
    cur_x = 0.0
    cur_y = 0.0
    row_h = 0.0
    max_x = 0.0
    max_y = 0.0

    for name, shape in parts.items():
        rot = rotations.get(name, (0.0, 0.0, 0.0))
        rx, ry, rz = (float(rot[0]), float(rot[1]), float(rot[2]))
        oriented = Rot(rx, ry, rz) * shape if (rx or ry or rz) else shape
        bb = oriented.bounding_box()
        w, d = bb.size.X, bb.size.Y
        if cur_x > 0.0 and cur_x + w > limit_x:
            cur_x = 0.0
            cur_y += row_h + gap
            row_h = 0.0
        tx = cur_x - bb.min.X
        ty = cur_y - bb.min.Y
        tz = -bb.min.Z
        raw[name] = ([tx, ty, tz], [rx, ry, rz])
        max_x = max(max_x, cur_x + w)
        max_y = max(max_y, cur_y + d)
        cur_x += w + gap
        row_h = max(row_h, d)

    cx = max_x * 0.5 if center_xy else 0.0
    cy = max_y * 0.5 if center_xy else 0.0

    return {
        name: {
            "translate_mm": [round(t[0] - cx, 3), round(t[1] - cy, 3), round(t[2], 3)],
            "rot_deg": [round(r[0], 3), round(r[1], 3), round(r[2], 3)],
        }
        for name, (t, r) in raw.items()
    }


def auto_assembly(
    parts: list[tuple[str, Shape]],
    *,
    gap_mm: float = 24.0,
    plate_gap_mm: float = 8.0,
    plate_rotations: dict[str, tuple[float, float, float]] | None = None,
) -> dict[str, Any]:
    """Generate a default bottom-up Z-axis assembly + print-plate spec for `parts`."""
    if not parts:
        raise ValueError("Cannot build assembly spec with no parts.")

    part_map = dict(parts)
    plate_map = compute_plate_transforms(part_map, gap=plate_gap_mm, rotations=plate_rotations)

    # Sort parts bottom-to-top by minimum Z so base parts stay anchored and upper parts drop in.
    ordered = sorted(parts, key=lambda item: (item[1].bounding_box().min.Z, item[0]))
    steps: list[dict[str, Any]] = []
    cumulative_lift = 0.0
    prev_max_z: float | None = None

    for idx, (name, shape) in enumerate(ordered):
        bb = shape.bounding_box()
        if idx == 0:
            lift = 0.0
        else:
            # Ensure clear visual separation above the previous part's assembled top
            step_gap = max(gap_mm, bb.size.Z * 0.65)
            cumulative_lift += step_gap
            if prev_max_z is not None and bb.min.Z + cumulative_lift < prev_max_z + gap_mm * 0.5:
                cumulative_lift = (prev_max_z - bb.min.Z) + gap_mm * 0.5
            lift = cumulative_lift
        prev_max_z = bb.max.Z + lift

        center = bb.center()
        step_obj = AssemblyStep(
            part=name,
            step=idx + 1,
            slide_mm=(0.0, 0.0, round(lift, 3)),
            pivot_mm=(round(center.X, 3), round(center.Y, 3), round(center.Z, 3)),
            plate=plate_map.get(name),
        )
        steps.append(step_obj.to_dict())

    return {
        "version": 1,
        "units": "mm",
        "up_axis": "Z",
        "plate_mm": [round(float(v), 1) for v in fdm.current().build],
        "steps": steps,
    }


def write_assembly(
    folder: Path,
    steps: list[AssemblyStep | dict[str, Any]],
    *,
    parts: dict[str, Shape] | None = None,
    plate_gap_mm: float = 8.0,
    plate_rotations: dict[str, tuple[float, float, float]] | None = None,
) -> Path:
    """Write an explicit `assembly.json` into `folder`, optionally auto-filling plate transforms."""
    plate_map = (
        compute_plate_transforms(parts, gap=plate_gap_mm, rotations=plate_rotations)
        if parts
        else {}
    )
    serialized: list[dict[str, Any]] = []
    for idx, item in enumerate(steps, start=1):
        d = item.to_dict() if isinstance(item, AssemblyStep) else dict(item)
        d.setdefault("step", idx)
        d.setdefault("label", str(d["part"]).replace("_", " ").replace("-", " ").title())
        d.setdefault("slide_mm", [0.0, 0.0, 0.0])
        d.setdefault("rotate_deg", [0.0, 0.0, 0.0])
        d.setdefault("pivot_mm", [0.0, 0.0, 0.0])
        if "plate" not in d and d["part"] in plate_map:
            d["plate"] = plate_map[d["part"]]
        serialized.append(d)

    spec = {
        "version": 1,
        "units": "mm",
        "up_axis": "Z",
        "plate_mm": [round(float(v), 1) for v in fdm.current().build],
        "steps": serialized,
    }
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / ASSEMBLY_FILENAME
    out.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def ensure_assembly(folder: Path, parts: list[tuple[str, Shape]]) -> Path | None:
    """Preserve an author-written `assembly.json`, or auto-generate one for `parts`."""
    if not parts:
        return None
    out = folder / ASSEMBLY_FILENAME
    if out.is_file():
        try:
            data = json.loads(out.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("steps"), list):
                return out
        except ValueError:
            pass
    spec = auto_assembly(parts)
    out.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out
