# ma3 Agent Evaluation Harness (ma3_v1)

Scripts and Docker scenarios for agent evaluation on LAN hosts (202).

## Layout

```
code/eval/
  README.md
  secrets/                  # NOT in git — copy from *.example
  scripts/
    run_all_scenarios_verify.sh   # CI: golden fix + verify all 10
    run_scenario_verify.sh
    apply_golden_fix.sh
    load_secrets.sh
  orchestrator/             # full agent eval matrix
  scenarios/                # infra scenarios + agent-client-sync + trigger-p*
  results/
    trigger/                # trigger experiment artifacts (mostly gitignored)
```

## Quick verify (no agent — golden path)

Confirms Docker scenarios and `verify.sh` work on the host:

```bash
cd code/eval/scripts
bash run_all_scenarios_verify.sh
# or one scenario:
bash run_scenario_verify.sh mihomo-proxy
```

On 202 (deploy first, then run the scenario verifies):

```bash
./deploy/deploy.sh deploy/deploy.202.env
cd code/eval/scripts && bash run_all_scenarios_verify.sh
```

## Full agent eval

```bash
source code/eval/scripts/load_secrets.sh
bash code/eval/orchestrator/run_eval.sh --scenario mihomo-proxy --agent droid --round 1
```

See [orchestrator/scenarios.json](orchestrator/scenarios.json) for the rotation matrix.

## Trigger mechanism experiment (P1–P6)

```bash
bash code/eval/scripts/run_trigger_scenario.sh trigger-p2 --seed-kb --print-prompt
bash code/eval/scripts/run_trigger_scenario.sh trigger-p5 --print-prompt
```

Docs: [scenarios/trigger/README.md](scenarios/trigger/README.md),
[docs/09-engineering/experiments/trigger-mechanisms.md](../docs/09-engineering/experiments/trigger-mechanisms.md).

### Experiment arms

| Arm | Command |
|---|---|
| A0-baseline (remote ma3.io) | `TRIGGER_ARM=A0-baseline bash code/eval/scripts/run_trigger_experiment.sh` |
| B0-local-skill-mcp | `TRIGGER_ARM=B0-local-skill-mcp bash code/eval/scripts/run_trigger_experiment.sh` |

Arm setup restores `~/.cursor/mcp.json` on exit. See [scenarios/trigger/arms.json](scenarios/trigger/arms.json).

Host profiles (not in repo): `~/ma3-eval/profiles/{claude,droid,cursor}/`

