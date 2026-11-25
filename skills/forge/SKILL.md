---
name: forge
description: Design 3D-printable parts parametrically with Build123d, validate geometry and printability at low token cost, preview live on a local or LAN Forge Hub (browser / Apple TV), and dispatch prints only with explicit user approval. Use when designing, revising, inspecting, or printing a physical part (enclosure, case, holder, bracket, lid, mount) or working in a repo with a hardware/ folder.
---

# Forge — Low-Token Parametric CAD & Print Workflow

Works with any coding agent (Claude Code, Gemini CLI, Antigravity, OpenAI Codex, ChatGPT, Cursor). Reply in the user's language; keep code, comments, and `hardware/` files in **English**.

## 0. Preflight
Run `forge doctor` if Forge has not been verified in this environment. If `forge` is missing, install it with `./install.sh` from the Forge repository.

## 1. Non-Negotiable Rules
- **Never guess a real object.** Every component a part holds, touches, or clears must pass the clarification gate below (make/model or product link, sourced dimensions, layout, design language). No "about" or "typical".
- **Never start a print autonomously.** The user starts prints from the Web / Apple TV UI or gives you that version's single-use **print code** (`forge print <project> <version> --code <code> [--printer <id>]`). Never read Hub token files or talk directly to the printer.
- **Never leak secrets or expose the Hub.** Config lives in `~/.config/forge/config.toml` (never print it). Hub is localhost/LAN-only unless the user explicitly enables the read-only remote preview profile.

## 2. Clarification Gate (Before Any Geometry Code)
Before writing geometry for a new part or new component, resolve and confirm in one short summary:
1. **Components:** exact make/model or product link + owned vs. to-buy.
2. **Dimensions:** manufacturer datasheet or caliper measurement (flag store listings as unreliable; ask the user to measure fit-critical values with calipers).
3. **Layout & assembly:** placement, port/button/LED faces, cable route, thermal clearance, lid closure.
4. **Design language:** one per project from `forge styles` (see [references/design-languages.md](references/design-languages.md)).
5. **Approval:** confirm the spec before writing geometry (`SPEC.md` → `approved`).

*Assumptions:* only when the user explicitly says "use X for now". Record in `params.py` (`ASSUMPTIONS`), repeat in summaries, and confirm again before printing.

## 3. Low-Token CAD Architecture (Strict)
1. **Separate `params.py` from geometry:** put all measurements, clearances, flags, and `validate_params()` in `hardware/parts/<part>/params.py`, and geometry in `<part>.py` (see [references/hardware-docs.md](references/hardware-docs.md)). For numeric revisions, read and edit **only `params.py`**.
2. **Never copy old versions** (`v5_lib.py`, `v6_lib.py`, ...). Rely on git history and Hub versions.
3. **Reuse Forge built-ins first** — never rewrite boilerplate CAD helpers:
   - `forge.styles`: `load`, `shell`, `grille`, `label`, `panel`, `ribs`
   - `forge.layout`: `place_on_bed`, `arrange_plate`
   - `forge.validate`: `assert_fdm_params`, `assert_clearance`, `print_scan`
   - `forge.mechanisms`: `teardrop_hole`, `pcb_standoff`, `snap_cantilever`, `cantilever_strain`, `usbc_cutout`, `heatset_boss`, `button_plunger`, `light_pipe_channel`, `oring_groove`, `prism_xy`, `prism_yz`
   - `forge.components`: shared measured/datasheet component library (`forge components`)
4. **Fail fast with `assert`s:** run `assert_fdm_params()` in `params.py` and `assert_clearance()` in assembly checks before meshing or rendering.

## 4. Tiered Design & Verification Loop
1. **Fast math/geometry loop (no STEP/STL, no PNG):**
   ```bash
   forge run hardware/parts/<part>/<part>.py --fast --json
   # Single sub-part tweak:
   forge run hardware/parts/<part>/<part>.py --fast --part <subpart> --json
   ```
   Iterate until `ok: true` and `interferences: []`.
2. **Full export + single compact visual check:**
   ```bash
   forge run hardware/parts/<part>/<part>.py
   ```
   Open `out/<forge-name>/render.png` (compact 768×640 2×2 grid) **once per milestone** (not after every small numeric tweak) to verify shape, cutouts, and no floating bodies. Run `forge.validate.print_scan` before a print-ready push.
3. **Two-stage upload to Forge Hub (local `forge serve` or Pi/Docker):**
   - **During visual iteration (fast — skips slicing):**
     ```bash
     forge push <forge-name> --preview -m "what changed"
     ```
   - **When approved for printing** (confirm the fitted build plate if using a slicer):
     ```bash
     forge push <forge-name> --plate textured|smooth -m "what changed"
     ```
   - **Optional studio visuals (requires Blender):** `forge render <forge-name>` (`--exploded`, `--turntable`, `--transparent`).
4. **Summarize concisely:** what changed, key outer dimensions, assumptions, print orientation, and (if sliced) estimated time/filament.

## 5. Printing & Post-Print
- Printer status: `forge status`.
- Print with user's single-use code: `forge print <forge-name> <version> --code <code> [--printer <id>]`.
- Before printing, remind the user: bed empty & clean, correct filament loaded, fitted build plate matches the sliced plate.
- After printing, ask how it fit and log the result in `SPEC.md`.

## Progressive Disclosure References
Read only when needed:
- Default FDM limits & reference tolerances: [references/fdm-and-tolerances.md](references/fdm-and-tolerances.md)
- Design languages (`instrument`, `quiet`, `plain`, `desk`): [references/design-languages.md](references/design-languages.md)
- `hardware/` docs & shared component library: [references/hardware-docs.md](references/hardware-docs.md)
