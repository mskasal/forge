"""forge CLI: parametric CAD loop, local Hub server, preview/sliced push, guarded print."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from forge import hub
from forge.slicers import get_slicer


def run(
    path: str,
    *,
    fast: bool = False,
    render: bool | None = None,
    part: str | None = None,
    as_json: bool = False,
) -> int:
    file = Path(path)
    if not file.is_file():
        sys.exit(f"File not found: {file}")
    env = os.environ.copy()
    if fast:
        env["FORGE_FAST"] = "1"
    if render is not None:
        env["FORGE_RENDER"] = "1" if render else "0"
    if part:
        env["FORGE_PART"] = part
    if as_json:
        env["FORGE_JSON"] = "1"
    return subprocess.call([sys.executable, str(file)], env=env)


def status() -> None:
    printers = hub._request("GET", "/printers")
    if not printers:
        print("No printers configured on Hub (preview-only mode).")
        return
    for s in printers:
        pid = s.get("id", "default")
        name = s.get("name") or pid
        if s.get("error"):
            print(f"{pid} ({name}): unreachable — {s['error']}")
            continue
        state = s.get("gcode_state") or "?"
        line = f"{pid} ({name}): {state}"
        if state in ("RUNNING", "PREPARE", "PAUSE"):
            line += f" · {s.get('mc_percent', 0)}% · {s.get('mc_remaining_time', '?')} min left"
            if s.get("total_layer_num"):
                line += f" · layer {s.get('layer_num', 0)}/{s['total_layer_num']}"
        if s.get("subtask_name"):
            line += f" · job: {s['subtask_name']}"
        print(line)
        print(f"  nozzle {s.get('nozzle_temper', 0):.0f} °C · bed {s.get('bed_temper', 0):.0f} °C")


def print_version(project: str, version: int, code: str, printer_id: str | None = None) -> None:
    """Dispatch an approved print job using the version's single-use print code."""
    payload: dict = {"code": code}
    if printer_id:
        payload["printer_id"] = printer_id
    body = json.dumps(payload).encode()
    r = hub._request("POST", f"/projects/{project}/versions/{version}/print", body, "application/json")
    minutes = f" (~{r['minutes']} min)" if r.get("minutes") else ""
    target = f" on {r['printer_id']}" if r.get("printer_id") else ""
    print(f"Dispatched {project} v{version}{target}{minutes}.")


