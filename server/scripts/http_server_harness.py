from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import uuid4

import httpx


ROOT = Path(__file__).resolve().parents[1]
LOCAL_VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON_EXE = LOCAL_VENV_PYTHON if LOCAL_VENV_PYTHON.exists() else Path(sys.executable)
SEED_PATH = ROOT / "data" / "seed_records.json"
TMP_ROOT = ROOT / ".tmp_http_tests"


class ServerBootError(RuntimeError):
    pass


@contextmanager
def managed_ma3_server(port: int = 8899):
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    temp_dir = TMP_ROOT / f"run_{uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    db_path = temp_dir / "ma3.db"
    log_path = temp_dir / "uvicorn.log"
    base_url = f"http://127.0.0.1:{port}"

    env = os.environ.copy()
    env["MA3_DB_PATH"] = str(db_path)
    env["MA3_SEED_PATH"] = str(SEED_PATH)

    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [
                str(PYTHON_EXE),
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=str(ROOT),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )

    try:
        wait_for_server(base_url, process, log_path)
        yield {
            "base_url": base_url,
            "db_path": db_path,
            "log_path": log_path,
            "process": process,
        }
    finally:
        shutdown_server(process)
        shutil.rmtree(temp_dir, ignore_errors=True)


def wait_for_server(
    base_url: str,
    process: subprocess.Popen,
    log_path: Path,
    timeout_seconds: float = 20.0,
) -> None:
    deadline = time.time() + timeout_seconds
    last_error = "server did not respond"

    while time.time() < deadline:
        if process.poll() is not None:
            raise ServerBootError(
                f"server exited early with code {process.returncode}\n{tail_log(log_path)}"
            )
        try:
            response = httpx.get(f"{base_url}/healthz", timeout=1.0)
            if response.status_code == 200:
                return
            last_error = f"unexpected status {response.status_code}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.2)

    raise ServerBootError(f"timed out waiting for {base_url}: {last_error}\n{tail_log(log_path)}")


def shutdown_server(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def tail_log(log_path: Path, max_chars: int = 4000) -> str:
    if not log_path.exists():
        return "<no log>"
    text = log_path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]
