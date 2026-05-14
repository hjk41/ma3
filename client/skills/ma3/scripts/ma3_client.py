#!/usr/bin/env python3
"""
ma3 API client for the local Codex plugin.

Single endpoint: set MA3_BASE_URL / MA3_API_KEY / MA3_ADMIN_KEY /
  MA3_AUTH_MODE (or legacy YINGCHAN_* variants) in environment or a .env file.

Multiple endpoints: create an endpoints.json file in the plugin root:
  [
    {"name": "public",   "base_url": "https://hjk41.cc",
     "api_key": "tok_xxx", "admin_key": "admin_yyy"},
    {"name": "internal", "base_url": "https://internal.company.com", "api_key": "tok_zzz"}
  ]
  When endpoints.json is present it takes precedence over env vars.

Read/write commands (use MA3_API_KEY / api_key — library token on current hjk41.cc deployment):
  healthz                              -- probe all endpoints
  self-update                          -- download latest client/skill from server, or git pull fallback
  list      [--offset N] [--limit N] [--status active|draft|invalid|all] [--endpoint name]
  search    --input|--payload <json>   -- fan out to all, merge results
  get-record <id>                      -- fetch from first endpoint that has it
  ingest    --input|--payload <json>  [--endpoint name]
  knowledge --input|--payload <json>  [--endpoint name]

Admin commands (use MA3_ADMIN_KEY / admin_key):
  create-library  --name <name> [--description "..."] [--public] [--endpoint name]
  list-libraries  [--endpoint name]
  create-token    <library_id> [--label <label>]      [--endpoint name]
  list-tokens     <library_id>                        [--endpoint name]
  revoke-token    <library_id> <token_id>             [--endpoint name]
  reject          <record_id>  [--note "..."]         [--endpoint name]
  delete-record   <record_id>                         [--endpoint name]
"""
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Force UTF-8 output on Windows (default terminal uses GBK/cp936 which garbles Chinese)
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


DEFAULT_BASE_URL = "https://hjk41.cc"
CLIENT_VERSION = "0.4.0"

