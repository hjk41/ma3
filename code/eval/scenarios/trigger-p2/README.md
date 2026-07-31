# trigger-p2 — Compose network fix (P2)

Wraps [compose-network-fix](../compose-network-fix/). KB should contain the nginx upstream hostname fix.

## Quick run

```bash
bash code/eval/scripts/run_trigger_scenario.sh trigger-p2 --seed-kb --verify-only
```

Expected: read before edit; upvote seeded record after fix; `curl :18081` returns backend body.
