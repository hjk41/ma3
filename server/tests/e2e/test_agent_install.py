"""
E2E: agent-driven installation test.

Spawns a Claude Code subprocess with the canonical "接入 ma3" prompt from the
Interaction Contract and verifies the plugin is installed fully, without any
manual intervention or trial-and-error retries.

Why this test exists
--------------------
Installation instructions (agents.md) are only useful if a real LLM agent can
follow them correctly on the first attempt.  This test catches regressions where
the instructions become ambiguous, a required step is missing, or the install
scripts need changes that haven't been reflected in agents.md.

Prerequisites (test is auto-skipped if absent)
-----------------------------------------------
- ``claude`` CLI available in PATH
- Auth env vars present in ``~/.claude/settings.json`` (populated by ``claude login``)
- A reachable ma3 server (override via ``MA3_TEST_BASE_URL`` env var)
- An API key for that server (override via ``MA3_TEST_API_KEY`` env var)

Run standalone::

    pytest tests/e2e/test_agent_install.py -v -s -m agent

The test is tagged ``@pytest.mark.agent`` and is NOT included in the default test
run (``pytest tests/``).  Run it deliberately as an integration check.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

# ── Configuration ──────────────────────────────────────────────────────────────

_DEFAULT_BASE_URL = "http://10.100.193.54:8000"
_DEFAULT_API_KEY = "073fa9d618d31f89ecd2ab21e4c9c404290f5a5e987ce46c"

MA3_TEST_BASE_URL = os.environ.get("MA3_TEST_BASE_URL", _DEFAULT_BASE_URL)
MA3_TEST_API_KEY = os.environ.get("MA3_TEST_API_KEY", _DEFAULT_API_KEY)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _claude_auth_env() -> dict[str, str]:
    """
    Return the auth env vars (ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL, …)
    stored in ~/.claude/settings.json so the claude subprocess can authenticate
    even when HOME is redirected to a temp directory.
    """
    settings_file = Path.home() / ".claude" / "settings.json"
    if not settings_file.exists():
        return {}
    try:
        return json.loads(settings_file.read_text(encoding="utf-8")).get("env", {})
    except Exception:
        return {}


def _has_claude_cli() -> bool:
    return bool(shutil.which("claude"))


def _server_reachable(base_url: str) -> bool:
    try:
        r = subprocess.run(
            ["curl", "-sf", "--max-time", "5", f"{base_url}/healthz"],
            capture_output=True,
            timeout=8,
        )
        return r.returncode == 0
    except Exception:
        return False


# ── Install prompt ─────────────────────────────────────────────────────────────

# Mirrors the Interaction Contract from agents.md:
#   "按 <URL>/agents.md 的说明，接入 ma3 系统"
# The API key is included in the prompt so agents.md's install instruction
# "the API key the user provides" is unambiguous — the agent picks it from here.
#
# "自主完成全部安装步骤" (complete all installation steps autonomously) and
# "不要等待确认" (do not wait for confirmation) together encode the
# no-manual-intervention requirement.

_INSTALL_PROMPT = textwrap.dedent("""\
    按 {base_url}/agents.md 的说明接入 ma3。
    API key: {api_key}
    自主完成全部安装步骤，安装后用 warmup 验证。不要等待用户确认。
