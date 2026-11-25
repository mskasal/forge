# Forge Setup Guide (AI Agents & Humans)

Single source of truth for installing and configuring Forge — whether an AI coding agent sets it up interactively or you run the commands yourself.

---

## AI Agent Setup Protocol

If a user asked you to install or set up Forge, **do not install optional components or write printer credentials blindly.**

### Step 1 — Ask the user first (one short message)
Ask these 5 concise questions and wait for their answers:

1. **AI tool(s):** Which agent(s) will you use with Forge? *(Claude Code, Antigravity/Gemini, Codex, Cursor, or web chat only — `./install.sh` links the first four automatically.)*
2. **Printer & slicer:** Do you have a 3D printer? If yes, what model, build volume (mm), and nozzle size? *(Bambu Studio local slicing is built-in; any other printer uses `slicer = "none"` and exports STEP/STL + 3D preview.)*
3. **Where should the Hub run?**
   - **Local only (`forge serve`)** on this laptop *(default — zero extra hardware)*, or
   - **Always-on Hub** on a Raspberry Pi / Linux Docker host *(~40 MB RAM)*.
4. **Remote read-only viewing:** Do you want to check prints/previews away from home? *(No / Tailscale / Cloudflare Tunnel `--profile remote` — strictly read-only, never prints remotely.)*
5. **Apple TV app (`Forge`):** Do you plan to build the tvOS viewer on this Mac? *(Needs Xcode 26 + Apple Developer account; installs optional `usd-core` for `model.usdz` export.)*

### Step 2 — Install only what the user chose
- **Never** print secret tokens, printer access codes, or `~/.config/forge/config.toml` contents to chat output.
- **Never** modify existing user shell profiles without asking; print the `export PATH` line if `~/.local/bin` is missing from `PATH`.
- Follow the matching module steps below, then run **Step 3**.

### Step 3 — Verify
1. Run `forge doctor` (expect zero errors; Hub unreachable is fine if `forge serve` is not running yet).
2. Run a quick verification build on the bundled example:
   ```bash
   forge run skills/forge/examples/tolerance-test/hardware/parts/plate-and-pins/plate-and-pins.py --fast --json
   ```
   Confirm `"ok": true`.
3. Tell the user the exact next command (`forge serve` to open `http://127.0.0.1:8590/preview`, or `forge init --part <name>` in a project repo).

---

## Manual Setup by Module

### 1. Workstation Core (Required)
Requirements: macOS or Linux (Windows via WSL2), Python 3.11+, `git`.

```bash
git clone https://github.com/mskasal/forge.git && cd forge
./install.sh
```

- Creates `.venv/` and installs `forge-cad[hub,dev]`.
- Symlinks `forge` into `~/.local/bin/forge`.
- Links `skills/forge` into `~/.claude/skills`, `~/.gemini/config/skills`, `~/.agents/skills`, and `~/.codex/skills`.
- Add `~/.local/bin` to your `PATH` if `forge doctor` reports `forge command not on PATH`.
- For **Apple TV USDZ export**, install with `FORGE_WITH_APPLETV=1 ./install.sh` (adds `usd-core`).

Start the local Hub + offline 3D preview:
```bash
forge serve                # localhost only: http://127.0.0.1:8590/preview
# forge serve --lan        # expose on your private LAN for phones / Apple TV
```
First run auto-creates an owner token and writes `~/.config/forge/config.toml` (`chmod 600`).

### 2. Printer & Slicer (Optional)
Edit `~/.config/forge/config.toml` (`chmod 600`). Override per-project printer/slicer settings in `./forge.toml` (never put tokens in `./forge.toml`).

```toml
[hub]
url = "http://127.0.0.1:8590"   # or http://<pi-ip>:8590 for an always-on Hub
token = "<owner-or-agent-token>"

[printer]
build_volume = [256.0, 256.0, 256.0]   # e.g. [180, 180, 180] for A1 mini
nozzle_mm = 0.4
layer_mm = 0.2

[slicer]
backend = "none"                       # "none", "bambu" (Bambu Studio), or "orca" (OrcaSlicer — macOS & Linux)
# Used only when backend = "bambu" or "orca":
machine = "Bambu Lab A1 0.4 nozzle"
process = "0.20mm Standard @BBL A1"
filament = "Bambu PLA Matte @BBL A1"
default_plate = "textured"             # "textured" or "smooth"
```

### 3. Always-On Hub (Optional — Raspberry Pi / Docker)
Run the ~40 MB RAM Hub 24/7 on a Raspberry Pi or home server with 0..N printers: see [hub/README.md](hub/README.md).

### 4. Remote Read-Only Preview (Optional)
Track live prints and inspect 3D models away from home without exposing printing or uploads: see [deploy/remote/README.md](deploy/remote/README.md).

### 5. Apple TV Client (Optional)
Inspect `model.usdz` with the Siri Remote and approve LAN prints on Apple TV: see [clients/appletv/README.md](clients/appletv/README.md).
