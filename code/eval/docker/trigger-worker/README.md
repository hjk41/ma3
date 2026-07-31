# ma3-trigger-worker

Docker image for parallel trigger-matrix **agent cells** (replaces host HOME isolation).

## Design

- Base: `agent-client-sync-runner` (claude / codex / cursor-agent / droid).
- Run as **host uid** (`--user 1000:1000`) so Claude allows `--dangerously-skip-permissions`.
- `--network host` so scenario verify ports (`:18081` / `:18082`) and local ma3 `:8010` work.
- Host Docker socket + CLI mounted for P2/P3 compose.
- Per-worker HOME under `code/eval/results/trigger/workers/wN/home` (bind-mounted via `/repo`).

## Build

```bash
cd code/eval/docker/trigger-worker
docker build -t ma3-trigger-worker:latest .
```

## Run one cell

```bash
export MA3_KEY_LOCAL=... DUCKCODING_CODEX_TOKEN=...
export DUCKCODING_HTTPS_PROXY=http://192.168.31.200:1080
bash code/eval/scripts/run_trigger_cell_docker.sh 0 A0-baseline claude trigger-p4 1
```
