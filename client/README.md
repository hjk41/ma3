# ma3 Plugin

Local Codex plugin for the ma3 verified-knowledge service.

ma3 is also referred to as `马妈妈` in Chinese instructions.

The bundled client auto-loads a plugin-local `.env` file from `C:\Users\hct\plugins\ma3\.env` when present.

## Environment

- `MA3_BASE_URL`
  - Optional.
  - Defaults to `https://hjk41.cc`.
- `MA3_API_KEY`
  - Optional.
  - Used for normal read/write operations.
  - On the current `https://hjk41.cc` deployment this is the library token.
- `MA3_ADMIN_KEY`
  - Optional.
  - Used for admin operations such as library/token management and promote/reject flows.
- `MA3_AUTH_MODE`
  - Optional.
  - `x-api-key` (default) or `bearer`.

Legacy `YINGCHAN_*` variables are still accepted as a compatibility fallback.

## Example Payloads

- `examples/search-payload.example.json`
- `examples/ingest-payload.example.json`

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

```powershell
python .\skills\ma3\scripts\ma3_client.py healthz
python .\skills\ma3\scripts\ma3_client.py search --input .\examples\search-payload.example.json
python .\skills\ma3\scripts\ma3_client.py get-record rec_123
python .\skills\ma3\scripts\ma3_client.py ingest --input .\examples\ingest-payload.example.json
```
