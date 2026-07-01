from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    return default if raw is None or not raw.strip() else raw.strip()


@dataclass(slots=True)
class Settings:
    service_name: str = "ma3"
    service_version: str = field(default_factory=lambda: _env_str("MA3_SERVICE_VERSION", "1.0.0"))
    skill_version: str = field(default_factory=lambda: _env_str("MA3_SKILL_VERSION", "1.0.0"))
    api_version: str = "v1"
    min_client_version: str = field(default_factory=lambda: _env_str("MA3_MIN_CLIENT_VERSION", "1.0.0"))
    recommended_client_version: str = field(
        default_factory=lambda: _env_str("MA3_RECOMMENDED_CLIENT_VERSION", "1.0.0")
    )
    min_tool_schema_version: str = field(
        default_factory=lambda: _env_str("MA3_MIN_TOOL_SCHEMA_VERSION", "ma3.mcp.v1")
    )
    protocol_version: str = "2025-03-26"
    tool_schema_version: str = field(default_factory=lambda: _env_str("MA3_TOOL_SCHEMA_VERSION", "ma3.mcp.v1"))
    client_state_filename: str = ".ma3/ma3-client.json"
    client_sync_command: str = 'bash "${MA3_BIN_DIR:-$HOME/.ma3/bin}/sync_ma3_client.sh" sync'
    sync_tooling_version: str = field(default_factory=lambda: _env_str("MA3_SYNC_TOOLING_VERSION", "1.0.0"))

    instance_id: str | None = field(default_factory=lambda: os.environ.get("MA3_INSTANCE_ID"))
    git_commit: str | None = field(default_factory=lambda: os.environ.get("MA3_GIT_COMMIT"))
    job_name: str | None = field(default_factory=lambda: os.environ.get("MA3_JOB_NAME"))
    public_base_url: str | None = field(default_factory=lambda: os.environ.get("MA3_PUBLIC_BASE_URL"))

    database_url: str = field(
        default_factory=lambda: os.environ.get("MA3_DATABASE_URL", "sqlite:///./data/ma3.db")
    )
    dev_auth: bool = field(default_factory=lambda: _env_bool("MA3_DEV_AUTH", True))
    dev_api_key: str = field(default_factory=lambda: os.environ.get("MA3_DEV_API_KEY", "ma3dev"))
    disable_embeddings: bool = field(default_factory=lambda: _env_bool("MA3_DISABLE_EMBEDDINGS", False))

    default_org_id: str = "org_default"
    default_library_id: str = "lib_default"

    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )

    @property
    def database_backend(self) -> str:
        url = os.environ.get("MA3_DATABASE_URL", self.database_url)
        return "postgresql" if url.startswith("postgresql") else "sqlite"

    @property
    def feature_flags(self) -> tuple[str, ...]:
        flags = ["mcp", "observatory", self.database_backend]
        if not self.disable_embeddings:
            flags.append("vector")
        if self.dev_auth:
            flags.append("dev_auth")
        return tuple(flags)


settings = Settings()
