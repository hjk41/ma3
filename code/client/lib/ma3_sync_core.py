"""Standalone ma3 client sync core (stdlib only). Used by server tests and ~/.ma3/bin scripts."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

TOOLING_PATHS: tuple[tuple[str, str], ...] = (
    ("scripts/sync_ma3_client.sh", "sync_ma3_client.sh"),
    ("scripts/sync_ma3_client.py", "sync_ma3_client.py"),
    ("lib/ma3_sync_core.py", "ma3_sync_core.py"),
)


class HttpFetch(Protocol):
    def get_bytes(self, path: str) -> bytes: ...


@dataclass(slots=True)
class SyncPlan:
    policy_refresh: bool
    mcp_reload: bool
    files_to_update: list[str]
    tooling_update: bool = False


@dataclass(slots=True)
class ClientState:
    base_url: str
    skill_bundle_version: str
    tool_schema_version: str
    synced_at: str
    files: dict[str, str]
    mcp_reload_required: bool = False
    sync_tooling_version: str | None = None

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "base_url": self.base_url,
            "skill_bundle_version": self.skill_bundle_version,
            "tool_schema_version": self.tool_schema_version,
            "synced_at": self.synced_at,
            "files": self.files,
            "mcp_reload_required": self.mcp_reload_required,
        }
        if self.sync_tooling_version:
            payload["sync_tooling_version"] = self.sync_tooling_version
        return payload

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ClientState:
        return cls(
            base_url=str(data.get("base_url") or ""),
            skill_bundle_version=str(data.get("skill_bundle_version") or "0.0.0"),
            tool_schema_version=str(data.get("tool_schema_version") or "ma3.mcp.v0"),
            synced_at=str(data.get("synced_at") or ""),
            files={str(k): str(v) for k, v in (data.get("files") or {}).items()},
            mcp_reload_required=bool(data.get("mcp_reload_required")),
            sync_tooling_version=data.get("sync_tooling_version"),
        )


DEFAULT_INSTALL_PATHS: dict[str, Path] = {
    "agent-onboarding.md": Path("ma3-agent-onboarding.md"),
    "templates/ma3-agent-policy.mdc": Path("policy/ma3-agent-policy.mdc"),
    "mcp-tools.json": Path("mcp-tools.json"),
}


def load_client_state(path: Path) -> ClientState | None:
    if not path.is_file():
        return None
    return ClientState.from_json(json.loads(path.read_text(encoding="utf-8")))


def write_client_state(path: Path, state: ClientState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_json(), indent=2) + "\n", encoding="utf-8")


def fetch_manifest(http: HttpFetch) -> dict[str, Any]:
    raw = http.get_bytes("/client/manifest.json")
    manifest = json.loads(raw.decode("utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be an object")
    return manifest


def _manifest_files(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in manifest.get("files", []):
        if isinstance(item, dict) and item.get("path"):
            out[str(item["path"])] = item
    return out


def plan_sync(state: ClientState | None, manifest: dict[str, Any]) -> SyncPlan:
    remote_skill = str(manifest.get("skill_bundle_version") or "0.0.0")
    remote_tool = str(manifest.get("tool_schema_version") or "ma3.mcp.v0")
    remote_files = {path: str(item["sha256"]) for path, item in _manifest_files(manifest).items()}

    tooling_update = False
    for manifest_path, _filename in TOOLING_PATHS:
        item = _manifest_files(manifest).get(manifest_path)
        if item and state and state.files.get(manifest_path) != item.get("sha256"):
            tooling_update = True
        if item and state is None:
            tooling_update = True

    if state is None:
        return SyncPlan(
            policy_refresh=True,
            mcp_reload=True,
            files_to_update=[p for p in remote_files if not p.startswith("scripts/") and not p.startswith("lib/")],
            tooling_update=True,
        )

    policy_refresh = state.skill_bundle_version != remote_skill or any(
        state.files.get(path) != sha
        for path, sha in remote_files.items()
        if path not in {"mcp-tools.json", *{t[0] for t in TOOLING_PATHS}}
    )
    mcp_reload = state.tool_schema_version != remote_tool or state.files.get("mcp-tools.json") != remote_files.get(
        "mcp-tools.json"
    )
    bundle_paths = {
        p
        for p in remote_files
        if not p.startswith("scripts/") and not p.startswith("lib/") and not p.startswith("templates/ma3-client")
    }
    files_to_update = [path for path in bundle_paths if state.files.get(path) != remote_files.get(path)]
    if state.skill_bundle_version != remote_skill:
        for path in bundle_paths:
            if path != "mcp-tools.json" and path not in files_to_update:
                files_to_update.append(path)
    if state.tool_schema_version != remote_tool and "mcp-tools.json" not in files_to_update:
        files_to_update.append("mcp-tools.json")

    for manifest_path, _ in TOOLING_PATHS:
        item = _manifest_files(manifest).get(manifest_path)
        if item and state.files.get(manifest_path) != item.get("sha256"):
            tooling_update = True

    return SyncPlan(
        policy_refresh=policy_refresh,
        mcp_reload=mcp_reload,
        files_to_update=files_to_update,
        tooling_update=tooling_update,
    )


def sync_tooling(
    http: HttpFetch,
    manifest: dict[str, Any],
    *,
    bin_dir: Path,
    lib_dir: Path,
    force: bool = False,
) -> list[str]:
    """Download sync scripts/libs from manifest. Returns updated manifest paths."""
    updated: list[str] = []
    files = _manifest_files(manifest)
    bin_dir.mkdir(parents=True, exist_ok=True)
    lib_dir.mkdir(parents=True, exist_ok=True)
    for manifest_path, filename in TOOLING_PATHS:
        item = files.get(manifest_path)
        if not item:
            continue
        url = str(item["url"])
        expected = str(item["sha256"])
        dest = (lib_dir if manifest_path.startswith("lib/") else bin_dir) / filename
        if not force and dest.is_file() and hashlib.sha256(dest.read_bytes()).hexdigest() == expected:
            continue
        content = http.get_bytes(url)
        digest = hashlib.sha256(content).hexdigest()
        if digest != expected:
            raise ValueError(f"sha256 mismatch for {manifest_path}")
        dest.write_bytes(content)
        if manifest_path.endswith(".sh"):
            dest.chmod(dest.stat().st_mode | 0o111)
        updated.append(manifest_path)
    return updated


def sync_client(
    http: HttpFetch,
    *,
    base_url: str,
    state_path: Path,
    install_dir: Path,
    install_paths: dict[str, Path] | None = None,
    bin_dir: Path | None = None,
    lib_dir: Path | None = None,
    force: bool = False,
    skip_tooling: bool = False,
) -> tuple[ClientState, SyncPlan]:
    manifest = fetch_manifest(http)
    current = load_client_state(state_path)
    plan = plan_sync(current, manifest)
    written: dict[str, str] = dict(current.files if current else {})

    if not skip_tooling and bin_dir is not None and lib_dir is not None and (force or plan.tooling_update):
        for path in sync_tooling(http, manifest, bin_dir=bin_dir, lib_dir=lib_dir, force=force):
            item = _manifest_files(manifest)[path]
            written[path] = str(item["sha256"])

    if not force and not plan.files_to_update and not plan.tooling_update:
        assert current is not None
        current.mcp_reload_required = False
        return current, plan

    paths = install_paths or DEFAULT_INSTALL_PATHS
    remote_files = {path: str(item["url"]) for path, item in _manifest_files(manifest).items()}

    targets = plan.files_to_update if not force else [
        p for p in remote_files if not p.startswith("scripts/") and not p.startswith("lib/")
    ]
    for rel_path in targets:
        if rel_path.startswith("scripts/") or rel_path.startswith("lib/"):
            continue
        if rel_path.endswith("ma3-client.env.example"):
            continue
        url = remote_files.get(rel_path)
        if not url:
            continue
        content = http.get_bytes(url)
        digest = hashlib.sha256(content).hexdigest()
        expected = _manifest_files(manifest).get(rel_path, {}).get("sha256")
        if expected and digest != expected:
            raise ValueError(f"sha256 mismatch for {rel_path}")
        dest_rel = paths.get(rel_path, Path(rel_path.replace("/", "-")))
        dest = install_dir / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        written[rel_path] = digest

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    state = ClientState(
        base_url=base_url.rstrip("/"),
        skill_bundle_version=str(manifest.get("skill_bundle_version") or "0.0.0"),
        tool_schema_version=str(manifest.get("tool_schema_version") or "ma3.mcp.v0"),
        synced_at=now,
        files=written,
        mcp_reload_required=plan.mcp_reload,
        sync_tooling_version=str(manifest.get("sync_tooling_version") or manifest.get("skill_bundle_version")),
    )
    write_client_state(state_path, state)
    return state, plan
