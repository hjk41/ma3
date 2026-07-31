# trigger-p1 — Install Factory Droid CLI (P1)

**User prompt**: see [prompt.txt](prompt.txt) — neutral wording, no ma3 hints.

## KB seed

[seed_kb.json](seed_kb.json) contains a golden record for Factory Droid install + DeepSeek BYOK +
ma3 MCP wiring. Seed before the run:

```bash
bash code/eval/scripts/seed_trigger_kb.sh trigger-p1
```

## Environment

- Uses isolated `workspace/.factory/` under this scenario dir when `FACTORY_HOME` is exported by
  [setup.sh](setup.sh).
- Full install on eval host (202): reuse binaries from
  [agent-client-sync](../agent-client-sync/binaries/) if present.

## Expected agent behavior

| Check | Pass |
|---|---|
| Read | `ma3_context` before first mutating action (curl/npm/install/write config) |
| Write | `ma3_feedback` upvote on seeded record — **not** a duplicate `ma3_report` |
| Task | `droid` on PATH; `workspace/.factory/mcp.json` points at ma3 MCP |

## Verify

```bash
bash setup.sh
bash verify.sh
```

Set `MA3_TRIGGER_DRY_RUN=1` to skip install checks (behavior-only dry run).