def main() -> None:
    ap = argparse.ArgumentParser(prog="forge", description="Forge parametric CAD & print pipeline.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="scaffold hardware/ docs + modular params.py + <part>.py")
    p.add_argument("--name", help="project name (default: folder name)")
    p.add_argument("--part", help="add part under hardware/parts/<part>/")
    p.add_argument("--style", help="project design language (`forge styles`)")

    p = sub.add_parser("run", help="run a CAD part script with Forge's Python")
    p.add_argument("file")
    p.add_argument("--fast", action="store_true", help="fast mode: skip STEP/STL export and PNG render")
    rg = p.add_mutually_exclusive_group()
    rg.add_argument("--no-render", dest="render", action="store_false", default=None, help="skip render.png")
    rg.add_argument("--render", dest="render", action="store_true", help="force render.png")
    p.add_argument("--part", help="validate only the named sub-part")
    p.add_argument("--json", dest="as_json", action="store_true", help="print compact single-line JSON")

    p = sub.add_parser("slice", help="slice out/<name>/ locally using configured slicer")
    p.add_argument("name")
    p.add_argument("--plate", help="build plate key (e.g. textured, smooth)")

    p = sub.add_parser("render", help="headless Blender studio render (hero shot, exploded, or turntable)")
    p.add_argument("name")
    p.add_argument("--exploded", action="store_true", help="separate multi-part STLs along +Z")
    p.add_argument("--turntable", action="store_true", help="render a 360° turntable video (requires ffmpeg)")
    p.add_argument("--color", default="#2b2e33", help='material hex color (default: "#2b2e33")')
    p.add_argument("--transparent", action="store_true", help="transparent PNG background (no floor)")
    p.add_argument("--engine", choices=("cycles", "eevee"), default="cycles", help="Blender render engine")
    p.add_argument("--samples", type=int, default=64, help="Cycles sample count (default: 64)")
    p.add_argument("--width", type=int, default=1920, help="output width in px (default: 1920)")
    p.add_argument("--height", type=int, default=1080, help="output height in px (default: 1080)")
    p.add_argument("--frames", type=int, default=36, help="turntable frame count (default: 36)")

    p = sub.add_parser("serve", help="start a local Forge Hub + offline 3D preview server")
    p.add_argument("--lan", action="store_true", help="bind 0.0.0.0 for LAN devices (Apple TV / phones)")
    p.add_argument("--port", type=int, default=8590, help="HTTP port (default: 8590)")
    p.add_argument("--data-dir", type=Path, help="directory for local Hub storage and tokens")

    p = sub.add_parser("push", help="convert and upload out/<name>/ as a new Hub version")
    p.add_argument("name")
    p.add_argument("-m", "--note", default="")
    p.add_argument("--color", help='single preview color, e.g. "#b83227"')
    p.add_argument("--plate", help="build plate key for slicing (e.g. textured, smooth)")
    p.add_argument("--preview", action="store_true", help="upload preview only (skip slicing)")
    p.add_argument("--force", action="store_true", help="bypass --fast / failed report guard")

    p = sub.add_parser("list", help="list projects or versions of a project on the Hub")
    p.add_argument("project", nargs="?")

    sub.add_parser("status", help="show status of all configured printers on the Hub")

    p = sub.add_parser("print", help="start a print with the owner's single-use print code")
    p.add_argument("project")
    p.add_argument("version", type=int)
    p.add_argument("--code", required=True, help="single-use print code shown in Web/Apple TV UI")
    p.add_argument("--printer", help="target printer id (required when multiple printers exist)")

    sub.add_parser("components", help="list and validate the shared component library")
    sub.add_parser("styles", help="list and validate design languages against FDM rules")

    p = sub.add_parser("export-skill", help="print a compact system prompt for web chat agents")
    p.add_argument("--format", choices=("generic", "chatgpt", "gemini", "claude"), default="generic")

    sub.add_parser("doctor", help="check workstation setup, skills, slicer, Hub, and printers")

    args = ap.parse_args()

    if args.cmd == "init":
        from forge.init import init

        init(args.name, args.part, args.style)
    elif args.cmd == "run":
        sys.exit(run(args.file, fast=args.fast, render=args.render, part=args.part, as_json=args.as_json))
    elif args.cmd == "slice":
        slicer = get_slicer()
        if slicer is None:
            sys.exit("No slicer configured (slicer.backend = 'none' in config.toml).")
        out = slicer.slice_project(args.name, args.plate)
        print(f"Sliced: {out}")
    elif args.cmd == "render":
        from forge.render import render_studio

        out = render_studio(
            args.name,
            exploded=args.exploded,
            turntable=args.turntable,
            color=args.color,
            transparent=args.transparent,
            engine=args.engine,
            samples=args.samples,
            width=args.width,
            height=args.height,
            frames=args.frames,
        )
        print(f"Rendered: {out}")
    elif args.cmd == "serve":
        from forge.serve import serve

        serve(lan=args.lan, port=args.port, data_dir=args.data_dir)
    elif args.cmd == "push":
        hub.push(args.name, args.note, args.color, args.plate, preview=args.preview, force=args.force)
    elif args.cmd == "list":
        hub.list_projects(args.project)
    elif args.cmd == "status":
        status()
    elif args.cmd == "print":
        print_version(args.project, args.version, args.code, args.printer)
    elif args.cmd == "components":
        from forge.components import print_catalog

        sys.exit(print_catalog())
    elif args.cmd == "styles":
        from forge.styles import print_catalog

        sys.exit(print_catalog())
    elif args.cmd == "export-skill":
        from forge.export_skill import export_skill

        print(export_skill(args.format), end="")
    elif args.cmd == "doctor":
        from forge.doctor import main as doctor

        sys.exit(doctor())


if __name__ == "__main__":
    main()
