# ma3 client — notes for agents

## Files that must stay in sync

When you modify any of the files below, check whether the paired files also need updating:

| If you change... | Also check... |
|---|---|
| `skills/ma3/scripts/ma3_client.py` | `install.sh`, `install.ps1` — they download this file from the server; any new env vars or CLI flags should be reflected in the install scripts and in `skills/ma3/SKILL.md` |
| `skills/ma3/SKILL.md` | The command examples must match the actual CLI of `ma3_client.py` |
| `.env.example` | `install.sh` and `install.ps1` — they write `.env` with the same keys |
| `install.sh` or `install.ps1` | Keep both scripts functionally equivalent |

## How the install scripts work

`install.sh` / `install.ps1` download `ma3_client.py` directly from the ma3 server:

```
GET http://<server>/client/ma3_client.py
```

This route is defined in `server/app/api/routes_docs.py`. It reads `ma3_client.py` live from the `client/` directory of this repo.

Similarly:
- `GET /install.sh`  → serves `client/install.sh`
- `GET /install.ps1` → serves `client/install.ps1`

So **no separate deployment step is needed** for the install scripts — editing the files in this repo is sufficient, as long as the server process is restarted (or the files are updated on the running server's filesystem).

## Deploying / updating

When you deploy a new version of the server or update client files:

1. Pull the latest code on the server machine.
2. Restart the server process so FastAPI picks up any route changes in `routes_docs.py`.
3. The install scripts and `ma3_client.py` are served live from the filesystem — no rebuild needed for those.

## Plugin manifest

`client/.claude-plugin/marketplace.json` declares this directory as a Claude Code plugin.
If you rename the plugin or change the skills directory layout, update this file too.
