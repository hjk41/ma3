# ma3 Agent Evaluation Harness

Scripts and Docker scenarios for the three-agent (Claude Code / Factory Droid / Cursor CLI) evaluation on LAN hosts.

## Layout

```
eval/
  README.md                 # this file
  secrets/                  # NOT in git — copy from *.example
    secrets.env             # DEEPSEEK_API_KEY, MIHOMO_SUBSCRIPTION_URL, …
    agent-keys.env          # ma3v4_* keys per agent (from bootstrap)
  scripts/
    load_secrets.sh         # source secrets for all eval scripts
    bootstrap_eval_tenant.sh
    ma3_watch.py
  orchestrator/
    run_eval.sh
    scenarios.json
  scenarios/                # one dir per scenario (compose + verify)
  results/                  # run JSON/CSV output (gitignored)
```

Host-isolated agent profiles (not in this repo):

```
/home/hct/ma3-eval/profiles/{claude,droid,cursor}/
```

## Secrets setup (one time)

```bash
cp eval/secrets/secrets.env.example eval/secrets/secrets.env
cp eval/secrets/agent-keys.env.example eval/secrets/agent-keys.env
# Edit secrets.env — add DEEPSEEK_API_KEY and MIHOMO_SUBSCRIPTION_URL
chmod 600 eval/secrets/*.env

# After ma3 is up:
bash eval/scripts/bootstrap_eval_tenant.sh
# Paste issued keys into agent-keys.env
```

Never commit `eval/secrets/*.env` or real subscription URLs.

## Run evaluation

```bash
source eval/scripts/load_secrets.sh
bash eval/orchestrator/run_eval.sh --scenario mihomo-proxy --agent droid --round 1
```

See [orchestrator/scenarios.json](orchestrator/scenarios.json) for the full rotation matrix.
