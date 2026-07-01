#!/usr/bin/env python3
"""Sync ma3 client bundle. Reads ma3-client.env (agent-maintained), self-updates tooling from manifest."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import asdict
from pathlib import Path


def _load_core(lib_dir: Path):
    core_path = lib_dir / "ma3_sync_core.py"
    if not core_path.is_file():
        repo_core = Path(__file__).resolve().parents[1] / "lib" / "ma3_sync_core.py"
        if repo_core.is_file():
            core_path = repo_core
        else:
            raise SystemExit(f"ma3_sync_core.py not found in {lib_dir} (bootstrap from server /client/lib/)")
    spec = importlib.util.spec_from_file_location("ma3_sync_core", core_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {core_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ma3_sync_core"] = mod
    spec.loader.exec_module(mod)
    return mod


def _source_env() -> None:
    config = os.environ.get("MA3_CLIENT_CONFIG", str(Path.home() / ".ma3" / "ma3-client.env"))
    path = Path(config).expanduser()
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = os.path.expandvars(value.strip().strip('"').strip("'"))
        os.environ.setdefault(key, value)


class UrllibFetch:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def get_bytes(self, path: str) -> bytes:
        url = self.base_url + path
        req = urllib.request.Request(url, headers={"User-Agent": "ma3-client-sync/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()


def _paths_from_env(install_dir: Path) -> dict[str, Path]:
    return {
        "agent-onboarding.md": Path(os.environ.get("MA3_ONBOARDING_REL", "ma3-agent-onboarding.md")),
        "templates/ma3-agent-policy.mdc": Path(os.environ.get("MA3_POLICY_REL", "policy/ma3-agent-policy.mdc")),
        "mcp-tools.json": Path(os.environ.get("MA3_MCP_TOOLS_REL", "mcp-tools.json")),
    }


def main() -> int:
    _source_env()
    install_dir = Path(os.environ.get("MA3_CLIENT_INSTALL_DIR", Path.home() / ".ma3")).expanduser()
    state_path = Path(os.environ.get("MA3_CLIENT_STATE", install_dir / "ma3-client.json")).expanduser()
    bin_dir = Path(os.environ.get("MA3_BIN_DIR", install_dir / "bin")).expanduser()
    lib_dir = Path(os.environ.get("MA3_LIB_DIR", install_dir / "lib")).expanduser()
    base_url = os.environ.get("MA3_BASE_URL", "http://127.0.0.1:8000")

    core = _load_core(lib_dir)

    parser = argparse.ArgumentParser(description="Sync ma3 client bundle from server manifest")
    parser.add_argument("--base-url", default=base_url)
    parser.add_argument("--install-dir", type=Path, default=install_dir)
    parser.add_argument("--state-path", type=Path, default=state_path)
    parser.add_argument("--bin-dir", type=Path, default=bin_dir)
    parser.add_argument("--lib-dir", type=Path, default=lib_dir)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="Compare local state with remote manifest")
    sync_parser = sub.add_parser("sync", help="Self-update tooling + download changed bundle files")
    sync_parser.add_argument("--force", action="store_true")
    tooling_parser = sub.add_parser("self-update", help="Update sync scripts/libs only")
    tooling_parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    http = UrllibFetch(args.base_url)
    try:
        if args.command == "check":
            manifest = core.fetch_manifest(http)
            state = core.load_client_state(args.state_path)
            plan = core.plan_sync(state, manifest)
            print(
                json.dumps(
                    {
                        "needs_sync": bool(plan.files_to_update or plan.tooling_update),
                        "policy_refresh": plan.policy_refresh,
                        "mcp_reload": plan.mcp_reload,
                        "tooling_update": plan.tooling_update,
                        "files_to_update": plan.files_to_update,
                        "remote": {
                            "skill_bundle_version": manifest.get("skill_bundle_version"),
                            "tool_schema_version": manifest.get("tool_schema_version"),
                            "sync_tooling_version": manifest.get("sync_tooling_version"),
                        },
                        "local_state": state.to_json() if state else None,
                    },
                    indent=2,
                )
            )
            return 0 if not plan.files_to_update and not plan.tooling_update else 2

        if args.command == "self-update":
            manifest = core.fetch_manifest(http)
            updated = core.sync_tooling(
                http, manifest, bin_dir=args.bin_dir, lib_dir=args.lib_dir, force=args.force
            )
            print(json.dumps({"updated_tooling": updated}, indent=2))
            if updated:
                print("tooling updated; re-run this command from the installed script path", file=sys.stderr)
            return 0

        if args.command == "sync":
            state, plan = core.sync_client(
                http,
                base_url=args.base_url,
                state_path=args.state_path,
                install_dir=args.install_dir,
                install_paths=_paths_from_env(args.install_dir),
                bin_dir=args.bin_dir,
                lib_dir=args.lib_dir,
                force=args.force,
            )
            print(json.dumps({"state": state.to_json(), "plan": asdict(plan)}, indent=2))
            if plan.tooling_update:
                print("sync_tooling updated; re-run sync if this process used stale scripts", file=sys.stderr)
            if state.mcp_reload_required:
                print(
                    "mcp_reload_required: reload MCP in your agent runtime "
                    "(see MA3_MCP_RELOAD_NOTE in ma3-client.env)",
                    file=sys.stderr,
                )
            note = os.environ.get("MA3_POLICY_INSTALL_NOTE")
            if note:
                print(f"policy_install: {note}", file=sys.stderr)
            return 0
    except urllib.error.URLError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
