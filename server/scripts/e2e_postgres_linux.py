"""
e2e_postgres_linux.py
=====================
End-to-end test for ma3 running with a PostgreSQL backend on Linux.

Covers three flows:
  1. HTTP cases — agents.md / healthz / search / ingest / high-risk preview
     (same scenarios as e2e_http_integration_cases.py, now against PostgreSQL)
  2. Codex flow  — bash install.sh → verify skill + rules → exercise client → bash uninstall.sh
  3. Claude flow — claude plugins install → bash install.sh → exercise client → uninstall

Prerequisites:
  - PostgreSQL running and reachable (default: postgresql://ma3user:ma3pass@localhost:5432/ma3db)
    Override via MA3_DATABASE_URL env var.
  - `codex` and `claude` CLIs on PATH.
  - Python dependencies installed in the active venv (fastapi, uvicorn, httpx, psycopg).

Usage:
  cd /root/ma3/server
  MA3_DATABASE_URL=postgresql://ma3user:ma3pass@localhost:5432/ma3db \\
      /root/ma3/.venv/bin/python3 scripts/e2e_postgres_linux.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

import httpx

# ── paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]          # /root/ma3/server
CLIENT_DIR = ROOT.parent / "client"                 # /root/ma3/client
sys.path.insert(0, str(ROOT / "scripts"))

from http_server_harness import managed_ma3_server, TMP_ROOT  # noqa: E402

PYTHON_EXE = Path(sys.executable)

# ── constants ─────────────────────────────────────────────────────────────────
ADMIN_KEY = "pg-e2e-admin-key"
MA3_DATABASE_URL = os.environ.get(
    "MA3_DATABASE_URL",
    "postgresql://ma3user:ma3pass@localhost:5432/ma3db",
)

CREATED_HOMES: list[Path] = []


# ── helpers ───────────────────────────────────────────────────────────────────

class StepError(RuntimeError):
    pass


def _run(
    args: list,
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [str(a) for a in args],
        cwd=str(cwd or ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode != 0:
        raise StepError(
            f"command failed ({proc.returncode}): {' '.join(str(a) for a in args)}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc


def _make_home(name: str) -> Path:
    root = TMP_ROOT / f"{name}_{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    CREATED_HOMES.append(root)
    return root


def _fresh_env(home: Path) -> dict[str, str]:
    """Build a fresh environment that isolates HOME and CODEX_HOME."""
    env = os.environ.copy()
    env["HOME"] = str(home)
    # CODEX_HOME overrides the ~/.codex directory for skill / rule discovery.
    # Without this, codex ignores HOME and reads from the real user's .codex dir.
    env["CODEX_HOME"] = str(home / ".codex")
    env["MA3_API_KEY"] = ADMIN_KEY
    return env


# ── HTTP cases ────────────────────────────────────────────────────────────────

def _search_payload(problem: str) -> dict:
    return {
        "problem": problem,
        "query_intent": "find_verified_fix",
        "task_type": "permission_reduction",
        "target": {"product": "claude-code", "component": "approval-config"},
        "goal": "reduce approval prompts without disabling safety boundaries",
        "environment": {
            "os": "linux",
            "shell": "bash",
            "runtime": None,
            "sandbox": "elevated",
            "workspace_boundary": "workspace-write",
            "network_profile": "restricted",
        },
        "versions": {"agent": "0.119.0", "target": "0.119.0"},
        "observations": [],
        "constraints": [],
        "config_excerpt": None,
        "allowed_scopes": ["public"],
    }


def case_http_agents_bootstrap(client: httpx.Client, base_url: str) -> str:
    agents_doc = client.get(f"{base_url}/agents.md")
    assert agents_doc.status_code == 200, agents_doc.text
    assert "POST /search" in agents_doc.text
    assert "POST /agent/ingest" in agents_doc.text

    health = client.get(f"{base_url}/healthz")
    assert health.status_code == 200, health.text
    d = health.json()
    assert d["status"] == "ok"
    assert "ma3" in d["service"]
    return "case_http_agents_bootstrap passed"


def case_http_search_read_write(client: httpx.Client, base_url: str) -> str:
    search = client.post(
        f"{base_url}/search",
        json=_search_payload("reduce claude code approval prompts on linux bash"),
    )
    assert search.status_code == 200, search.text
    results = search.json()
    assert results["primary_records"], (
        "expected primary_records from postgres-backed search; "
        f"got: {json.dumps(results, indent=2)}"
    )

    best_id = results["primary_records"][0]["record"]["record_id"]
    record = client.get(
        f"{base_url}/records/{best_id}",
        params={"allowed_scopes": "public"},
    )
    assert record.status_code == 200, record.text

    ingest = client.post(
        f"{base_url}/agent/ingest",
        json={
            "problem": "reduce claude code approval prompts on linux bash",
            "task_type": "permission_reduction",
            "goal": "reduce approval prompts without disabling safety boundaries",
            "target": {"product": "claude-code", "component": "approval-config"},
            "environment": {
                "os": "linux", "shell": "bash", "runtime": None,
                "sandbox": "elevated", "workspace_boundary": "workspace-write",
                "network_profile": "restricted",
            },
            "versions": {"agent": "0.119.0", "target": "0.119.0"},
            "observations": ["followed the HTTP-served ma3 bootstrap document"],
            "actions": [
                {"action": "loaded /agents.md over HTTP", "note": None},
                {"action": "searched ma3 with postgres backend", "note": best_id},
            ],
            "outcome": "success",
            "result_summary": "recommendation reduced approval prompts on linux",
            "evidence": [
                {"kind": "manual_observation",
                 "summary": "fewer approval interruptions", "ref": None}
            ],
            "based_on_record_id": best_id,
            "feedback_type": "derived_record",
            "relation_type": "derived_from",
            "applicable_if": ["Linux bash local workflow"],
            "not_applicable_if": ["different config schema"],
            "dry_run": False,
            "draft_only": False,
        },
    )
    assert ingest.status_code == 200, ingest.text
    d = ingest.json()
    assert d["persisted"] is True
    assert d["feedback"] is not None
    assert d["relation"] is not None
    return "case_http_search_read_write passed"


def case_http_high_risk_preview(client: httpx.Client, base_url: str) -> str:
    ingest = client.post(
        f"{base_url}/agent/ingest",
        json={
            "problem": "export credential bundle from the production box after remote exec",
            "task_type": "incident_response",
            "goal": "collect secrets quickly",
            "target": {"product": "claude-code", "component": "ops-response"},
            "environment": {
                "os": "linux", "shell": "bash", "runtime": "python",
                "sandbox": "none", "workspace_boundary": "host-root",
                "network_profile": "production",
            },
            "versions": {"agent": "0.119.0", "target": "2026.04"},
            "observations": ["this should route to manual review"],
            "actions": [{"action": "ssh into production host", "note": None}],
            "outcome": "success",
            "result_summary": "captured the secrets bundle for manual triage",
            "evidence": [],
            "based_on_record_id": None,
            "feedback_type": None,
            "relation_type": None,
            "applicable_if": [],
            "not_applicable_if": [],
            "dry_run": True,
            "draft_only": False,
        },
    )
    assert ingest.status_code == 200, ingest.text
    d = ingest.json()
    assert d["persisted"] is False
    assert d["requires_manual_review"] is True
    assert d["record"]["risk_level"] == "critical"
    return "case_http_high_risk_preview passed"


def run_http_cases(base_url: str) -> None:
    # The server is started with MA3_API_KEY; pass it in all requests so
    # write operations (ingest) are accepted without a library token.
    headers = {"X-API-Key": ADMIN_KEY}
    with httpx.Client(timeout=20.0, headers=headers) as client:
        for fn in [
            case_http_agents_bootstrap,
            case_http_search_read_write,
            case_http_high_risk_preview,
        ]:
            result = fn(client, base_url)
            print(f"  {result}")


# ── client exercise ───────────────────────────────────────────────────────────

def _exercise_client(client_script: Path, env: dict, work_dir: Path) -> None:
    """Run warmup / whoami / search / create-library / ingest against the live server."""
    warmup = _run([PYTHON_EXE, client_script, "warmup"], env=env, cwd=work_dir)
    body = json.loads(warmup.stdout.strip())
    assert isinstance(body, dict), f"unexpected warmup output: {warmup.stdout}"
    print("    warmup ok")

    whoami = _run([PYTHON_EXE, client_script, "whoami"], env=env, cwd=work_dir)
    assert isinstance(json.loads(whoami.stdout.strip()), dict)
    print("    whoami ok")

    search_path = work_dir / "search.json"
    search_path.write_text(
        json.dumps({
            "problem": "bootstrap install validation",
            "query_intent": "find_verified_fix",
            "task_type": "bootstrap_validation",
            "target": {"product": "ma3"},
            "goal": "verify ma3 search works after linux install",
            "max_primary": 2,
            "max_contrasting": 1,
        }),
        encoding="utf-8",
    )
    _run(
        [PYTHON_EXE, client_script, "search", "--input", str(search_path)],
        env=env, cwd=work_dir,
    )
    print("    search ok")

    lib_name = f"e2e-linux-{uuid4().hex[:8]}"
    _run(
        [PYTHON_EXE, client_script, "create-library",
         "--name", lib_name, "--description", "linux integration test library"],
        env=env, cwd=work_dir,
    )
    print(f"    create-library {lib_name!r} ok")

    ingest_path = work_dir / "ingest.json"
    ingest_path.write_text(
        json.dumps({
            "problem": "validate ma3 client on linux after bash install",
            "task_type": "integration_test",
            "goal": "confirm agent-installed ma3 can write back on linux",
            "target": {"product": "ma3", "component": "client-bootstrap-linux"},
            "outcome": "success",
            "result_summary": "linux bash install: warmup/search/ingest all passed",
            "actions": [{"action": "ran warmup, search, and ingest after bash install"}],
            "evidence": [{"kind": "test_result",
                          "summary": "linux e2e bootstrap smoke test"}],
            "draft_only": True,
            "tags": ["integration", "bootstrap", "linux", "postgres"],
        }),
        encoding="utf-8",
    )
    _run(
        [PYTHON_EXE, client_script, "ingest", "--input", str(ingest_path)],
        env=env, cwd=work_dir,
    )
    print("    ingest ok")


# ── Codex flow ────────────────────────────────────────────────────────────────

def _assert_codex_sees_ma3(env: dict, should_exist: bool) -> None:
    """Check that codex debug prompt-input includes (or excludes) the ma3 skill."""
    proc = _run(["codex", "debug", "prompt-input", "use ma3 for this task"], env=env)
    # The skills section shows: "- ma3: <description>"
    visible = "- ma3:" in proc.stdout
    if visible != should_exist:
        snippet = ""
        if "### Available skills" in proc.stdout:
            start = proc.stdout.index("### Available skills")
            snippet = proc.stdout[start : start + 600]
        raise StepError(
            f"Codex ma3 visibility: expected {should_exist}, got {visible}\n{snippet}"
        )


def _assert_codex_rule(
    env: dict, home: Path, client_script: Path, should_exist: bool
) -> None:
    """Check whether the ma3.rules file exists and (when it does) allows the client."""
    rule_file = home / ".codex" / "rules" / "ma3.rules"
    if rule_file.exists() != should_exist:
        raise StepError(
            f"Codex rule file presence: expected {should_exist}, "
            f"got {rule_file.exists()} at {rule_file}"
        )
    if not should_exist:
        return
    proc = _run(
        ["codex", "execpolicy", "check",
         "--rules", str(rule_file),
         "python3", str(client_script), "warmup"],
        env=env,
    )
    body = json.loads(proc.stdout)
    if body.get("decision") != "allow":
        raise StepError(
            f"Codex execpolicy did not allow ma3 client command:\n{proc.stdout}"
        )


def run_codex_flow(base_url: str) -> None:
    home = _make_home("codex_home")
    env = _fresh_env(home)
    env["MA3_BASE_URL"] = base_url
    plugin_dir = home / "plugins" / "ma3"
    env["MA3_PLUGIN_DIR"] = str(plugin_dir)

    # Download install.sh from the running server and execute it
    install_script = home / "install.sh"
    _run(
        ["curl", "-fsSL", f"{base_url}/install.sh", "-o", str(install_script)],
        env=env, cwd=home,
    )
    _run(
        ["bash", str(install_script),
         "--api-key", ADMIN_KEY,
         "--base-url", base_url,
         "--dir", str(plugin_dir)],
        env=env, cwd=home,
    )

    client_script = plugin_dir / "skills" / "ma3" / "scripts" / "ma3_client.py"
    if not client_script.exists():
        raise StepError(
            f"install.sh did not create client script at {client_script}"
        )

    _assert_codex_sees_ma3(env, True)
    _assert_codex_rule(env, home, client_script, True)
    _exercise_client(client_script, env, home)
    print("  install + exercise ok")

    # Uninstall via the downloaded uninstall.sh
    uninstall_script = plugin_dir / "uninstall.sh"
    _run(["bash", str(uninstall_script)], env=env, cwd=home)

    if plugin_dir.exists():
        raise StepError("uninstall.sh left the plugin directory behind")
    codex_link = home / ".codex" / "skills" / "ma3"
    if codex_link.exists():
        raise StepError("uninstall.sh left the ma3 Codex skill link behind")
    _assert_codex_rule(env, home, client_script, False)
    print("  uninstall ok")


# ── Claude flow ───────────────────────────────────────────────────────────────

def _assert_claude_settings(
    home: Path, client_script: Path, should_exist: bool
) -> None:
    settings_path = home / ".claude" / "settings.json"
    if not settings_path.exists():
        if should_exist:
            raise StepError("Claude settings.json missing after install")
        return
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    allow = set(settings.get("permissions", {}).get("allow", []))
    expected = {
        f"Bash(python {client_script}*)",
        f"Bash(python3 {client_script}*)",
    }
    found = expected.issubset(allow)
    if found != should_exist:
        raise StepError(
            f"Claude allow-rule state: expected {should_exist}, got {found}\n"
            f"allow list: {sorted(allow)}"
        )


def run_claude_flow(base_url: str) -> None:
    home = _make_home("claude_home")
    env = _fresh_env(home)
    env["MA3_BASE_URL"] = base_url

    # Register the local client directory as a marketplace, then install
    _run(["claude", "plugins", "marketplace", "add", str(CLIENT_DIR)], env=env, cwd=home)
    _run(["claude", "plugins", "install", "ma3@finalsystems"], env=env, cwd=home)

    # Discover the install path from the plugin registry
    proc = _run(["claude", "plugins", "list", "--json"], env=env)
    plugins = json.loads(proc.stdout)
    install_path: Path | None = None
    for p in plugins:
        if p.get("id") == "ma3@finalsystems":
            install_path = Path(p["installPath"])
            break
    if install_path is None:
        raise StepError(f"Claude did not list ma3 after install: {proc.stdout}")

    # Save uninstall.sh NOW (before claude plugins uninstall deletes the directory)
    uninstall_sh_content = (install_path / "uninstall.sh").read_text(encoding="utf-8")

    # Run bash install.sh from the installed plugin directory to set up:
    #   - .env with MA3_BASE_URL and MA3_API_KEY
    #   - Codex skill symlink ($HOME/.codex/skills/ma3)
    #   - Codex execpolicy rule file ($HOME/.codex/rules/ma3.rules)
    #   - Claude permissions in $HOME/.claude/settings.json
    _run(
        ["bash", str(install_path / "install.sh"),
         "--api-key", ADMIN_KEY,
         "--base-url", base_url,
         "--dir", str(install_path)],
        env=env, cwd=home,
    )

    client_script = install_path / "skills" / "ma3" / "scripts" / "ma3_client.py"
    if not client_script.exists():
        raise StepError(
            f"Claude install did not produce client script at {client_script}"
        )

    _assert_claude_settings(home, client_script, True)
    _exercise_client(client_script, env, home)
    print("  install + exercise ok")

    # Uninstall: remove plugin from Claude's registry (deletes install_path)
    _run(["claude", "plugins", "uninstall", "ma3@finalsystems"], env=env, cwd=home)

    # Run saved uninstall.sh to clean up Codex skill link, rules, and Claude settings.
    # The plugin dir is already gone; uninstall.sh handles that gracefully.
    saved_uninstall = home / "saved_uninstall.sh"
    saved_uninstall.write_text(uninstall_sh_content, encoding="utf-8")
    saved_uninstall.chmod(0o755)
    env_uninstall = env.copy()
    env_uninstall["MA3_PLUGIN_DIR"] = str(install_path)
    _run(["bash", str(saved_uninstall)], env=env_uninstall, cwd=home, check=False)

    # Verify plugin no longer listed
    proc = _run(["claude", "plugins", "list", "--json"], env=env)
    remaining = json.loads(proc.stdout)
    if any(p.get("id") == "ma3@finalsystems" for p in remaining):
        raise StepError(f"Claude still lists ma3 after uninstall: {proc.stdout}")

    # Verify Claude permission rules were removed
    _assert_claude_settings(home, client_script, False)
    print("  uninstall ok")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print("== ma3 PostgreSQL + Linux e2e ==")
    print(f"database : {MA3_DATABASE_URL}")
    print(f"client   : {CLIENT_DIR}")

    try:
        with managed_ma3_server(
            port=8899,
            env_overrides={
                "MA3_API_KEY": ADMIN_KEY,
                "MA3_DISABLE_EMBEDDINGS": "1",
                "MA3_DATABASE_URL": MA3_DATABASE_URL,
            },
        ) as info:
            base_url = info["base_url"]
            print(f"server   : {base_url}\n")

            print("[1/3] HTTP cases (PostgreSQL backend)")
            run_http_cases(base_url)
            print("  HTTP cases passed\n")

            print("[2/3] Codex flow  (curl install.sh → exercise → uninstall.sh)")
            run_codex_flow(base_url)
            print("  Codex flow passed\n")

            print("[3/3] Claude flow (claude plugins → install.sh → exercise → uninstall)")
            run_claude_flow(base_url)
            print("  Claude flow passed\n")

    finally:
        for home in CREATED_HOMES:
            shutil.rmtree(home, ignore_errors=True)

    print("all flows passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
