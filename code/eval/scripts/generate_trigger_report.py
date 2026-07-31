#!/usr/bin/env python3
"""Generate multi-arm trigger experiment report (A0–A6, optional B0)."""
from __future__ import annotations

import csv
from pathlib import Path

CSV = Path(__file__).resolve().parents[1] / "results/trigger/runs.csv"
OUT = Path(__file__).resolve().parents[1] / "results/trigger/experiment-report.md"

ARMS_ORDER = [
    "A0-baseline",
    "A1-policy-1.6",
    "A2-tooldesc",
    "A3-hooks",
    "A4-policy-hooks",
    "A5-soft-signal",
    "A6-session-prompt",
    "B0-local-skill-mcp",
]

ARM_LABELS = {
    "A0-baseline": "baseline policy 1.5.1",
    "A1-policy-1.6": "policy 1.6 FIRST-ACTION GATE",
    "A2-tooldesc": "MCP tool description enhanced",
    "A3-hooks": "Cursor hooks (deny-once)",
    "A4-policy-hooks": "A1 policy + A3 hooks",
    "A5-soft-signal": "server soft signals",
    "A6-session-prompt": "session prompt prefix",
    "B0-local-skill-mcp": "local skill + localhost MCP",
}


def pct(n: int, d: int) -> str:
    return "n/a" if d == 0 else f"{100.0 * n / d:.0f}%"


def dedupe(rows: list[dict]) -> list[dict]:
    """Keep last row per arm+runtime+scenario+round (only r1–r3)."""
    key_order: dict[tuple, dict] = {}
    for r in rows:
        run_id = r.get("run_id", "")
        parts = run_id.rsplit("-r", 1)
        rnd = parts[-1] if len(parts) == 2 else run_id
        if not rnd.isdigit() or int(rnd) not in {1, 2, 3}:
            continue
        key = (r.get("arm"), r.get("runtime"), r.get("scenario_id"), rnd)
        key_order[key] = r
    return list(key_order.values())


def arm_stats(subset: list[dict], prompts: set[str] | None = None) -> dict:
    if prompts is not None:
        subset = [r for r in subset if r.get("prompt_id") in prompts]
    read_rs = [r for r in subset if r.get("prompt_id") in {"P1", "P2", "P3", "P5"}]
    neg_rs = [r for r in subset if r.get("prompt_id") in {"P4", "P6"}]
    return {
        "n": len(subset),
        "read_ok": sum(1 for r in read_rs if r.get("read_before_mutation") == "1"),
        "read_n": len(read_rs),
        "write_ok": sum(1 for r in read_rs if r.get("write_occurred") == "1"),
        "write_n": len(read_rs),
        "false_read": sum(1 for r in neg_rs if r.get("false_read") == "1"),
        "neg_n": len(neg_rs),
        "task_ok": sum(1 for r in subset if r.get("task_pass") == "1"),
    }


def row_line(arm: str, s: dict) -> str:
    return (
        f"| {arm} | {s['n']} | "
        f"{pct(s['read_ok'], s['read_n'])} ({s['read_ok']}/{s['read_n']}) | "
        f"{pct(s['write_ok'], s['write_n'])} ({s['write_ok']}/{s['write_n']}) | "
        f"{s['false_read']}/{s['neg_n']} | "
        f"{pct(s['task_ok'], s['n'])} ({s['task_ok']}/{s['n']}) |"
    )


