# Self-hosting ma3

Run your own ma3 instance (private knowledge libraries + MCP).  
**Support: community best-effort, no SLA.**

Official SaaS / our internal SSH deploy scripts are separate; this page is for **Compose self-host**.

## Quick start (bootstrap API key, no OIDC)

```bash
git clone https://github.com/hjk41/ma3.git
cd ma3/deploy/self-host
cp .env.example .env   # set POSTGRES_PASSWORD and MA3_API_KEY_ENCRYPTION_SECRET
./up.sh
./verify.sh
docker compose exec ma3 cat /data/bootstrap_api_key.txt
```

Use `plaintext_key=…` as `X-API-Key` for MCP. Point agents at:

`MA3_BASE_URL=http://127.0.0.1:8000` (or your LAN IP / published port).

**Defaults**

| Item | Default |
|------|---------|
| Auth | No OIDC → **bootstrap key** on first start |
| Embeddings | **On** (first start downloads the model into the data volume) |
| `MA3_DEV_AUTH` | **Off** |
| Reverse proxy | **Not required** for LAN + API key |

The Compose image installs **CPU-only** PyTorch (no CUDA/NCCL). That is enough for the default MiniLM embedding model. Disable embeddings on weak machines: `MA3_DISABLE_EMBEDDINGS=1` in `.env`.

HF cache lives under the `ma3_data` volume (`/data/hf`, including `hub/`). After the first successful download you may set `HF_HUB_OFFLINE=1`.

If the container cannot reach Hugging Face (e.g. Docker IPv6 / no WAN), set `HTTP_PROXY` / `HTTPS_PROXY` in `.env` (and keep `db` in `NO_PROXY`).

## Optional: your own OIDC

Set in `.env` (preferred):

```bash
MA3_OIDC_ENABLED=1
MA3_OIDC_ISSUER=https://your-idp.example.com/realms/ma3
MA3_OIDC_CLIENT_ID=...
MA3_OIDC_CLIENT_SECRET=...
MA3_OIDC_REDIRECT_URI=https://ma3.example.com/auth/callback
MA3_AUTH_ADMIN_USERS=you@example.com
MA3_PUBLIC_BASE_URL=https://ma3.example.com
```

Legacy Authing variables (`MA3_AUTHING_*`) still work and enable Authing-style `/oidc` issuer normalization. For Authing via `MA3_OIDC_*`, set `MA3_OIDC_AUTHING_PATH_COMPAT=1` if your issuer URL omits `/oidc`.

With OIDC enabled, portal login at `/ui/keys/` can mint keys; bootstrap auto-create is skipped.

Without OIDC, **browser pages under `/ui/me/` are unavailable** by design — use the bootstrap API key for MCP. Open `/ui/home/` for instance info and `/mcp/info` for endpoint details.

## When do you need a reverse proxy?

Not for LAN + bootstrap key. Prefer Caddy/nginx when:

- You enable **OIDC** (HTTPS callback URLs), or
- You expose the instance on the **public internet** (TLS).

See `Caddyfile.example` in this directory.

## Community library semantics

Each self-hosted instance has its own `lib_default`. It is **not** synchronized with `https://ma3.io`. Agents only see the instance configured in `MA3_BASE_URL`.

## Data volumes

| Volume | Contents |
|--------|----------|
| `ma3_pgdata` | PostgreSQL + pgvector |
| `ma3_data` | bootstrap key file, HF cache |

Back up both. Do not `docker compose down -v` unless you intend to wipe data.

Postgres init runs `CREATE EXTENSION vector` as the image superuser (the app role cannot create extensions).

## Verify

```bash
./verify.sh
# Live deploy verification (healthz, MCP, client bundle, bootstrap UI):
bash ./verify_integration.sh
# or manually:
curl -sS "$MA3_BASE_URL/healthz"
# MCP tools/list with X-API-Key
```

Manual bootstrap / rotate:

```bash
docker compose exec ma3 python scripts/bootstrap_selfhost.py --force
```

## Security notes

- Change all secrets in `.env` before any shared or public deployment.
- Treat `/data/bootstrap_api_key.txt` as a root credential.
- Never set `MA3_DEV_AUTH=1` on a public URL.
- Report vulnerabilities: see repo root `SECURITY.md`.

## Related

- Checklist: [self-hosting-mvp-checklist.md](self-hosting-mvp-checklist.md)
- ADR-015: [015-oidc-pluggable-selfhost-bootstrap.md](../02-architecture/decisions/015-oidc-pluggable-selfhost-bootstrap.md)
- Agent onboarding: `GET {MA3_BASE_URL}/client/agent-onboarding.md`
