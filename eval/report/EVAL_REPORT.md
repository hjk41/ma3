# ma3 Agent Evaluation Harness — Status Report

Generated: 2026-06-30 (UTC)

## Environment

| Item | Value |
|------|-------|
| Eval host | `192.168.31.202` (`hct-ThinkPad-P1-Gen-2`) |
| ma3 URL | `http://127.0.0.1:8000` |
| ma3 API | v4 (`auth_mode=v4`) |
| Repo commit (local) | `172cc6a47d8f68a4e0efe278382869ccb73f8b2f` |
| Docker | 29.1.3 + Compose 2.40.3 |
| Eval org | `ma3-eval` (`org_cae2506bae3c`) |
| Eval library | `lib_f188af1ddc52` |
| Agent profiles | `/home/hct/ma3-eval/profiles/{claude,droid,cursor}` |

## Harness completion

| Task | Status |
|------|--------|
| 10 scenarios under `eval/scenarios/` | Done |
| Orchestrator (`run_eval.sh`, `run_all_eval.sh`, `scenarios.json`) | Done |
| Secrets layout + `load_secrets.sh` | Done |
| `bootstrap_eval_tenant.sh` | Done — keys in `eval/secrets/agent-keys.env` on 202 |
| `setup_agent_profiles.sh` path fix (`dirname $0/..`) | Done |
| `deploy_ma3_local.sh` excludes `eval/secrets` | Done |
| `secrets.env` from `~/.bashrc` | Done (local + copied to 202) |
| ma3 deploy to 202 | Done |
| Docker on 202 | Done (+ SOCKS proxy for registry pulls) |
| Smoke test | Done (see below) |

### Scenarios (10/10)

| ID | First agent | Files | Smoke |
|----|-------------|-------|-------|
| claude-deepseek-byok | claude-code | compose + broken settings + verify | Not run |
| mihomo-proxy | droid | compose + broken config + verify | Not run (needs `MIHOMO_SUBSCRIPTION_URL`) |
| transparent-gateway | cursor-cli | compose + broken iptables script + verify | Not run |
| droid-deepseek-byok | claude-code | compose + broken settings + verify | Not run |
| nginx-reverse-proxy | droid | compose + broken nginx + verify | **Smoke OK** |
| supervisord-service | cursor-cli | compose + broken supervisord + verify | Not run |
| postgres-backup | claude-code | compose + broken backup.sh + verify | Not run |
| ssh-key-only | droid | compose + broken sshd_config + verify | Not run |
| http-proxy-apt | cursor-cli | compose + broken env.sh + verify | Not run |
| compose-network-fix | claude-code | compose + broken nginx upstream + verify | Not run |

## Smoke test: `nginx-reverse-proxy`

### Dry-run (orchestrator, no agent)

```bash
bash eval/orchestrator/run_eval.sh --scenario nginx-reverse-proxy --agent droid --round 1 --dry-run
```

| Field | Result |
|-------|--------|
| `verify_pass` | **false** (expected — broken config left in place) |
| `agent_exit` | 0 (agent skipped) |
| Compose lifecycle | up → verify → down — OK |

Result JSON: `eval/results/eval-nginx-reverse-proxy-droid-r1.json`

### Manual verify (no agent)

Applied fix `proxy_pass http://backend:5678;` in `workspace/nginx.conf`, then `verify.sh`:

| Step | Result |
|------|--------|
| setup + fix + compose up | OK |
| `verify.sh` | **pass** (`verify ok`) |
| compose down | OK |

## Blockers / follow-ups

1. **Docker registry access on 202** — Direct pulls time out; configured `/etc/systemd/system/docker.service.d/proxy.conf` with `socks5h://192.168.31.200:1080`. Required before any scenario pull.
2. **Agent CLIs not installed on 202** — Full matrix needs `claude`, `droid`, and `cursor` on the eval host; only harness + dry-run tested so far.
3. **Claude MCP registration** — Still manual: `HOME=/home/hct/ma3-eval/profiles/claude claude mcp add ...`
4. **Cursor DeepSeek proxy** — `deepseek-cursor-proxy` not set up; Cursor CLI scenarios blocked until proxy on `:9000` exists.
5. **`MIHOMO_SUBSCRIPTION_URL`** — Not set in `secrets.env`; `mihomo-proxy` / subscription-dependent paths cannot verify end-to-end.
6. **Remaining scenario images** — Only `nginx:alpine`, `hashicorp/http-echo`, `curlimages/curl` pre-pulled; first run of other scenarios will pull more images (via SOCKS proxy).
7. **Full 30-run matrix** — Not started; awaiting agent installs + subscription URL.

## Harness fixes applied during bring-up

- `run_eval.sh`: call `setup.sh` **before** `docker compose up` (workspace files must exist for volume mounts).
- All `verify.sh`: removed redundant `setup.sh` call (was resetting agent/manual fixes before check).
- `nginx-reverse-proxy/setup.sh` / `mihomo-proxy/setup.sh`: fixed scenario dir resolution (`dirname $0` not `$0/..`).

## Next steps

1. Set `MIHOMO_SUBSCRIPTION_URL` in `eval/secrets/secrets.env` on 202 (never commit).
2. Install Claude Code, Factory Droid, Cursor CLI + DeepSeek proxy on 202.
3. Register Claude MCP with eval key.
4. Pre-pull scenario images or run `run_all_eval.sh --dry-run` to validate compose for all 10.
5. Execute full rotation matrix (`run_all_eval.sh`) and refresh this report with per-run metrics.
