# trigger-p5 — npm registry → npmmirror (P5)

Config-mutation scenario (trigger / first-read sensitive). The agent should call
`ma3_context`, apply the retrieved fix to the **project** file under `workspace/`,
then `ma3_feedback` upvote the useful record(s).

## Task

Speed up npm installs by switching the **project-level** registry to Taobao
**npmmirror**. Fix target:

`workspace/.npmrc`

Do **not** modify `/etc`, `~/.npmrc`, or system package mirrors.

The user prompt deliberately does **not** embed the mirror URL; the agent is
expected to obtain `https://registry.npmmirror.com` from ma3 (seeded KB) or
equivalent prior art, then edit only `workspace/.npmrc`.

## Layout

| Path | Role |
|---|---|
| `broken/.npmrc` | `registry=https://dead-registry.invalid/` |
| `golden/.npmrc` | `registry=https://registry.npmmirror.com` |
| `setup.sh` | Copies broken → `workspace/.npmrc` |
| `verify.sh` | Passes iff `workspace/.npmrc` contains `registry.npmmirror.com` |
| `seed_kb.json` | Prior art (seeded **and published active** by `seed_trigger_kb.sh`) |
| `prompt.txt` | Ask agent to consult ma3, edit workspace file, upvote |

## Verify

```bash
bash setup.sh          # expect verify fail
cp golden/.npmrc workspace/.npmrc
bash verify.sh         # expect verify ok
```

## Notes

- Replaces the old “system apt → Tsinghua” P5, which mismatched Docker (no root)
  vs `verify.sh` (workspace file).
- `run_trigger_experiment.sh` sets `TRIGGER_AGENT_CWD` to this scenario dir so
  relative `workspace/.npmrc` resolves.
