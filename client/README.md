# ma3 Plugin

Local plugin for the ma3 verified-knowledge service.

ma3 is also referred to as `马妈妈` in Chinese instructions.

## Install

**Linux / macOS / WSL:**

```bash
MA3_API_KEY=<your_token> curl -fsSL http://10.100.193.54:8000/install.sh | bash
```

**Windows PowerShell:**

```powershell
$env:MA3_API_KEY="<your_token>"; irm http://10.100.193.54:8000/install.ps1 | iex
```

Install creates `~/plugins/ma3/` with all files needed to run offline:

```
~/plugins/ma3/
├── .codex-plugin/plugin.json
├── .env
├── AGENTS.md
├── examples/
│   ├── search-payload.example.json
│   └── ingest-payload.example.json
└── skills/ma3/
    ├── SKILL.md
    └── scripts/ma3_client.py
```

Verify with:

```bash
python ~/plugins/ma3/skills/ma3/scripts/ma3_client.py warmup
```

## Environment

Config is loaded from `~/plugins/ma3/.env`:

- `MA3_BASE_URL` — defaults to `https://hjk41.cc`
- `MA3_API_KEY` — library token for normal read/write
- `MA3_LIBRARY_ID` — which library this token belongs to (optional, shown in ingest responses)
- `MA3_ADMIN_KEY` — for library/token management and promote/reject
- `MA3_AUTH_MODE` — `x-api-key` (default) or `bearer`

Legacy `YINGCHAN_*` variables are still accepted as a compatibility fallback.

## Quick Commands

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\healthz.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\search.ps1 --input payload.json
powershell -ExecutionPolicy Bypass -File .\scripts\get-record.ps1 rec_123
powershell -ExecutionPolicy Bypass -File .\scripts\ingest.ps1 --input ingest.json
```

Linux/macOS:

```bash
bash ./scripts/healthz.sh
bash ./scripts/search.sh --input payload.json
bash ./scripts/get-record.sh rec_123
bash ./scripts/ingest.sh --input ingest.json
```

## Direct Client Examples

```bash
python ~/plugins/ma3/skills/ma3/scripts/ma3_client.py warmup
python ~/plugins/ma3/skills/ma3/scripts/ma3_client.py search --input examples/search-payload.example.json
python ~/plugins/ma3/skills/ma3/scripts/ma3_client.py get-record rec_123
python ~/plugins/ma3/skills/ma3/scripts/ma3_client.py ingest --input examples/ingest-payload.example.json
```

