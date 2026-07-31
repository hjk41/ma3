#!/usr/bin/env python3
"""Parallel trigger matrix: N Docker workers, one active job per scenario (port/compose safety)."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

EVAL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = EVAL_ROOT / "scripts"
CSV = Path(os.environ.get("TRIGGER_CSV", EVAL_ROOT / "results/trigger/runs.csv"))
LOG = Path(os.environ.get("TRIGGER_MATRIX_LOG", EVAL_ROOT / "results/trigger/experiment-matrix.log"))
MANIFEST = EVAL_ROOT / "scenarios/trigger/manifest.json"
ROUNDS = int(os.environ.get("TRIGGER_ROUNDS", "3"))
WORKERS = int(os.environ.get("TRIGGER_PARALLEL_WORKERS", "4"))
SKIP_DONE = os.environ.get("TRIGGER_SKIP_DONE", "1") == "1"

ARMS = os.environ.get(
    "TRIGGER_ARMS",
    "A0-baseline A1-gate C0-skill C1-gate-skill",
).split()
RUNTIMES = os.environ.get("TRIGGER_RUNTIMES", "cursor-agent claude codex").split()


def log(msg: str) -> None:
    line = time.strftime("[%Y-%m-%dT%H:%M:%SZ]", time.gmtime()) + " " + msg
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def pick_scenarios() -> list[str]:
    import json

    manifest = json.loads(MANIFEST.read_text())
    order = ["P1", "P2", "P4", "P5", "P6", "P3"]
    by_pid = {s["prompt_id"]: s["id"] for s in manifest["scenarios"]}
    return [by_pid[p] for p in order if p in by_pid]


def runtime_available(rt: str) -> bool:
    import shutil

    if rt == "cursor-agent":
        return shutil.which("cursor-agent") is not None
    if rt == "droid":
        return shutil.which("droid") is not None
    if rt == "claude":
        return shutil.which("claude") is not None or Path.home().joinpath(".npm-global/bin/claude").is_file()
    if rt == "codex":
        return shutil.which("codex") is not None
    return False


def is_done(run_id: str) -> bool:
    if not CSV.is_file():
        return False
    return any(line.startswith(run_id + ",") for line in CSV.read_text(encoding="utf-8").splitlines())


def build_jobs(scenarios: list[str]) -> list[tuple[str, str, str, str, str]]:
    jobs = []
    for arm in ARMS:
        for rt in RUNTIMES:
            if not runtime_available(rt):
                continue
            for sc in scenarios:
                for rnd in range(1, ROUNDS + 1):
                    run_id = f"{arm}-{rt}-{sc}-r{rnd}"
                    if SKIP_DONE and is_done(run_id):
                        continue
                    jobs.append((arm, rt, sc, str(rnd), run_id))
    return jobs


def main() -> int:
    scenarios = os.environ.get("TRIGGER_SCENARIOS", "").split() or pick_scenarios()
    jobs = build_jobs(scenarios)
    log(f"parallel workers={WORKERS} pending_jobs={len(jobs)} (B0 excluded)")

    if not jobs:
        log("nothing to run")
        return 0

    if os.environ.get("TRIGGER_SKIP_LOCAL_RESTART", "0") != "1":
        subprocess.run(["bash", str(SCRIPTS / "restart_local_ma3.sh")], check=False)
    else:
        log("TRIGGER_SKIP_LOCAL_RESTART=1 — keeping existing ma3")

    pending = list(jobs)
    active: dict[int, subprocess.Popen] = {}  # worker_id -> proc
    active_run: dict[int, str] = {}
    active_scenario: dict[int, str] = {}
    run_id_by_pid: dict[int, str] = {}
    done = fail = 0

    def free_workers() -> list[int]:
        return [w for w in range(WORKERS) if w not in active]

    def launch(worker: int, job: tuple[str, str, str, str, str]) -> None:
        arm, rt, sc, rnd, run_id = job
        log(f"RUN {run_id} (worker={worker})")
        cell_log = EVAL_ROOT / "results/trigger/workers" / f"w{worker}" / "cell.log"
        cell_log.parent.mkdir(parents=True, exist_ok=True)
        logf = open(cell_log, "a", encoding="utf-8")
        cell_runner = os.environ.get(
            "TRIGGER_CELL_RUNNER",
            str(SCRIPTS / "run_trigger_cell_docker.sh"),
        )
        proc = subprocess.Popen(
            ["bash", cell_runner, str(worker), arm, rt, sc, rnd],
            stdout=logf,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
        )
        logf.close()
        active[worker] = proc
        active_run[worker] = run_id
        active_scenario[worker] = sc
        run_id_by_pid[proc.pid] = run_id

    while pending or active:
        finished_workers = []
        for w, proc in list(active.items()):
            if proc.poll() is not None:
                run_id = active_run[w]
                if proc.returncode == 0:
                    done += 1
                    log(f"DONE {run_id}")
                else:
                    fail += 1
                    log(f"FAIL {run_id}")
                finished_workers.append(w)

        for w in finished_workers:
            del active[w]
            del active_run[w]
            del active_scenario[w]

        busy_scenarios = set(active_scenario.values())
        for w in free_workers():
            pick = None
            for i, job in enumerate(pending):
                if job[2] not in busy_scenarios:
                    pick = i
                    break
            if pick is None:
                break
            job = pending.pop(pick)
            launch(w, job)
            busy_scenarios.add(job[2])

        if active:
            time.sleep(3)

    subprocess.run([sys.executable, str(SCRIPTS / "generate_trigger_report.py")], check=False)
    log(f"parallel complete done={done} fail={fail} workers={WORKERS}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
