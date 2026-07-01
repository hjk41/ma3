from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCENARIO_DIR = Path(__file__).resolve().parents[3] / "eval" / "scenarios" / "agent-client-sync"


def _docker_available() -> bool:
    return shutil.which("docker") is not None


@pytest.mark.docker
def test_agent_profiles_install_and_upgrade_in_docker():
    """Run full install + server skill bump + upgrade for cursor/codex/claude/droid."""
    if not _docker_available():
        pytest.skip("docker not available")

    run_sh = SCENARIO_DIR / "run.sh"
    assert run_sh.is_file(), f"missing scenario: {run_sh}"

    subprocess.run(["bash", str(run_sh)], cwd=SCENARIO_DIR, check=True, timeout=600)
