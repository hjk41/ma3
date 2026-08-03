# Agent eval 节奏（周更子集）

> 英文版：[agent-eval-cadence.md](agent-eval-cadence.md)

设计：[Fable archive](../../09-engineering/design-archive/26-quality-playwright-eval-cadence-fable.md)。  
完整发版门禁： [release-agent-behavior-tests.zh.md](release-agent-behavior-tests.zh.md)。

## 决策

| 项 | 选择 |
|----|------|
| 节奏 | **每周一**目标，**LAN 主机 checklist**（非 GitHub cron） |
| 周更子集 | **claude × T2 / T4 / T5**（载体 `mihomo-proxy`） |
| 发版前 | 仍为 **T0–T5 × 三 Agent** |
| 入口 | `code/eval/scripts/run_behavior_subset.sh` |

## 运行

```bash
bash code/eval/scripts/run_behavior_subset.sh --dry-run
export MA3_BASE_URL=http://127.0.0.1:8000
bash code/eval/scripts/run_behavior_subset.sh --agent claude --tests T2,T4,T5
```

报告（gitignore）：`code/eval/results/behavior/<UTC>-<agent>/report.{json,md}`。

## 运行记录

| 日期 (UTC) | 主机 | Agent | T2 | T4 | T5 | 备注 |
|------------|------|-------|----|----|----|------|
| 2026-07-03 | LAN | 三 Agent | PASS* | PASS* | PASS* | 完整 18/18，见发版行为文档 §4 |
| 2026-08-03 | hct-ThinkPad-P1-Gen-2 | claude | SKIPPED | SKIPPED | SKIPPED | `--dry-run` smoke；见 `results/behavior/2026-08-03T010723Z-claude/` |
