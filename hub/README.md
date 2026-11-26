# Forge Hub (Always-On Raspberry Pi / Docker)

Lightweight FastAPI server (~40 MB RAM) providing versioned model storage, offline Three.js 3D web preview, SSE live reload, and guarded multi-printer dispatch.

> **Hard architectural boundary:** `hub/` never imports `forge`, `build123d`, `OCCT`, or `scipy`. Heavy CAD and slicing stay on your workstation; the Hub runs comfortably on any Raspberry Pi or low-memory container.

---

## Quick Setup (Docker Compose)

Run on your Raspberry Pi or Linux server:

### 1. Create Hub config & tokens (`chmod 600`)
Generate random bearer tokens in `hub/config/` (mounted read-only into `/etc/forge` by `hub/docker-compose.yml`):

```bash
mkdir -p hub/config
cp hub/hub.toml.example hub/config/hub.toml
cat > hub/config/tokens <<EOF
owner:$(openssl rand -base64 24 | tr -d '/+=')
agent:$(openssl rand -base64 24 | tr -d '/+=')
appletv:$(openssl rand -base64 24 | tr -d '/+=')
web:$(openssl rand -base64 24 | tr -d '/+=')
EOF
chmod 600 hub/config/tokens hub/config/hub.toml
```

| Token role | Preview & status | Upload versions | Submit revisions | View print codes | Start print | Accepted remotely? |
| --- | --- | --- | --- | --- | --- | --- |
| `owner` | Yes | Yes | Yes | Yes | Yes (direct) | **No (403)** |
| `appletv` | Yes | Yes | Yes | Yes | Yes (direct) | **No (403)** |
| `agent` | Yes | Yes | Read/status only | **No (403)** | Only with single-use `--code` | **No (403)** |
| `web` | Yes | **No (403)** | **No (403)** | **No (403)** | **No (403)** | Yes (GET-only) |

### Interactive Assembly & LAN Revision Queue
- Versions containing `assembly.json` unlock the **`Assembly` / `Print Plate`** toggle, step-by-step playback (`0.25×`–`2×`), **X-Ray**, per-part visibility toggles, and browser video capture (**`● Rec`** / **`360° Clip`**) in `/preview`.
- On LAN, `owner` and `appletv` tokens can submit voice/text revision prompts (`POST /projects/<name>/revisions`), which the Hub queues and broadcasts over SSE to an active workstation chat session running `forge wait-revision <name>`. Revision endpoints are strictly blocked remotely (`403`).

### 2. Start the Hub
```bash
docker compose -f hub/docker-compose.yml up -d
```

Open `http://<server-ip>:8590/preview` on any device on your LAN and sign in with your `owner` (or `web`) token.

### 3. Point your workstation to the Hub
On your laptop, set `[hub]` in `~/.config/forge/config.toml` (`chmod 600`):
```toml
[hub]
url = "http://<server-ip>:8590"
token = "<your-owner-or-agent-token>"
```
Verify with `forge doctor`.

---

## Adding Printers (Optional)

With zero `[[printers]]` blocks in `hub/config/hub.toml`, the Hub runs in **preview-only mode** (`GET /printers` returns `[]`).

To add one or more Bambu Lab printers (LAN-Only Mode enabled on the printer), uncomment and duplicate `[[printers]]` in `hub/config/hub.toml`:

```toml
[[printers]]
id = "a1"
name = "Studio A1"
backend = "bambu_lan"
model = "Bambu Lab A1"
nozzle = "0.4"
host = "192.168.1.50"
serial = "03919A000000000"
access_code_env = "FORGE_PRINTER_A1_CODE"
max_nozzle_temp = 240.0
max_bed_temp = 65.0
use_ams = false
```

- Pass `FORGE_PRINTER_A1_CODE` via environment (or use `access_code_file` mounted read-only).
- Multiple printers are polled in parallel with independent 5 s caches; one offline printer never stalls the others.
- When 2+ printers are configured, `POST /print` requires `printer_id` (`forge print <project> <ver> --code <code> --printer a1`).
- **Safety invariant:** Every outbound MQTT message passes through `guard()` (only `pushall` and approved `project_file` with all calibration/leveling checks forced on), and `check_3mf()` refuses any `.gcode.3mf` whose target model, nozzle, or temperature exceeds that printer's limits.

---

## Optional Remote Read-Only Preview
To view 3D previews and live print progress outside your home network (strictly read-only), see [deploy/remote/README.md](../deploy/remote/README.md).
