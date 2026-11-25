"""Optional headless Blender studio renderer (`forge render`) — zero extra Python deps."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from forge.check import OUT_DIR

MAC_BLENDER = Path("/Applications/Blender.app/Contents/MacOS/Blender")
DEFAULT_COLOR = "#2b2e33"


def find_blender() -> Path | None:
    """Locate Blender CLI on macOS or Linux (overridable via FORGE_BLENDER_CLI)."""
    override = os.environ.get("FORGE_BLENDER_CLI")
    if override and Path(override).is_file():
        return Path(override)
    if MAC_BLENDER.is_file():
        return MAC_BLENDER
    found = shutil.which("blender")
    return Path(found) if found else None


def hex_to_rgba(color: str) -> tuple[float, float, float, float]:
    """Convert #RRGGBB hex string to linear-ish sRGB RGBA tuple in [0, 1]."""
    raw = color.strip().lstrip("#")
    if len(raw) != 6:
        raise ValueError(f"Expected #RRGGBB color, got {color!r}")
    r, g, b = (int(raw[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (r, g, b, 1.0)


def collect_stls(folder: Path) -> list[Path]:
    """Return part STLs in out/<name>/ (excluding assembly.stl unless it is the only STL)."""
    stls = sorted(p for p in folder.glob("*.stl") if p.stem != "assembly")
    if stls:
        return stls
    asm = folder / "assembly.stl"
    return [asm] if asm.is_file() else []


def build_blender_script(spec: dict) -> str:
    """Return a self-contained Blender Python script for headless studio rendering."""
    payload = json.dumps(spec)
    return f"""
import json, math, os, sys
from pathlib import Path
import bpy
from mathutils import Vector

SPEC = json.loads({payload!r})

# Clean default scene
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# Import STLs (Blender 4.x wm.stl_import with 3.x fallback)
imported = []
for stl_path in SPEC["stls"]:
    before = set(bpy.data.objects)
    if hasattr(bpy.ops.wm, "stl_import"):
        bpy.ops.wm.stl_import(filepath=stl_path, global_scale=0.001)
    else:
        bpy.ops.import_mesh.stl(filepath=stl_path, global_scale=0.001)
    new_objs = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    imported.extend(new_objs)

if not imported:
    sys.exit("No mesh objects imported from STL files.")

# Smooth-by-angle / shading + matte/satin PBR material
mat = bpy.data.materials.new(name="ForgeStudioMat")
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = SPEC["rgba"]
    bsdf.inputs["Roughness"].default_value = 0.42
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.45

for obj in imported:
    obj.data.materials.clear()
    obj.data.materials.append(mat)

# Optional Z-axis exploded view for multi-part assemblies
if SPEC["exploded"] and len(imported) > 1:
    bpy.context.view_layer.update()
    def min_z(o):
        return min((o.matrix_world @ Vector(c)).z for c in o.bound_box)
    imported.sort(key=min_z)
    gap_m = SPEC["explode_gap_mm"] * 0.001
    for idx, obj in enumerate(imported):
        obj.location.z += idx * gap_m

bpy.context.view_layer.update()

# Compute combined world bounding box
corners = [obj.matrix_world @ Vector(c) for obj in imported for c in obj.bound_box]
bb_min = Vector((min(v.x for v in corners), min(v.y for v in corners), min(v.z for v in corners)))
bb_max = Vector((max(v.x for v in corners), max(v.y for v in corners), max(v.z for v in corners)))
center = (bb_min + bb_max) * 0.5
radius = max((bb_max - bb_min).length * 0.5, 0.01)

# Subtle matte floor unless transparent
if not SPEC["transparent"]:
    bpy.ops.mesh.primitive_plane_add(size=radius * 20.0, location=(center.x, center.y, bb_min.z - 0.0002))
    floor = bpy.context.active_object
    fmat = bpy.data.materials.new(name="StudioFloor")
    fmat.use_nodes = True
    fbsdf = fmat.node_tree.nodes.get("Principled BSDF")
    if fbsdf:
        fbsdf.inputs["Base Color"].default_value = (0.90, 0.90, 0.92, 1.0)
        fbsdf.inputs["Roughness"].default_value = 0.85
    floor.data.materials.append(fmat)

# Soft neutral world
world = bpy.data.worlds.new("StudioWorld")
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs["Color"].default_value = (0.94, 0.94, 0.96, 1.0)
    bg.inputs["Strength"].default_value = 0.45

# 3-point studio area lights
def add_light(name, loc, energy, size):
    data = bpy.data.lights.new(name=name, type="AREA")
    data.energy = energy * (radius * 10.0) ** 2
    data.size = size * radius
    obj = bpy.data.objects.new(name=name, object_data=data)
    scene.collection.objects.link(obj)
    obj.location = loc
    direction = center - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

add_light("Key", center + Vector((radius * 2.4, -radius * 2.2, radius * 2.6)), 35.0, 2.0)
add_light("Fill", center + Vector((-radius * 2.6, -radius * 1.4, radius * 1.4)), 14.0, 3.0)
add_light("Rim", center + Vector((0.0, radius * 2.8, radius * 2.0)), 22.0, 2.0)

# Camera aimed at center
cam_data = bpy.data.cameras.new("StudioCam")
cam_data.lens = 50.0
cam = bpy.data.objects.new("StudioCam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

dist = radius * 3.1
elev = math.radians(26.0)

def place_camera(azimuth_deg):
    az = math.radians(azimuth_deg)
    cam.location = center + Vector((
        dist * math.cos(elev) * math.cos(az),
        dist * math.cos(elev) * math.sin(az),
        dist * math.sin(elev),
    ))
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()

# Render engine + cross-platform GPU auto-detection (Metal / HIP / OPTIX / CUDA -> CPU fallback)
if SPEC["engine"] == "eevee":
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items else "BLENDER_EEVEE"
else:
    scene.render.engine = "CYCLES"
    scene.cycles.samples = SPEC["samples"]
    scene.cycles.use_denoising = True
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for dev_type in ("METAL", "HIP", "OPTIX", "CUDA"):
            try:
                prefs.compute_device_type = dev_type
                prefs.get_devices()
                gpus = [d for d in prefs.devices if d.type == dev_type]
                if gpus:
                    for d in prefs.devices:
                        d.use = d.type == dev_type
                    scene.cycles.device = "GPU"
                    break
            except Exception:
                continue
    except Exception:
        scene.cycles.device = "CPU"

scene.render.resolution_x = SPEC["width"]
scene.render.resolution_y = SPEC["height"]
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = SPEC["transparent"]

if SPEC["turntable"]:
    frames_dir = Path(SPEC["frames_dir"])
    frames_dir.mkdir(parents=True, exist_ok=True)
    n = SPEC["frames"]
    for i in range(n):
        place_camera(-45.0 + (360.0 * i / n))
        scene.render.filepath = str(frames_dir / f"frame_{{i:04d}}.png")
        bpy.ops.render.render(write_still=True)
else:
    place_camera(-45.0)
    scene.render.filepath = SPEC["output"]
    bpy.ops.render.render(write_still=True)
"""


def render_studio(
    project_name: str,
    *,
    exploded: bool = False,
    turntable: bool = False,
    color: str = DEFAULT_COLOR,
    transparent: bool = False,
    engine: str = "cycles",
    samples: int = 64,
    width: int = 1920,
    height: int = 1080,
    frames: int = 36,
    explode_gap_mm: float = 18.0,
) -> Path:
    """Render a headless Blender studio hero shot, exploded view, or 360° turntable."""
    blender = find_blender()
    if blender is None:
        sys.exit(
            "Blender not found. Install Blender (e.g. `pacman -S blender` on Arch/Omarchy or "
            "Blender.app on macOS) or set FORGE_BLENDER_CLI."
        )
    folder = OUT_DIR / project_name
    stls = collect_stls(folder)
    if not stls:
        sys.exit(f"No STL files found in {folder}; run `forge run` first.")

    rgba = hex_to_rgba(color)
    suffix = "_exploded" if exploded else ""
    out_img = folder / f"studio{suffix}.png"
    frames_dir = folder / f"turntable{suffix}_frames"
    out_mp4 = folder / f"turntable{suffix}.mp4"

    spec = {
        "stls": [str(p.resolve()) for p in stls],
        "rgba": list(rgba),
        "exploded": exploded,
        "explode_gap_mm": explode_gap_mm,
        "turntable": turntable,
        "transparent": transparent,
        "engine": engine,
        "samples": samples,
        "width": width,
        "height": height,
        "frames": frames,
        "output": str(out_img.resolve()),
        "frames_dir": str(frames_dir.resolve()),
    }

    with tempfile.TemporaryDirectory() as tmp:
        script_path = Path(tmp) / "studio_render.py"
        script_path.write_text(build_blender_script(spec), encoding="utf-8")
        r = subprocess.run(
            [str(blender), "--background", "--python", str(script_path)],
            capture_output=True,
            text=True,
        )
    if r.returncode != 0:
        sys.exit(f"Blender render failed (exit {r.returncode}):\n{r.stdout[-1500:]}{r.stderr[-1500:]}")

    if not turntable:
        if not out_img.is_file():
            sys.exit(f"Blender exited 0 but did not produce {out_img}")
        return out_img

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        r2 = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-framerate", "24",
                "-i", str(frames_dir / "frame_%04d.png"),
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                str(out_mp4),
            ],
            capture_output=True,
            text=True,
        )
        if r2.returncode == 0 and out_mp4.is_file():
            return out_mp4
    return frames_dir