""")


# ── Test ───────────────────────────────────────────────────────────────────────

@pytest.mark.agent
@pytest.mark.skipif(
    not _has_claude_cli() or not _claude_auth_env(),
    reason="'claude' CLI or auth not available (run 'claude login' first)",
)
def test_agent_installs_ma3_plugin_autonomously(tmp_path):
    """
    A Claude Code agent given only the standard "接入 ma3" prompt must be able
    to install the ma3 plugin fully without manual intervention or retries.

    Isolation
    ---------
    HOME is redirected to a fresh temp directory so the agent starts with a clean
    slate and all installation artifacts are isolated from the real home.  Auth
    env vars are injected directly so claude can still authenticate.

    Verification
    ------------
    1. Plugin directory and client script were created.
    2. ``.env`` contains the correct BASE_URL and API_KEY.
    3. Codex skill symlink exists at ``~/.codex/skills/ma3``.
    4. Claude permission rules for ``ma3_client.py`` are in settings.json.
    5. The installed client can call ``healthz`` successfully.
    """
    if not _server_reachable(MA3_TEST_BASE_URL):
        pytest.skip(f"ma3 server not reachable at {MA3_TEST_BASE_URL}")

    # ── Isolated HOME ──────────────────────────────────────────────────────────

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    fake_claude_dir = fake_home / ".claude"
    fake_claude_dir.mkdir()
    fake_codex_dir = fake_home / ".codex"
    fake_codex_dir.mkdir()

    # Seed an empty settings.json; install.sh step 5 will patch it.
    (fake_claude_dir / "settings.json").write_text("{}", encoding="utf-8")

    # ── Subprocess environment ─────────────────────────────────────────────────

    # Auth env vars come from the real settings.json so claude can authenticate.
    # We do NOT set MA3_API_KEY here — the agent should extract it from the prompt
    # and pass it to install.sh via --api-key (the recommended form in agents.md).
    subprocess_env = {
        **os.environ,
        **_claude_auth_env(),
        "HOME": str(fake_home),
    }

    # ── Run the agent ──────────────────────────────────────────────────────────

    prompt = _INSTALL_PROMPT.format(
        base_url=MA3_TEST_BASE_URL,
        api_key=MA3_TEST_API_KEY,
    )

    result = subprocess.run(
        [
            "claude",
            "--dangerously-skip-permissions",
            "--print",
            prompt,
        ],
        env=subprocess_env,
        capture_output=True,
        text=True,
        timeout=300,   # 5-minute ceiling; typical run is 2-3 min
        cwd=str(fake_home),
    )

    agent_output = (result.stdout + "\n" + result.stderr).strip()

    # ── Artifact assertions ────────────────────────────────────────────────────

    plugin_dir = fake_home / "plugins" / "ma3"
    client_script = plugin_dir / "skills" / "ma3" / "scripts" / "ma3_client.py"
    env_file = plugin_dir / ".env"
    skill_link = fake_codex_dir / "skills" / "ma3"
    settings_file = fake_claude_dir / "settings.json"

    def _fail(msg: str) -> None:
        pytest.fail(f"{msg}\n\n─── agent output ───\n{agent_output}\n───")

    # Plugin directory
    if not plugin_dir.is_dir():
        _fail(f"Plugin directory not created: {plugin_dir}")

    # Client script
    if not client_script.exists():
        _fail(f"ma3_client.py not downloaded to {client_script}")

    # .env content
    if not env_file.exists():
        _fail(f".env not created at {env_file}")

    env_text = env_file.read_text(encoding="utf-8")
    if MA3_TEST_BASE_URL not in env_text:
        _fail(
            f".env is missing MA3_BASE_URL={MA3_TEST_BASE_URL!r}\n"
            f".env contents:\n{env_text}"
        )
    if MA3_TEST_API_KEY not in env_text:
        _fail(f".env is missing the API key\n.env contents:\n{env_text}")

    # Codex skill symlink
    if not skill_link.exists():
        _fail(f"Codex skill symlink not created at {skill_link}")

    # Claude permission rules
    settings = json.loads(settings_file.read_text(encoding="utf-8"))
    allow_rules = settings.get("permissions", {}).get("allow", [])
    if not any("ma3_client.py" in r for r in allow_rules):
        _fail(
            "Claude permission rules for ma3_client.py not added to settings.json.\n"
            f"permissions.allow: {allow_rules}"
        )

    # ── Functional check ───────────────────────────────────────────────────────

    healthz = subprocess.run(
        ["python3", str(client_script), "healthz"],
        env={
            "MA3_BASE_URL": MA3_TEST_BASE_URL,
            "MA3_API_KEY": MA3_TEST_API_KEY,
            "MA3_AUTH_MODE": "x-api-key",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert healthz.returncode == 0, (
        f"healthz failed after agent install:\n"
        f"stdout: {healthz.stdout}\nstderr: {healthz.stderr}"
    )
    assert "ok" in healthz.stdout.lower(), (
        f"Unexpected healthz response: {healthz.stdout!r}"
    )