def main() -> None:
    rows = dedupe(list(csv.DictReader(CSV.open(encoding="utf-8"))))
    full = {"P1", "P2", "P3", "P4", "P5", "P6"}
    primary = [a for a in ARMS_ORDER if a.startswith("A")]
    present = {r.get("arm") for r in rows}

    coverage = []
    for arm in primary:
        n = sum(1 for r in rows if r.get("arm") == arm)
        coverage.append(f"| {arm} | {n}/54 |")

    lines = [
        "# ma3 触发机制实验报告（A0–A6）",
        "",
        "> 分支：`trigger` ｜ 数据：`code/eval/results/trigger/runs.csv`",
        "",
        "## 1. 实验组说明",
        "",
        "| Arm | 机制 |",
        "|---|---|",
    ]
    for arm in primary:
        lines.append(f"| **{arm}** | {ARM_LABELS.get(arm, '')} |")

    lines += [
        "",
        "矩阵：7 arms × 3 runtimes（cursor-agent / droid / claude）× 6 scenarios × 3 rounds = **378** 格（不含 B0）。",
        "",
        "### 覆盖",
        "",
        "| Arm | 去重格数 |",
        "|---|---|",
        *coverage,
        f"| **合计** | {sum(1 for r in rows if r.get('arm') in primary)}/378 |",
        "",
        "## 2. Cursor-agent（主战场：policy/hooks 生效）",
        "",
        "| Arm | n | 首读 (P1/P2/P3/P5) | 写回 | 误读 (P4/P6) | 任务完成 |",
        "|---|---:|---|---|---|---|",
    ]
    for arm in primary:
        s = arm_stats(
            [r for r in rows if r.get("arm") == arm and r.get("runtime") == "cursor-agent"],
            full,
        )
        if s["n"]:
            lines.append(row_line(arm, s))

    lines += [
        "",
        "### Cursor 分场景（正例=首读 / 负例=误读）",
        "",
        "| Arm | P1 | P2 | P3 | P4 | P5 | P6 |",
        "|---|---|---|---|---|---|---|",
    ]
    for arm in primary:
        cur = [r for r in rows if r.get("arm") == arm and r.get("runtime") == "cursor-agent"]
        if not cur:
            continue
        cells = []
        for pid in ["P1", "P2", "P3", "P4", "P5", "P6"]:
            rs = [r for r in cur if r.get("prompt_id") == pid]
            if not rs:
                cells.append("-")
            elif pid in {"P4", "P6"}:
                fr = sum(1 for r in rs if r.get("false_read") == "1")
                cells.append(f"误{fr}/{len(rs)}")
            else:
                ok = sum(1 for r in rs if r.get("read_before_mutation") == "1")
                cells.append(f"{ok}/{len(rs)}")
        lines.append(f"| {arm} | {' | '.join(cells)} |")

    lines += [
        "",
        "## 3. 全 runtime 汇总",
        "",
        "| Arm | n | 首读 | 写回 | 误读 | 任务完成 |",
        "|---|---:|---|---|---|---|",
    ]
    for arm in primary:
        s = arm_stats([r for r in rows if r.get("arm") == arm], full)
        if s["n"]:
            lines.append(row_line(arm, s))

    for title, runtime in (("Droid", "droid"), ("Claude", "claude")):
        lines += [
            "",
            f"## 4. {title}",
            "",
            "| Arm | n | 首读 | 写回 | 误读 | 任务完成 |",
            "|---|---:|---|---|---|---|",
        ]
        for arm in primary:
            s = arm_stats(
                [r for r in rows if r.get("arm") == arm and r.get("runtime") == runtime],
                full,
            )
            if s["n"]:
                lines.append(row_line(arm, s))

    lines += [
        "",
        "## 5. 结论（Cursor 主战场）",
        "",
        "1. **A3 hooks** 综合最优：首读 100%、任务 100%、误读 0；写回与 A1/A4 同档（高于 A0）。",
        "2. **A1 policy 1.6**：首读与 A0 持平，写回略升，误读改善。",
        "3. **A4 = A1+A3**：首读满格，但未优于单独 A3（P6 仍可能误读）。",
        "4. **A6 session prefix**：正例读/写最强，负例误读最差（P6 近乎全误）。",
        "5. **A2 tooldesc**：整体不优于 A0（P2 首读偏弱）。",
        "6. **A5 soft signal**：写回尚可，误读偏高。",
        "7. **Droid / Claude**：droid 不读 Cursor policy；claude 的 ma3 指标多为 0（解析/接线差异），跨 runtime 对比应以 cursor-agent 为主。",
        "",
        "## 6. 如何复现",
        "",
        "```bash",
        "TRIGGER_SKIP_DONE=1 TRIGGER_PARALLEL_WORKERS=4 \\",
        "  bash code/eval/scripts/run_full_trigger_matrix.sh",
        "",
        "python3 code/eval/scripts/generate_trigger_report.py",
        "```",
        "",
    ]

    if "B0-local-skill-mcp" in present:
        b0 = arm_stats([r for r in rows if r.get("arm") == "B0-local-skill-mcp"], full)
        lines += [
            "## 附录：B0（历史对照，不在默认矩阵）",
            "",
            f"- n={b0['n']} 首读 {pct(b0['read_ok'], b0['read_n'])} "
            f"写回 {pct(b0['write_ok'], b0['write_n'])} "
            f"误读 {b0['false_read']}/{b0['neg_n']} "
            f"任务 {pct(b0['task_ok'], b0['n'])}",
            "",
        ]

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
