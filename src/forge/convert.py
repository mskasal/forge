"""Convert STEP outputs into web (GLB) and optional Apple TV (USDZ) preview assets.

- model.glb  — Three.js web preview (glTF binary, metres, Y-up) — always generated
- model.usdz — Apple TV / RealityKit (USD, mm, Z-up) — generated when `usd-core` is installed

Runs on the workstation during `forge push` because OCCT tessellation uses ~500 MB RAM.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from build123d import Color, Compound, Unit, export_gltf, import_step

from forge.assembly import ensure_assembly
from forge.check import COLORS

TOL = 0.05  # mm — below FDM resolution


def load_parts(folder: Path) -> list[tuple[str, Compound]]:
    steps = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".step", ".stp"))
    parts = [p for p in steps if p.stem != "assembly"] or steps
    if not parts:
        raise FileNotFoundError(f"No STEP files found in {folder}")
    return [(p.stem, import_step(p)) for p in parts]


def part_colors(n: int, color: str | None = None) -> list[Color]:
    return [Color(color or COLORS[i % len(COLORS)]) for i in range(n)]


def write_glb(parts, colors: list[Color], path: Path) -> None:
    children = []
    for (name, shape), col in zip(parts, colors):
        shape.color = col
        shape.label = name
        children.append(shape)
    export_gltf(
        Compound(children=children),
        str(path),
        unit=Unit.MM,
        binary=True,
        linear_deflection=TOL,
        angular_deflection=0.2,
    )


def write_usdz(parts, colors: list[Color], path: Path) -> bool:
    """Write USDZ if `usd-core` (pxr) is installed; return False otherwise."""
    try:
        from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, UsdUtils, Vt
    except ImportError:
        return False

    with tempfile.TemporaryDirectory() as tmp:
        usdc = Path(tmp) / "model.usdc"
        stage = Usd.Stage.CreateNew(str(usdc))
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(stage, 0.001)
        root = UsdGeom.Xform.Define(stage, "/Model")
        stage.SetDefaultPrim(root.GetPrim())
        for i, ((name, shape), col) in enumerate(zip(parts, colors)):
            safe = "".join(c if c.isalnum() else "_" for c in name) or f"part{i}"
            verts, tris = shape.tessellate(TOL, 0.2)
            mesh = UsdGeom.Mesh.Define(stage, f"/Model/{safe}")
            mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(v.X, v.Y, v.Z) for v in verts]))
            mesh.CreateFaceVertexCountsAttr(Vt.IntArray([3] * len(tris)))
            mesh.CreateFaceVertexIndicesAttr(Vt.IntArray([k for t in tris for k in t]))
            mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)

            rgb = Gf.Vec3f(*tuple(col)[:3])
            mesh.CreateDisplayColorAttr(Vt.Vec3fArray([rgb]))
            mat = UsdShade.Material.Define(stage, f"/Model/Materials/{safe}")
            shader = UsdShade.Shader.Define(stage, f"/Model/Materials/{safe}/Surface")
            shader.CreateIdAttr("UsdPreviewSurface")
            shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(rgb)
            shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.7)
            mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
            UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(mat)
        stage.GetRootLayer().Save()
        if not UsdUtils.CreateNewUsdzPackage(Sdf.AssetPath(str(usdc)), str(path)):
            raise RuntimeError("Failed to create USDZ package")
    return True


def convert(folder: Path, color: str | None = None) -> list[Path]:
    """Generate model.glb, assembly.json, and optional model.usdz from STEP files."""
    parts = load_parts(folder)
    colors = part_colors(len(parts), color)
    glb, usdz = folder / "model.glb", folder / "model.usdz"
    write_glb(parts, colors, glb)
    out = [glb]
    asm = ensure_assembly(folder, parts)
    if asm is not None:
        out.append(asm)
    if write_usdz(parts, colors, usdz):
        out.append(usdz)
    else:
        if usdz.exists():
            usdz.unlink()
        print("Note: usd-core not installed; generated model.glb only (pip install 'forge-cad[appletv]' for USDZ).", file=sys.stderr)
    return out
