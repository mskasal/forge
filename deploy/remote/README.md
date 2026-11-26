# Optional Remote Read-Only Preview (`--profile remote`)

Monitor live print progress and inspect 3D models (`model.glb`) from outside your home network — **without ever exposing printing, print codes, CAD source files, or uploads to the internet**.

---

## What Is Allowed vs. Blocked Remotely

| Capability | Over Remote Gateway |
| --- | --- |
| 3D web preview (`/preview`, `/static/*.js`, `model.glb`, `assembly.json`) | **Allowed** (`GET`, OAuth login + `web` token) |
| Live print progress (`/printers`, `/events`, `/summary`, `/report`) | **Allowed** (`GET`, OAuth login + `web` token) |
| Download STEP / STL / `.gcode.3mf` | **Blocked (403)** |
| View print codes (`GET .../print`) | **Blocked (403)** |
| Start a print (`POST .../print`) or upload versions (`POST .../versions`) | **Blocked (403)** |
| Voice/LAN revision queue (`GET`/`POST .../revisions`) | **Blocked (403)** |
| Using `owner`, `appletv`, or `agent` tokens remotely | **Blocked (403 — `web` token only)** |

Enforced independently at **two layers**:
1. **Caddy (`deploy/remote/Caddyfile`):** Accepts only `GET` requests for preview routes + `/oauth2/*` and forwards to `oauth2-proxy`.
2. **Forge Hub (`hub/app.py`):** Recognizes traffic from `FORGE_REMOTE_PEER` (`forge-auth`, `172.30.90.2` in `hub/docker-compose.yml`) and independently enforces `GET`-only, `REMOTE_ROUTES`, `X-Forwarded-Email`, and the dedicated read-only `web` token.

---

## Setup (Cloudflare Tunnel + Caddy + OAuth2-Proxy)

Prerequisites: a domain managed on Cloudflare, a Cloudflare Zero Trust Tunnel token, and a Google or GitHub OAuth client (client ID + secret).

1. Ensure `hub/config/tokens` has a dedicated `web:<random-token>` line (see [hub/README.md](../../hub/README.md); never reuse your `owner` token remotely).
2. Copy the example configs and restrict permissions:
   ```bash
   cp deploy/remote/.env.example deploy/remote/.env
   cp deploy/remote/Caddyfile.example deploy/remote/Caddyfile
   chmod 600 deploy/remote/.env
   ```
3. Fill `deploy/remote/.env` with `CLOUDFLARE_TUNNEL_TOKEN`, `OAUTH2_PROXY_CLIENT_ID`, `OAUTH2_PROXY_CLIENT_SECRET`, `OAUTH2_PROXY_COOKIE_SECRET`, `OAUTH2_PROXY_REDIRECT_URL`, and restrict access to your email domain or email list (`OAUTH2_PROXY_EMAIL_DOMAINS`).
4. In Cloudflare Zero Trust, point your public hostname (e.g. `forge.example.com`) to `http://forge-caddy:8080`.
5. Start the Hub + remote stack:
   ```bash
   docker compose -f hub/docker-compose.yml --profile remote up -d
   ```
6. Open `https://forge.example.com/preview`, sign in via OAuth, and enter your read-only `web` token once in the browser prompt.

---

## Simpler Alternative (No Domain Needed): Tailscale

If you don't own a domain or don't want Cloudflare + OAuth, skip `--profile remote` completely and use [Tailscale](https://tailscale.com) (with subnet routing to your LAN) so you reach `http://<hub-lan-ip>:8590/preview` privately without exposing anything publicly.