CLIENT_CONTEXTUAL_REDACTION_PATTERNS = {
    "windows_path": re.compile(r"\b[A-Za-z]:\\[^\s'\"<>|]+"),
    "unix_path": re.compile(r"(?<!\w)/(?:home|root|usr|etc|var|opt|tmp|srv|mnt)/[^\s'\"<>|]+"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}
CLIENT_SECRET_REDACTION_PATTERNS = {
    "secret_assignment": re.compile(
        r"(?i)\b(api[_-]?key|token|secret|password|session|access[_-]?key|private[_-]?key)\b\s*[:=]\s*([^\s,;\"']+)"
    ),
    "github_token": re.compile(r"\bghp_[A-Za-z0-9]{36,}\b"),
    "aws_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "long_token": re.compile(r"\b[0-9a-fA-F]{40,}\b"),
}


# ── helpers ────────────────────────────────────────────────────────────────

def _plugin_root() -> str:
    """Locate the plugin root by walking up from the script and looking for anchors.

    Anchors (in order of preference):
      1. A directory containing .codex-plugin/plugin.json
      2. A directory containing both .env and skills/

    Falls back to 3 levels up (original behaviour) if no anchor is found.
    """
    script_path = Path(os.path.abspath(__file__))
    for candidate in [script_path.parent, *script_path.parents]:
        if (candidate / ".codex-plugin" / "plugin.json").exists():
            return str(candidate)
        if (candidate / ".env").exists() and (candidate / "skills").exists():
            return str(candidate)
    # Fallback: 3 levels up from the script (skills/ma3/scripts/ -> plugin root)
    return str(script_path.parents[3])


def load_dotenv_file() -> None:
    env_path = os.path.join(_plugin_root(), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8-sig") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = value


def first_env(*names: str) -> Optional[str]:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


# ── endpoint model ──────────────────────────────────────────────────────────

@dataclass
class Endpoint:
    name: str
    base_url: str
    api_key: Optional[str] = None    # library token for normal read/write on current deployment
    admin_key: Optional[str] = None  # admin key — for library/token/record management
    auth_mode: str = "x-api-key"     # "x-api-key" | "bearer"
    library_id: Optional[str] = None # which library this token belongs to (client-side metadata)

    def _auth_headers(self, key: Optional[str]) -> Dict[str, str]:
        if not key:
            return {}
        mode = self.auth_mode.strip().lower()
        if mode == "bearer":
            return {"Authorization": f"Bearer {key}"}
        return {"X-API-Key": key}

    def headers(self, include_json: bool = False, use_admin: bool = False) -> Dict[str, str]:
        h: Dict[str, str] = {"User-Agent": "ma3-codex-plugin/0.1.0"}
        if include_json:
            h["Content-Type"] = "application/json"
        key = self.admin_key if use_admin else self.api_key
        h.update(self._auth_headers(key))
        return h

    def request(
        self, method: str, path: str, payload: Any = None, use_admin: bool = False
    ) -> Tuple[int, Any]:
        url = self.base_url.rstrip("/") + path
        data = None
        headers = self.headers(include_json=payload is not None, use_admin=use_admin)
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status, _parse_body(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, _parse_body(exc.read().decode("utf-8", errors="replace"))
        except urllib.error.URLError as exc:
            return 0, {"error": str(exc.reason)}


def _parse_body(body: str) -> Any:
    body = body.strip()
    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"raw": body}


# ── endpoint loading ────────────────────────────────────────────────────────

def load_endpoints() -> List[Endpoint]:
    """
    Priority:
      1. endpoints.json in plugin root
      2. MA3_BASE_URL env var  (+ MA3_API_KEY, MA3_ADMIN_KEY, MA3_AUTH_MODE)
      3. default URL
    """
    endpoints_path = os.path.join(_plugin_root(), "endpoints.json")
    if os.path.exists(endpoints_path):
        with open(endpoints_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list) or not data:
            raise SystemExit("endpoints.json must be a non-empty JSON array.")
        result = []
        for i, item in enumerate(data):
            if "base_url" not in item:
                raise SystemExit(f"endpoints.json entry {i} is missing 'base_url'.")
            result.append(Endpoint(
                name=item.get("name") or f"endpoint-{i}",
                base_url=item["base_url"].rstrip("/"),
                api_key=item.get("api_key") or None,
                admin_key=item.get("admin_key") or None,
                auth_mode=item.get("auth_mode", "x-api-key"),
                library_id=item.get("library_id") or None,
            ))
        return result

    base_url  = first_env("MA3_BASE_URL", "YINGCHAN_BASE_URL") or DEFAULT_BASE_URL
    api_key   = first_env("MA3_API_KEY",  "YINGCHAN_API_KEY")
    admin_key = first_env("MA3_ADMIN_KEY")
    auth_mode = first_env("MA3_AUTH_MODE", "YINGCHAN_AUTH_MODE") or "x-api-key"
    library_id = first_env("MA3_LIBRARY_ID")
    return [Endpoint(name="default", base_url=base_url.rstrip("/"),
                     api_key=api_key, admin_key=admin_key, auth_mode=auth_mode,
                     library_id=library_id)]


# ── endpoint selectors ──────────────────────────────────────────────────────

def _pick_one(endpoints: List[Endpoint], name: Optional[str], key_attr: str, label: str) -> Endpoint:
    """Return a single endpoint for a write/admin operation."""
    if name:
        for ep in endpoints:
            if ep.name == name:
                return ep
        available = [ep.name for ep in endpoints]
        raise SystemExit(f"Unknown endpoint '{name}'. Available: {available}")

    keyed = [ep for ep in endpoints if getattr(ep, key_attr)]
    if len(keyed) == 1:
        return keyed[0]
    if len(keyed) > 1:
        names = [ep.name for ep in keyed]
        raise SystemExit(
            f"Multiple endpoints have {label} configured ({names}). "
            "Use --endpoint <name> to specify which one."
        )
    # No key — try first endpoint anyway
    return endpoints[0]


def _pick_ingest_endpoint(endpoints: List[Endpoint], name: Optional[str]) -> Endpoint:
    return _pick_one(endpoints, name, "api_key", "API keys")


def _pick_admin_endpoint(endpoints: List[Endpoint], name: Optional[str]) -> Endpoint:
    return _pick_one(endpoints, name, "admin_key", "admin keys")


def _pick_by_library(endpoints: List[Endpoint], library_id: str) -> Endpoint:
    """Find the endpoint whose library_id matches. Requires api_key to be set."""
    matched = [ep for ep in endpoints if ep.library_id == library_id and ep.api_key]
    if not matched:
        raise SystemExit(
            f"No endpoint found with library_id='{library_id}'. "
            "Add library_id to endpoints.json or check for typos."
        )
    if len(matched) > 1:
        names = [ep.name for ep in matched]
        raise SystemExit(
            f"Multiple endpoints match library_id='{library_id}': {names}. "
            "Use --endpoint <name> to disambiguate."
        )
    return matched[0]


def _single_or_all(endpoints: List[Endpoint], name: Optional[str]) -> List[Endpoint]:
    if name:
        targets = [ep for ep in endpoints if ep.name == name]
        if not targets:
            raise SystemExit(f"Unknown endpoint '{name}'.")
        return targets
    return endpoints


# ── read/write commands ─────────────────────────────────────────────────────

def _parse_version(v: str) -> tuple:
    """Parse 'X.Y.Z' into (X, Y, Z) for comparison. Non-numeric parts become 0."""
    parts = []
    for p in v.split(".")[:3]:
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _version_update_reason(body: Dict[str, Any], include_recommended: bool = True) -> Optional[str]:
    """Return a human-readable update reason when this client is older than server policy."""
    min_v = body.get("min_client_version")
    if min_v and _parse_version(CLIENT_VERSION) < _parse_version(str(min_v)):
        return f"client {CLIENT_VERSION} < server requires {min_v}"
    rec_v = body.get("recommended_client_version")
    if include_recommended and rec_v and _parse_version(CLIENT_VERSION) < _parse_version(str(rec_v)):
        return f"client {CLIENT_VERSION} < server recommends {rec_v}"
    return None


def _request_with_retry(
    ep: "Endpoint",
    method: str,
    path: str,
    payload: Any = None,
    timeout: int = 30,
    retries: int = 1,
) -> Tuple[int, Any]:
    """Call ep.request with a custom timeout, retrying once on network/timeout errors."""
    import time as _time

    url = ep.base_url.rstrip("/") + path
    headers = ep.headers(include_json=payload is not None)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None

    last_status, last_body = 0, {}
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, _parse_body(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, _parse_body(exc.read().decode("utf-8", errors="replace"))
        except Exception as exc:
            last_status, last_body = 0, {"error": str(exc)}
            if attempt < retries:
                _time.sleep(2)

    return last_status, last_body


def cmd_healthz(endpoints: List[Endpoint]) -> int:
    results = {}
    overall_ok = True
    for ep in endpoints:
        status, body = ep.request("GET", "/healthz")
        ep_result: Dict[str, Any] = {"url": ep.base_url, "status": status, "body": body}
        if 200 <= status < 300:
            if "features" in body:
                ep_result["features"] = body["features"]
            ep_result["client_version"] = CLIENT_VERSION
            update_reason = _version_update_reason(body, include_recommended=True)
            if update_reason:
                key = (
                    "version_warning"
                    if "requires" in update_reason
                    else "recommended_version_warning"
                )
                ep_result[key] = f"{update_reason} — run: ma3_client.py self-update"
                overall_ok = False
        else:
            overall_ok = False
        results[ep.name] = ep_result
    results["plugin_root"] = _plugin_root()
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if overall_ok else 1


def cmd_self_update(endpoints: List[Endpoint], quiet: bool = False) -> int:
    """Update all client files from the server, or fall back to git pull."""
    # Try HTTP download from the first configured endpoint
    ep = endpoints[0]
    plugin_root = Path(_plugin_root())
    client_files: List[Tuple[str, str, Optional[str]]] = []
    manifest_status, manifest = ep.request("GET", "/client/manifest.json")
    if 200 <= manifest_status < 300 and isinstance(manifest, dict):
        for item in manifest.get("files", []):
            if not isinstance(item, dict):
                continue
            rel_path = str(item.get("path") or "")
            server_path = str(item.get("url") or "")
            sha256 = item.get("sha256")
            if (
                rel_path
                and server_path.startswith("/")
                and not rel_path.startswith("/")
                and ".." not in Path(rel_path).parts
            ):
                client_files.append((rel_path, server_path, str(sha256) if sha256 else None))

    if not client_files:
        client_files = [
            ("skills/ma3/scripts/ma3_client.py", "/client/ma3_client.py", None),
            ("skills/ma3/SKILL.md",              "/client/SKILL.md", None),
            ("AGENTS.md",                         "/client/AGENTS.md", None),
            ("examples/search-payload.example.json", "/client/examples/search-payload.example.json", None),
            ("examples/ingest-payload.example.json",  "/client/examples/ingest-payload.example.json", None),
        ]

    downloaded = 0
    errors = []
    for rel_path, server_path, expected_sha256 in client_files:
        dest = plugin_root / rel_path
        url = ep.base_url.rstrip("/") + server_path
        req = urllib.request.Request(url, headers={"User-Agent": "ma3-self-update/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                content = resp.read()
                if expected_sha256:
                    actual_sha256 = hashlib.sha256(content).hexdigest()
                    if actual_sha256 != expected_sha256:
                        raise RuntimeError(
                            f"sha256 mismatch: expected {expected_sha256}, got {actual_sha256}"
                        )
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)
                if not quiet:
                    print(f"  updated: {dest}")
                downloaded += 1
        except Exception as exc:
            errors.append(f"  WARN: {rel_path}: {exc}")

    if errors and not quiet:
        for msg in errors:
            print(msg, file=sys.stderr)

    if downloaded > 0:
        if not quiet:
            print(f"self-update complete ({downloaded} files refreshed from {ep.base_url})")
        return 0

    # Nothing downloaded from server — fall back to git pull
    if not quiet:
        print("Could not reach server; trying git pull ...", file=sys.stderr)
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(Path(__file__).resolve().parent),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        if not quiet:
            print("ERROR: not a git repository either — cannot self-update.", file=sys.stderr)
        return 1
    repo_root = result.stdout.strip()
    if not quiet:
        print(f"Updating ma3 at {repo_root} ...")
    pull = subprocess.run(
        ["git", "pull", "origin", "main"],
        cwd=repo_root,
        capture_output=quiet,
        text=quiet,
    )
    return pull.returncode


def cmd_list_records(
    endpoints: List[Endpoint],
    offset: int,
    limit: int,
    status: str,
    endpoint_name: Optional[str],
) -> int:
    targets = _single_or_all(endpoints, endpoint_name)
    path = f"/records?offset={offset}&limit={limit}&status={status}"
    all_results: Dict[str, Any] = {}
    for ep in targets:
        status_code, body = ep.request("GET", path)
        all_results[ep.name] = {"status": status_code, "body": body}

    if len(targets) == 1:
        body = all_results[targets[0].name]["body"]
        print(json.dumps(body, ensure_ascii=False, indent=2))
        return 0 if all_results[targets[0].name]["status"] < 300 else 1

    print(json.dumps(all_results, ensure_ascii=False, indent=2))
    return 0


def cmd_search(endpoints: List[Endpoint], payload: Any) -> int:
    """Fan out to all endpoints, merge and deduplicate by record_id."""
    primary: List[Any]     = []
    contrasting: List[Any] = []
    seen: set = set()
    errors: Dict[str, Any] = {}

    for ep in endpoints:
        status, body = _request_with_retry(ep, "POST", "/search", payload, timeout=30, retries=1)
        if not (200 <= status < 300):
            errors[ep.name] = {"status": status, "body": body}
            continue
        for match in body.get("primary_records", []):
            rid = match.get("record", {}).get("record_id")
            if rid and rid in seen:
                continue
            if rid:
                seen.add(rid)
            match.setdefault("_source_endpoint", ep.name)
            primary.append(match)
        for match in body.get("contrasting_records", []):
            rid = match.get("record", {}).get("record_id")
            if rid and rid in seen:
                continue
            if rid:
                seen.add(rid)
            match.setdefault("_source_endpoint", ep.name)
            contrasting.append(match)

    primary.sort(key=lambda m: m.get("match_score", 0), reverse=True)
    contrasting.sort(key=lambda m: m.get("match_score", 0), reverse=True)

    result: Dict[str, Any] = {
        "primary_records": primary,
        "contrasting_records": contrasting,
    }
    if errors:
        result["_endpoint_errors"] = errors

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if primary or contrasting else (1 if errors else 0)


def cmd_warmup(endpoints: List[Endpoint]) -> int:
    """Verify full chain: healthz + minimal search on each endpoint."""
    import time
    results: Dict[str, Any] = {}
    overall_ok = True

    for ep in endpoints:
        ep_result: Dict[str, Any] = {"url": ep.base_url}

        # healthz
        status, body = ep.request("GET", "/healthz")
        ep_result["healthz"] = {"status": status, "ok": 200 <= status < 300}
        if not (200 <= status < 300):
            overall_ok = False
            results[ep.name] = ep_result
            continue
        if "features" in body:
            ep_result["features"] = body["features"]

        update_reason = _version_update_reason(body, include_recommended=True)
        if update_reason:
            key = "version_warning" if "requires" in update_reason else "recommended_version_warning"
            ep_result[key] = update_reason
            if os.environ.get("MA3_DISABLE_AUTO_UPDATE") == "1":
                ep_result["self_update_skipped"] = "MA3_DISABLE_AUTO_UPDATE=1"
            else:
                update_rc = cmd_self_update([ep], quiet=True)
                ep_result["self_update_performed"] = update_rc == 0
                ep_result["self_update_returncode"] = update_rc
                ep_result["rerun_required"] = update_rc == 0
                if update_rc == 0:
                    ep_result["next_step"] = (
                        "Rerun warmup so the agent uses the refreshed client/skill files."
                    )
            overall_ok = False
            results[ep.name] = ep_result
            continue

        # minimal search
        minimal_payload = {
            "problem": "warmup ping",
            "query_intent": "find_verified_fix",
            "task_type": "warmup",
            "target": {"product": "ma3"},
            "goal": "verify the search endpoint accepts a minimal valid payload",
            "max_primary": 1,
            "max_contrasting": 0,
        }
        t0 = time.monotonic()
        status, sbody = _request_with_retry(ep, "POST", "/search", minimal_payload, timeout=30, retries=1)
        elapsed = round(time.monotonic() - t0, 2)
        ep_result["search"] = {
            "status": status,
            "ok": 200 <= status < 300,
            "elapsed_s": elapsed,
        }
        if not (200 <= status < 300):
            overall_ok = False

        results[ep.name] = ep_result

    results["plugin_root"] = _plugin_root()
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if overall_ok else 1


def cmd_get_record(endpoints: List[Endpoint], record_id: str) -> int:
    """Try each endpoint in order; return the first hit."""
    for ep in endpoints:
        status, body = ep.request("GET", f"/records/{record_id}")
        if 200 <= status < 300:
            body["_source_endpoint"] = ep.name
            print(json.dumps(body, ensure_ascii=False, indent=2))
            return 0
    print(json.dumps({"error": f"record '{record_id}' not found in any endpoint"},
                     ensure_ascii=False, indent=2), file=sys.stderr)
    return 1


def _walk_strings(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        out: List[str] = []
        for item in value:
            out.extend(_walk_strings(item))
        return out
    if isinstance(value, dict):
        out = []
        for item in value.values():
            out.extend(_walk_strings(item))
        return out
    return []


def redaction_hits(payload: Any) -> Dict[str, int]:
    hits: Dict[str, int] = {}
    for text in _walk_strings(payload):
        for name, pattern in {
            **CLIENT_CONTEXTUAL_REDACTION_PATTERNS,
            **CLIENT_SECRET_REDACTION_PATTERNS,
        }.items():
            count = len(pattern.findall(text))
            if count:
                hits[name] = hits.get(name, 0) + count
    return hits


def apply_redaction_mode(payload: Any, redaction_mode: Optional[str]) -> Any:
    if not isinstance(payload, dict):
        return payload
    if "redaction_mode" in payload:
        return payload
    mode = redaction_mode
    if mode is None:
        hits = redaction_hits(payload)
        if hits and sys.stdin.isatty() and sys.stderr.isatty():
            summary = ", ".join(f"{key}={value}" for key, value in sorted(hits.items()))
            print(
                f"ma3 detected contextual/sensitive values ({summary}). Choose redaction mode: "
                "[a]uto redact detected values, [n]one keep detected values. [a/n] ",
                end="",
                file=sys.stderr,
                flush=True,
            )
            answer = sys.stdin.readline().strip().lower()
            mode = "none" if answer in {"n", "no", "none", "全保留"} else "auto"
        else:
            mode = "auto"
    payload = dict(payload)
    payload["redaction_mode"] = mode
    return payload


def cmd_ingest(
    endpoints: List[Endpoint],
    payload: Any,
    endpoint_name: Optional[str],
    library_id: Optional[str] = None,
    redaction_mode: Optional[str] = None,
) -> int:
    payload = apply_redaction_mode(payload, redaction_mode)
    if library_id:
        ep = _pick_by_library(endpoints, library_id)
    else:
        ep = _pick_ingest_endpoint(endpoints, endpoint_name)
    status, body = ep.request("POST", "/agent/ingest", payload)
    result: Dict[str, Any] = {"status": status, "_endpoint": ep.name, "body": body}
    if ep.library_id:
        result["_library_id"] = ep.library_id
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if 200 <= status < 300 else 1


def cmd_knowledge(
    endpoints: List[Endpoint],
    payload: Any,
    endpoint_name: Optional[str],
    redaction_mode: Optional[str] = None,
) -> int:
    """POST /knowledge — writes a Q&A-style knowledge record to one endpoint."""
    payload = apply_redaction_mode(payload, redaction_mode)
    ep = _pick_ingest_endpoint(endpoints, endpoint_name)
    status, body = ep.request("POST", "/knowledge", payload=payload)
    result = {"endpoint": ep.name, "status": status, "body": body}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if 200 <= status < 300 else 1


def cmd_v2_request(
    endpoints: List[Endpoint],
    method: str,
    path: str,
    endpoint_name: Optional[str],
    payload: Any = None,
    require_write: bool = False,
    redaction_mode: Optional[str] = None,
) -> int:
    """Call a v2 endpoint on one selected endpoint.

    v2 commands are intentionally single-endpoint: agent workflows should avoid
    fan-out surprises when writing reports or reading case timelines.
    """
    ep = _pick_ingest_endpoint(endpoints, endpoint_name) if require_write else _single_or_all(endpoints, endpoint_name)[0]
    if require_write and payload is not None:
        payload = apply_redaction_mode(payload, redaction_mode)
    status, body = ep.request(method, path, payload=payload)
    result = {"endpoint": ep.name, "status": status, "body": body}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if 200 <= status < 300 else 1


# ── admin commands ──────────────────────────────────────────────────────────

def _admin_request(
    endpoints: List[Endpoint],
    method: str,
    path: str,
    endpoint_name: Optional[str],
    payload: Any = None,
) -> int:
    ep = _pick_admin_endpoint(endpoints, endpoint_name)
    status, body = ep.request(method, path, payload=payload, use_admin=True)
    print(json.dumps(body, ensure_ascii=False, indent=2))
    return 0 if 200 <= status < 300 else 1


def _write_or_admin_request(
    endpoints: List[Endpoint],
    method: str,
    path: str,
    endpoint_name: Optional[str],
    payload: Any = None,
) -> int:
    """Use library token (api_key) if available; fall back to admin key on 401/403.

    This allows library admin tokens to perform operations, while automatically
    falling back to the global admin key when the library token lacks permission.
    The explicit note matters because users often confuse the normal library token
    with the separate admin key during first-time setup.
    """
    ep = _pick_one(endpoints, endpoint_name, "api_key", "API keys")
    if ep.api_key:
        status, body = ep.request(method, path, payload=payload, use_admin=False)
        if status in (401, 403) and ep.admin_key:
            # api_key lacks permission — fall back to admin key
            status, body = ep.request(method, path, payload=payload, use_admin=True)
    elif ep.admin_key:
        status, body = ep.request(method, path, payload=payload, use_admin=True)
    else:
        body = {"error": "no api_key or admin_key configured for this endpoint"}
        status = 0
    print(json.dumps(body, ensure_ascii=False, indent=2))
    return 0 if 200 <= status < 300 else 1


def cmd_create_library(
    endpoints: List[Endpoint],
    name: str,
    description: str,
    is_public: bool,
    parent: Optional[str],
    endpoint_name: Optional[str],
) -> int:
    payload: Dict[str, Any] = {"name": name, "description": description, "is_public": is_public}
    if parent:
        payload["parent_library_id"] = parent
    return _write_or_admin_request(endpoints, "POST", "/libraries", endpoint_name, payload)


def cmd_delete_library(
    endpoints: List[Endpoint],
    library_id: str,
    endpoint_name: Optional[str],
) -> int:
    return _write_or_admin_request(endpoints, "DELETE", f"/libraries/{library_id}", endpoint_name)


def cmd_create_invite(
    endpoints: List[Endpoint],
    endpoint_name: Optional[str],
) -> int:
    return _admin_request(endpoints, "POST", "/invites", endpoint_name)


def cmd_use_invite(
    endpoints: List[Endpoint],
    code: str,
    name: str,
    description: str,
    endpoint_name: Optional[str],
) -> int:
    """POST /libraries/from-invite — no auth required."""
    targets = _single_or_all(endpoints, endpoint_name)
    ep = targets[0]
    payload = {"code": code, "name": name, "description": description}
    status, body = ep.request("POST", "/libraries/from-invite", payload=payload)
    print(json.dumps(body, ensure_ascii=False, indent=2))
    return 0 if 200 <= status < 300 else 1


def cmd_list_libraries(endpoints: List[Endpoint], endpoint_name: Optional[str]) -> int:
    targets = _single_or_all(endpoints, endpoint_name)
    results: Dict[str, Any] = {}
    for ep in targets:
        status, body = ep.request("GET", "/libraries", use_admin=bool(ep.admin_key))
        results[ep.name] = body
    if len(targets) == 1:
        print(json.dumps(results[targets[0].name], ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


def cmd_create_token(
    endpoints: List[Endpoint],
    library_id: str,
    label: str,
    role: str,
    endpoint_name: Optional[str],
) -> int:
    payload = {"label": label, "role": role}
    return _write_or_admin_request(endpoints, "POST", f"/libraries/{library_id}/tokens",
                                   endpoint_name, payload)


def cmd_list_tokens(
    endpoints: List[Endpoint], library_id: str, endpoint_name: Optional[str]
) -> int:
    return _write_or_admin_request(endpoints, "GET", f"/libraries/{library_id}/tokens", endpoint_name)


def cmd_revoke_token(
    endpoints: List[Endpoint],
    library_id: str,
    token_id: str,
    endpoint_name: Optional[str],
) -> int:
    return _write_or_admin_request(endpoints, "DELETE",
                                   f"/libraries/{library_id}/tokens/{token_id}", endpoint_name)


def cmd_whoami(endpoints: List[Endpoint], endpoint_name: Optional[str]) -> int:
    """Show identity info for all configured credentials on each endpoint."""
    targets = _single_or_all(endpoints, endpoint_name)
    results: Dict[str, Any] = {}
    for ep in targets:
        ep_result: Dict[str, Any] = {}
        if ep.admin_key:
            _, body = ep.request("GET", "/libraries/whoami", use_admin=True)
            ep_result["admin_key"] = body
        if ep.api_key:
            _, body = ep.request("GET", "/libraries/whoami")
            ep_result["api_key"] = body
        if not ep.admin_key and not ep.api_key:
            _, body = ep.request("GET", "/libraries/whoami")
            ep_result["anonymous"] = body
        results[ep.name] = ep_result
    if len(targets) == 1:
        print(json.dumps(results[targets[0].name], ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


def cmd_promote(
    endpoints: List[Endpoint],
    record_id: str,
    note: Optional[str],
    endpoint_name: Optional[str],
) -> int:
    payload = {"review_note": note} if note else {}
    return _write_or_admin_request(endpoints, "PATCH", f"/records/{record_id}/promote",
                                   endpoint_name, payload)


def cmd_reject(
    endpoints: List[Endpoint],
    record_id: str,
    note: Optional[str],
    endpoint_name: Optional[str],
) -> int:
    payload = {"review_note": note} if note else {}
    return _write_or_admin_request(endpoints, "PATCH", f"/records/{record_id}/reject",
                                   endpoint_name, payload)


def cmd_delete_record(
    endpoints: List[Endpoint],
    record_id: str,
    endpoint_name: Optional[str],
) -> int:
    return _write_or_admin_request(endpoints, "DELETE", f"/records/{record_id}", endpoint_name)


# ── payload loading ─────────────────────────────────────────────────────────

def load_json_payload(input_path: Optional[str], payload_text: Optional[str]) -> Any:
    if input_path and payload_text:
        raise SystemExit("Provide only one of --input or --payload.")
    if input_path:
        with open(input_path, "r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    if payload_text:
        return json.loads(payload_text)
    raise SystemExit("Either --input or --payload is required.")


# ── main ────────────────────────────────────────────────────────────────────

def main() -> int:
    load_dotenv_file()
    endpoints = load_endpoints()

    parser = argparse.ArgumentParser(
        description="ma3 API client. Configure via endpoints.json or MA3_* env vars."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── read/write ──
    subparsers.add_parser("healthz", help="Probe all configured endpoints.")
    subparsers.add_parser("self-update", help="Re-download all client files from server (or git pull).")
    subparsers.add_parser("warmup", help="healthz + minimal search — verify full chain before use.")

    list_p = subparsers.add_parser("list", help="GET /records — paginated browse.")
    list_p.add_argument("--offset",   type=int, default=0,  help="Start offset (default 0).")
    list_p.add_argument("--limit",    type=int, default=20, help="Page size 1-100 (default 20).")
    list_p.add_argument("--status",   default="active",     help="active (default) | draft | invalid | all.")
    list_p.add_argument("--endpoint", help="Target a specific endpoint by name.")

    search_p = subparsers.add_parser("search", help="POST /search — fans out to all endpoints.")
    search_p.add_argument("--input",   help="Path to a JSON payload file.")
    search_p.add_argument("--payload", help="Inline JSON payload.")

    get_p = subparsers.add_parser("get-record", help="GET /records/{id} — tries all endpoints.")
    get_p.add_argument("record_id", help="Record ID to fetch.")

    ingest_p = subparsers.add_parser("ingest", help="POST /agent/ingest — writes to one endpoint.")
    ingest_p.add_argument("--input",    help="Path to a JSON payload file.")
    ingest_p.add_argument("--payload",  help="Inline JSON payload.")
    ingest_p.add_argument("--endpoint", help="Endpoint name (required when multiple have API keys).")
    ingest_p.add_argument("--library",  help="Target by library_id (alternative to --endpoint).")
    ingest_p.add_argument("--redaction-mode", choices=["auto", "none"], help="auto redacts detected values; none preserves them after user confirmation.")

    know_p = subparsers.add_parser("knowledge", help="POST /knowledge — writes a knowledge record to one endpoint.")
    know_p.add_argument("--input",    help="Path to a JSON payload file.")
    know_p.add_argument("--payload",  help="Inline JSON payload.")
    know_p.add_argument("--endpoint", help="Endpoint name (required when multiple have API keys).")
    know_p.add_argument("--redaction-mode", choices=["auto", "none"], help="auto redacts detected values; none preserves them after user confirmation.")

    # ── v2 agent/tool workflow wrappers ──
    v2ctx_p = subparsers.add_parser("v2-context", help="POST /v2/agent/context — one-call agent retrieval context.")
    v2ctx_p.add_argument("--input", help="Path to a JSON payload file.")
    v2ctx_p.add_argument("--payload", help="Inline JSON payload.")
    v2ctx_p.add_argument("--endpoint", help="Target endpoint by name.")

    v2rep_p = subparsers.add_parser("v2-report", help="POST /v2/agent/report — write an agent result with case assignment.")
    v2rep_p.add_argument("--input", help="Path to a JSON payload file.")
    v2rep_p.add_argument("--payload", help="Inline JSON payload.")
    v2rep_p.add_argument("--endpoint", help="Target endpoint by name.")
    v2rep_p.add_argument("--redaction-mode", choices=["auto", "none"], help="auto redacts detected values; none preserves them after user confirmation.")

    v2case_p = subparsers.add_parser("v2-case", help="GET /v2/cases/{id} — read a v2 case timeline.")
    v2case_p.add_argument("case_id", help="Case ID to fetch.")
    v2case_p.add_argument("--endpoint", help="Target endpoint by name.")

    v2cases_p = subparsers.add_parser("v2-cases", help="GET /v2/cases — browse v2 cases.")
    v2cases_p.add_argument("--state", help="Optional case state filter.")
    v2cases_p.add_argument("--limit", type=int, default=20)
    v2cases_p.add_argument("--offset", type=int, default=0)
    v2cases_p.add_argument("--endpoint", help="Target endpoint by name.")

    v2exp_p = subparsers.add_parser("v2-explain", help="POST /v2/search/explain — explain v2 retrieval/ranking.")
    v2exp_p.add_argument("--input", help="Path to a JSON payload file.")
    v2exp_p.add_argument("--payload", help="Inline JSON payload.")
    v2exp_p.add_argument("--endpoint", help="Target endpoint by name.")

    v2doc_p = subparsers.add_parser("v2-doctor", help="GET /v2/doctor — server-side v2 diagnostics.")
    v2doc_p.add_argument("--endpoint", help="Target endpoint by name.")

    v2stats_p = subparsers.add_parser("v2-stats", help="GET /v2/stats/{name} — overview/search/knowledge-quality/quality-actions.")
    v2stats_p.add_argument("name", choices=["overview", "search", "knowledge-quality", "quality-actions"])
    v2stats_p.add_argument("--endpoint", help="Target endpoint by name.")

    # ── admin ──
    cl_p = subparsers.add_parser("create-library", help="POST /libraries — create a library. (admin or library admin for child)")
    cl_p.add_argument("--name",        required=True, help="Library name.")
    cl_p.add_argument("--description", default="",    help="Optional description.")
    cl_p.add_argument("--public",      action="store_true", help="Make library publicly readable.")
    cl_p.add_argument("--parent",      default=None,  help="Parent library ID (omit for root; library admin always creates child under own library).")
    cl_p.add_argument("--endpoint",    help="Target endpoint by name.")

    dl_p = subparsers.add_parser("delete-library", help="DELETE /libraries/{id} — delete a library and its contents. (library admin or global admin)")
    dl_p.add_argument("library_id", help="Library ID to delete.")
    dl_p.add_argument("--endpoint", help="Target endpoint by name.")

    ll_p = subparsers.add_parser("list-libraries", help="GET /libraries — list libraries. (admin sees all)")
    ll_p.add_argument("--endpoint", help="Target endpoint by name.")

    ci_p = subparsers.add_parser("create-invite", help="POST /invites — create a one-time invite code. (global admin only)")
    ci_p.add_argument("--endpoint", help="Target endpoint by name.")

    ui_p = subparsers.add_parser("use-invite", help="POST /libraries/from-invite — create a personal library from an invite code.")
    ui_p.add_argument("--code",        required=True, help="Invite code.")
    ui_p.add_argument("--name",        required=True, help="Name for your personal library.")
    ui_p.add_argument("--description", default="",    help="Optional description.")
    ui_p.add_argument("--endpoint",    help="Target endpoint by name.")

    ct_p = subparsers.add_parser("create-token", help="POST /libraries/{id}/tokens — create a token. (library admin or global admin)")
    ct_p.add_argument("library_id", help="Library ID.")
    ct_p.add_argument("--label",    default="default", help="Token label (default: 'default').")
    ct_p.add_argument("--role",     default="writer",  help="Token role: writer (default) or admin.")
    ct_p.add_argument("--endpoint", help="Target endpoint by name.")

    lt_p = subparsers.add_parser("list-tokens", help="GET /libraries/{id}/tokens — list tokens. (library admin or global admin)")
    lt_p.add_argument("library_id", help="Library ID.")
    lt_p.add_argument("--endpoint", help="Target endpoint by name.")

    rt_p = subparsers.add_parser("revoke-token", help="DELETE /libraries/{id}/tokens/{tid}. (library admin or global admin)")
    rt_p.add_argument("library_id", help="Library ID.")
    rt_p.add_argument("token_id",   help="Token ID to revoke.")
    rt_p.add_argument("--endpoint", help="Target endpoint by name.")

    wm_p = subparsers.add_parser("whoami", help="GET /libraries/whoami — show identity for current credentials.")
    wm_p.add_argument("--endpoint", help="Target endpoint by name.")

    pr_p = subparsers.add_parser("promote", help="PATCH /records/{id}/promote — approve a legacy draft if needed. (admin)")
    pr_p.add_argument("record_id", help="Record ID to promote.")
    pr_p.add_argument("--note",    help="Optional review note.", default=None)
    pr_p.add_argument("--endpoint", help="Target endpoint by name.")

    rj_p = subparsers.add_parser("reject", help="PATCH /records/{id}/reject — reject a record. (admin)")
    rj_p.add_argument("record_id", help="Record ID to reject.")
    rj_p.add_argument("--note",    help="Optional review note.", default=None)
    rj_p.add_argument("--endpoint", help="Target endpoint by name.")

    dr_p = subparsers.add_parser("delete-record", help="DELETE /records/{id} — permanently delete a record. (admin)")
    dr_p.add_argument("record_id", help="Record ID to delete.")
    dr_p.add_argument("--endpoint", help="Target endpoint by name.")

    args = parser.parse_args()
    ep_name = getattr(args, "endpoint", None)

    if args.command == "healthz":
        return cmd_healthz(endpoints)
    if args.command == "self-update":
        return cmd_self_update(endpoints)
    if args.command == "warmup":
        return cmd_warmup(endpoints)
    if args.command == "list":
        return cmd_list_records(endpoints, args.offset, args.limit, args.status, ep_name)
    if args.command == "search":
        return cmd_search(endpoints, load_json_payload(args.input, args.payload))
    if args.command == "get-record":
        return cmd_get_record(endpoints, args.record_id)
    if args.command == "ingest":
        return cmd_ingest(
            endpoints,
            load_json_payload(args.input, args.payload),
            ep_name,
            getattr(args, "library", None),
            getattr(args, "redaction_mode", None),
        )
    if args.command == "knowledge":
        return cmd_knowledge(
            endpoints,
            load_json_payload(args.input, args.payload),
            ep_name,
            getattr(args, "redaction_mode", None),
        )
    if args.command == "v2-context":
        return cmd_v2_request(endpoints, "POST", "/v2/agent/context", ep_name, load_json_payload(args.input, args.payload))
    if args.command == "v2-report":
        return cmd_v2_request(
            endpoints,
            "POST",
            "/v2/agent/report",
            ep_name,
            load_json_payload(args.input, args.payload),
            require_write=True,
            redaction_mode=getattr(args, "redaction_mode", None),
        )
    if args.command == "v2-case":
        return cmd_v2_request(endpoints, "GET", f"/v2/cases/{args.case_id}", ep_name)
    if args.command == "v2-cases":
        path = f"/v2/cases?limit={args.limit}&offset={args.offset}"
        if args.state:
            path += f"&state={args.state}"
        return cmd_v2_request(endpoints, "GET", path, ep_name)
    if args.command == "v2-explain":
        return cmd_v2_request(endpoints, "POST", "/v2/search/explain", ep_name, load_json_payload(args.input, args.payload))
    if args.command == "v2-doctor":
        return cmd_v2_request(endpoints, "GET", "/v2/doctor", ep_name)
    if args.command == "v2-stats":
        return cmd_v2_request(endpoints, "GET", f"/v2/stats/{args.name}", ep_name)
    if args.command == "create-library":
        return cmd_create_library(endpoints, args.name, args.description, args.public, args.parent, ep_name)
    if args.command == "delete-library":
        return cmd_delete_library(endpoints, args.library_id, ep_name)
    if args.command == "list-libraries":
        return cmd_list_libraries(endpoints, ep_name)
    if args.command == "create-invite":
        return cmd_create_invite(endpoints, ep_name)
    if args.command == "use-invite":
        return cmd_use_invite(endpoints, args.code, args.name, args.description, ep_name)
    if args.command == "create-token":
        return cmd_create_token(endpoints, args.library_id, args.label, args.role, ep_name)
    if args.command == "list-tokens":
        return cmd_list_tokens(endpoints, args.library_id, ep_name)
    if args.command == "revoke-token":
        return cmd_revoke_token(endpoints, args.library_id, args.token_id, ep_name)
    if args.command == "whoami":
        return cmd_whoami(endpoints, ep_name)
    if args.command == "promote":
        return cmd_promote(endpoints, args.record_id, args.note, ep_name)
    if args.command == "reject":
        return cmd_reject(endpoints, args.record_id, args.note, ep_name)
    if args.command == "delete-record":
        return cmd_delete_record(endpoints, args.record_id, ep_name)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
