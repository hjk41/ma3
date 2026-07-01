"""Server adapter around standalone client/lib/ma3_sync_core.py."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_CORE_PATH = Path(__file__).resolve().parents[3] / "client" / "lib" / "ma3_sync_core.py"
_spec = importlib.util.spec_from_file_location("ma3_sync_core", _CORE_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"cannot load ma3_sync_core from {_CORE_PATH}")
_mod = importlib.util.module_from_spec(_spec)
sys.modules["ma3_sync_core"] = _mod
_spec.loader.exec_module(_mod)

ClientState = _mod.ClientState
DEFAULT_INSTALL_PATHS = _mod.DEFAULT_INSTALL_PATHS
HttpFetch = _mod.HttpFetch
SyncPlan = _mod.SyncPlan
fetch_manifest = _mod.fetch_manifest
load_client_state = _mod.load_client_state
plan_sync = _mod.plan_sync
sync_client = _mod.sync_client
sync_tooling = _mod.sync_tooling
write_client_state = _mod.write_client_state


class HttpFetchAdapter:
    """Adapter for FastAPI TestClient in integration tests."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def get_bytes(self, path: str) -> bytes:
        response = self._client.get(path)
        if response.status_code != 200:
            raise RuntimeError(f"GET {path} failed: {response.status_code}")
        return response.content
