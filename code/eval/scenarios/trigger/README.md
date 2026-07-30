# Trigger mechanism eval scenarios (P1–P6)

Scenarios for the [trigger experiment](../../../docs/09-engineering/experiments/trigger-mechanisms.md).
Each scenario ships a **neutral user prompt** (`prompt.txt`), optional **KB seed data**
(`seed_kb.json`), and **task verification** (`verify.sh`).

Behavior metrics (first-action read, write-back type, false triggers) come from server logs
and transcript analysis — not from `verify.sh` alone.

## Scenarios

| ID | Dir | Prompt | Read | Write | Infra |
|---|---|---|---|---|---|
| P1 | [trigger-p1](../trigger-p1/) | Install Factory Droid CLI | yes | upvote | host / profile |
| P2 | [trigger-p2](../trigger-p2/) | Compose network debug | yes | upvote | Docker (`compose-network-fix`) |
| P3 | [trigger-p3](../trigger-p3/) | nginx http3 directive error | yes | `report_kind:new` | Docker |
| P4 | [trigger-p4](../trigger-p4/) | Trivial Python question | no | no | none |
| P5 | [trigger-p5](../trigger-p5/) | Switch project npm registry to npmmirror | yes | upvote | workspace `.npmrc` |

> **P5 changelog:** previously “system apt → Tsinghua”; redesigned to project
> `workspace/.npmrc` → `registry.npmmirror.com` so prompt, seed, verify, and
> Docker (no root) all target the same writable file. Seeds are published
> `active` by `seed_trigger_kb.sh`.

| P6 | [trigger-p6](../trigger-p6/) | Read-only repo exploration | no | no | sample tree |

See [manifest.json](manifest.json) for machine-readable metadata.

## Experiment arms

| Arm ID | MCP + skill 来源 |
|---|---|
| `A0-baseline` | 远程 `https://ma3.io` |
| `B0-local-skill-mcp` | 本地 `http://127.0.0.1:8000`（sync + MCP 同源） |

```bash
TRIGGER_ARM=B0-local-skill-mcp bash code/eval/scripts/run_trigger_experiment.sh
```

## Quick start

```bash
cd code/eval/scripts

# Reset env + seed KB + print prompt (no agent)
bash run_trigger_scenario.sh trigger-p2 --seed-kb --print-prompt

# Infra-only verify (golden path for docker scenarios)
bash run_trigger_scenario.sh trigger-p2 --verify-only

# Seed KB for a scenario (requires MA3_KEY_* in secrets)
bash seed_trigger_kb.sh trigger-p1
```

## Run matrix (experiment plan)

- **Week 1**: P1, P2, P4 × all arms × 5 runs (Cursor); droid/claude: A0, A2, A5 × P1, P2, P4
- **Week 2**: add P5, P6 (hooks arms)
- **Week 3**: add P3 (write-back), optional U1–U3

Log each run in [results/trigger/runs.csv](../results/trigger/runs.csv).
