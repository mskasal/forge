# AGENTS.md — Forge

Cross-agent repository instructions (Claude Code, Antigravity, Gemini CLI, OpenAI Codex, Cursor).
- **Installing / setting up Forge:** Follow `SETUP.md` — ask the user which optional modules they want (printer/slicer, local vs. Pi/Docker Hub, remote preview, Apple TV) before installing or configuring anything. Never assume Bambu hardware, a Raspberry Pi, remote access, or Apple TV.
- **Designing 3D-printable parts in any project:** Load the open-standard skill at `skills/forge/SKILL.md`.

## Architecture
- **`src/forge/`** (workstation, ~500 MB RAM): Build123d CAD toolkit, `check`, `layout`, `validate` (`print_scan`), `mechanisms`, `styles`, `components`, STEP→GLB/(USDZ) conversion, optional slicer (`slicers/bambu.py`), Hub client, local `forge serve`.
- **`hub/`** (always-on Hub, ~40 MB RAM): Lightweight FastAPI server, locally bundled offline Three.js preview, multi-printer registry (`printers/bambu_lan.py` with `guard()`). **Hard invariant: `hub/` must NEVER import `forge`, `build123d`, `OCCT`, or `scipy`.**
- **`deploy/remote/`**: Optional read-only remote preview configs (Cloudflare Tunnel + Caddy + oauth2-proxy).
- **`skills/forge/`**: Open Agent Skills package (`SKILL.md`, `references/`, `templates/`, `examples/`).
- **`clients/appletv/`**: Standalone `Forge` tvOS app (XcodeGen + Swift 6 + RealityKit).

## Non-negotiable rules
1. **Never guess real-object dimensions.** Cite caliper measurements or manufacturer datasheets (`forge.dim.Dim`).
2. **Never start a print autonomously.** Prints require explicit owner confirmation (Web/Apple TV UI or single-use `forge print --code`).
3. **Never weaken `hub/printers/bambu_lan.py` `guard()` or `check_3mf()`.** Only `pushall` and approved `project_file` reach the printer, and target model/nozzle/temperature bounds must match.
4. **Never expose write/print/print-code endpoints remotely.** Remote preview is strictly `GET`-only with the read-only `web` token.
5. **Run both test suites before committing:**
   - `.venv/bin/pytest tests/`
   - `.venv/bin/pytest hub/tests/`
