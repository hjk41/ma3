from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

from http_server_harness import TMP_ROOT, managed_ma3_server


ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT.parent / "client"
PYTHON_EXE = ROOT.parent / ".venv" / "Scripts" / "python.exe"
if not PYTHON_EXE.exists():
    PYTHON_EXE = Path(sys.executable)

ADMIN_KEY = "rc-e2e-admin-key"
CREATED_HOMES: list[Path] = []


class StepError(RuntimeError):
    pass


def _run(
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        args,
        cwd=str(cwd or ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode != 0:
        raise StepError(
            f"command failed ({proc.returncode}): {' '.join(args)}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc


def _powershell(
    command: str,
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return _run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        env=env,
        cwd=cwd,
        check=check,
    )


def _load_json(stdout: str) -> object:
    text = stdout.strip()
    if not text:
        raise StepError("expected JSON output, got empty output")
    return json.loads(text)


def _make_home(name: str) -> Path:
    root = TMP_ROOT / f"{name}_{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    CREATED_HOMES.append(root)
    return root


def _fresh_env(home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["MA3_API_KEY"] = ADMIN_KEY
    env["MA3_BASE_URL"] = env.get("MA3_BASE_URL", "")
    return env


def _assert_codex_sees_ma3(env: dict[str, str], should_exist: bool) -> None:
    proc = _run(
        ["codex.exe", "debug", "prompt-input", "use ma3 for this task"],
        env=env,
    )
    visible = "- ma3:ma3:" in proc.stdout or "- ma3:ma3 " in proc.stdout or "- ma3:ma3" in proc.stdout
    if visible != should_exist:
        raise StepError(
            f"unexpected Codex ma3 visibility: expected {should_exist}, got {visible}\n{proc.stdout}"
        )


def _assert_codex_rule(env: dict[str, str], home: Path, client_script: Path, should_exist: bool) -> None:
    rule_file = home / ".codex" / "rules" / "ma3.rules"
    if rule_file.exists() != should_exist:
        raise StepError(f"unexpected Codex rule file presence: expected {should_exist}, got {rule_file.exists()}")
    if not should_exist:
        return
    proc = _run(
        [
            "codex.exe",
            "execpolicy",
            "check",
            "--rules",
            str(rule_file),
            "python",
            str(client_script),
            "warmup",
        ],
        env=env,
    )
    body = _load_json(proc.stdout)
    if not isinstance(body, dict) or body.get("decision") != "allow":
        raise StepError(f"Codex execpolicy did not allow ma3 client command:\n{proc.stdout}")


def _assert_claude_plugin_list(env: dict[str, str], should_exist: bool) -> Path | None:
    proc = _run(["claude.exe", "plugins", "list", "--json"], env=env)
    payload = json.loads(proc.stdout)
    for plugin in payload:
        if plugin.get("id") == "ma3@finalsystems":
            if not should_exist:
                raise StepError(f"Claude still lists ma3 after uninstall: {proc.stdout}")
            return Path(plugin["installPath"])
    if should_exist:
        raise StepError(f"Claude does not list ma3 after install: {proc.stdout}")
    return None


def _assert_claude_rules(home: Path, client_script: Path, should_exist: bool) -> None:
    settings_path = home / ".claude" / "settings.json"
    if not settings_path.exists():
        if should_exist:
            raise StepError("Claude settings.json missing after install")
        return
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    allow = settings.get("permissions", {}).get("allow", [])
    expected = {
        f"Bash(python {client_script}*)",
        f"Bash(python3 {client_script}*)",
    }
    found = expected.issubset(set(allow))
    if found != should_exist:
        raise StepError(
            f"unexpected Claude allow-rule state: expected {should_exist}, got {found}\n{json.dumps(settings, ensure_ascii=False, indent=2)}"
        )


def _write_payload(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _exercise_client(client_script: Path, env: dict[str, str], work_dir: Path) -> None:
    warmup = _run([str(PYTHON_EXE), str(client_script), "warmup"], env=env, cwd=work_dir)
    warmup_body = _load_json(warmup.stdout)
    if not isinstance(warmup_body, dict):
        raise StepError(f"unexpected warmup output: {warmup.stdout}")

    whoami = _run([str(PYTHON_EXE), str(client_script), "whoami"], env=env, cwd=work_dir)
    whoami_body = _load_json(whoami.stdout)
    if not isinstance(whoami_body, dict):
        raise StepError(f"unexpected whoami output: {whoami.stdout}")

    search_path = _write_payload(
        work_dir / "search.json",
        {
            "problem": "bootstrap install validation",
            "query_intent": "find_verified_fix",
            "task_type": "bootstrap_validation",
            "target": {"product": "ma3"},
            "goal": "verify ma3 search works after install",
            "max_primary": 2,
            "max_contrasting": 1,
        },
    )
    _run(
        [str(PYTHON_EXE), str(client_script), "search", "--input", str(search_path)],
        env=env,
        cwd=work_dir,
    )

    _run(
        [
            str(PYTHON_EXE),
            str(client_script),
            "create-library",
            "--name",
            f"e2e-{uuid4().hex[:8]}",
            "--description",
            "integration test library",
        ],
        env=env,
        cwd=work_dir,
    )

    ingest_path = _write_payload(
        work_dir / "ingest.json",
        {
            "problem": "validate installed ma3 client",
            "task_type": "integration_test",
            "goal": "confirm agent-installed ma3 can write back",
            "target": {"product": "ma3", "component": "client-bootstrap"},
            "outcome": "success",
            "result_summary": "installed client completed warmup/search/ingest",
            "actions": [{"action": "ran warmup, search, and ingest after bootstrap"}],
            "evidence": [{"kind": "test_result", "summary": "end-to-end bootstrap smoke test"}],
            "draft_only": True,
            "tags": ["integration", "bootstrap", "install"],
        },
    )
    _run(
        [str(PYTHON_EXE), str(client_script), "ingest", "--input", str(ingest_path)],
        env=env,
        cwd=work_dir,
    )


def _remove_claude_rules(settings_path: Path, script_path: Path) -> None:
    if not settings_path.exists():
        return
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return
    allow = settings.setdefault("permissions", {}).setdefault("allow", [])
    rules = {
        f"Bash(python {script_path}*)",
        f"Bash(python3 {script_path}*)",
    }
    settings["permissions"]["allow"] = [rule for rule in allow if rule not in rules]
    settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")


def run_codex_flow(base_url: str) -> None:
    home = _make_home("codex_home")
    env = _fresh_env(home)
    env["MA3_BASE_URL"] = base_url
    plugin_dir = home / "plugins" / "ma3"
    env["MA3_PLUGIN_DIR"] = str(plugin_dir)

    install_script = home / "install.ps1"
    _powershell(
        f"Invoke-WebRequest '{base_url}/install.ps1' -OutFile '{install_script}' -UseBasicParsing",
        env=env,
        cwd=home,
    )
    _run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(install_script),
            "-ApiKey",
            ADMIN_KEY,
            "-BaseUrl",
            base_url,
            "-Dir",
            str(plugin_dir),
        ],
        env=env,
        cwd=home,
    )

    client_script = plugin_dir / "skills" / "ma3" / "scripts" / "ma3_client.py"
    if not client_script.exists():
        raise StepError(f"Codex install did not produce client script at {client_script}")

    _assert_codex_sees_ma3(env, True)
    _assert_codex_rule(env, home, client_script, True)
    _exercise_client(client_script, env, home)

    uninstall_script = plugin_dir / "uninstall.ps1"
    _run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(uninstall_script),
            "-Dir",
            str(plugin_dir),
        ],
        env=env,
        cwd=home,
    )

    if plugin_dir.exists():
        raise StepError("Codex uninstall left the plugin directory behind")
    codex_link = home / ".codex" / "skills" / "ma3"
    if codex_link.exists():
        raise StepError("Codex uninstall left the ma3 skill link behind")
    _assert_codex_rule(env, home, client_script, False)


def run_claude_flow(base_url: str) -> None:
    home = _make_home("claude_home")
    env = _fresh_env(home)
    env["MA3_BASE_URL"] = base_url

    _run(["claude.exe", "plugins", "marketplace", "add", str(CLIENT_DIR)], env=env, cwd=home)
    _run(["claude.exe", "plugins", "install", "ma3@finalsystems"], env=env, cwd=home)

    install_path = _assert_claude_plugin_list(env, True)
    assert install_path is not None

    _run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(install_path / "install.ps1"),
            "-ApiKey",
            ADMIN_KEY,
            "-BaseUrl",
            base_url,
            "-Dir",
            str(install_path),
        ],
        env=env,
        cwd=home,
    )

    client_script = install_path / "skills" / "ma3" / "scripts" / "ma3_client.py"
    if not client_script.exists():
        raise StepError(f"Claude install did not produce client script at {client_script}")

    # A fresh CLI invocation acts as the restart persistence check.
    _assert_claude_plugin_list(env, True)
    _assert_claude_rules(home, client_script, True)
    _exercise_client(client_script, env, home)

    _run(["claude.exe", "plugins", "uninstall", "ma3@finalsystems"], env=env, cwd=home)
    _remove_claude_rules(home / ".claude" / "settings.json", client_script)
    _assert_claude_plugin_list(env, False)
    _assert_claude_rules(home, client_script, False)


def main() -> int:
    print("== ma3 agent bootstrap e2e ==")
    try:
        with managed_ma3_server(
            port=8899,
            env_overrides={"MA3_API_KEY": ADMIN_KEY, "MA3_DISABLE_EMBEDDINGS": "1"},
        ) as info:
            base_url = info["base_url"]
            print(f"server: {base_url}")
            run_codex_flow(base_url)
            print("codex: install -> use -> uninstall ok")
            run_claude_flow(base_url)
            print("claude: install -> use -> uninstall ok")
    finally:
        for home in CREATED_HOMES:
            shutil.rmtree(home, ignore_errors=True)
    print("all flows passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
