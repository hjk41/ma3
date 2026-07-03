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
    dev_auth: bool = field(default_factory=lambda: _env_bool("MA3_DEV_AUTH", False))
    dev_api_key: str = field(default_factory=lambda: os.environ.get("MA3_DEV_API_KEY", "ma3dev"))
    writer_api_keys: tuple[str, ...] = field(default_factory=lambda: tuple())
    maintainer_api_keys: tuple[str, ...] = field(default_factory=lambda: tuple())
    vector_scan_limit: int = field(default_factory=lambda: int(os.environ.get("MA3_VECTOR_SCAN_LIMIT", "500")))
    disable_embeddings: bool = field(default_factory=lambda: _env_bool("MA3_DISABLE_EMBEDDINGS", False))
    embedding_model: str = field(
        default_factory=lambda: _env_str("MA3_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    )
    embedding_dim: int = field(default_factory=lambda: int(os.environ.get("MA3_EMBEDDING_DIM", "384")))

    authing_enabled: bool = field(default_factory=lambda: _env_bool("MA3_AUTHING_ENABLED", False))
    authing_issuer: str = field(default_factory=lambda: _env_str("MA3_AUTHING_ISSUER", ""))
    authing_app_id: str = field(default_factory=lambda: _env_str("MA3_AUTHING_APP_ID", ""))
    authing_app_secret: str = field(default_factory=lambda: _env_str("MA3_AUTHING_APP_SECRET", ""))
    authing_redirect_uri: str = field(default_factory=lambda: _env_str("MA3_AUTHING_REDIRECT_URI", ""))
    authing_account_url: str = field(default_factory=lambda: _env_str("MA3_AUTHING_ACCOUNT_URL", ""))
    auth_session_cookie: str = field(default_factory=lambda: _env_str("MA3_AUTH_SESSION_COOKIE", "ma3_session"))
    auth_oauth_state_cookie: str = field(default_factory=lambda: _env_str("MA3_AUTH_OAUTH_STATE_COOKIE", "ma3_oauth_state"))
    auth_admin_users: tuple[str, ...] = field(default_factory=lambda: tuple())
    auth_userinfo_cache_ttl_seconds: int = field(
        default_factory=lambda: int(os.environ.get("MA3_AUTH_USERINFO_CACHE_TTL_SECONDS", "60"))
    )

    default_org_id: str = "org_default"
    default_library_id: str = "lib_default"

    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )

    def __post_init__(self) -> None:
        raw_admins = os.environ.get("MA3_AUTH_ADMIN_USERS", "")
        if raw_admins.strip():
            object.__setattr__(
                self,
                "auth_admin_users",
                tuple(item.strip() for item in raw_admins.split(",") if item.strip()),
            )
        raw_writers = os.environ.get("MA3_WRITER_API_KEYS", "")
        if raw_writers.strip():
            object.__setattr__(
                self,
                "writer_api_keys",
                tuple(item.strip() for item in raw_writers.split(",") if item.strip()),
            )
        raw_maintainers = os.environ.get("MA3_MAINTAINER_API_KEYS", "")
        if raw_maintainers.strip():
            object.__setattr__(
                self,
                "maintainer_api_keys",
                tuple(item.strip() for item in raw_maintainers.split(",") if item.strip()),
            )

    @property
    def authing_configured(self) -> bool:
        return bool(self.authing_enabled and self.authing_issuer and self.authing_app_id and self.authing_app_secret)

    def authing_issuer_base(self) -> str:
        issuer = self.authing_issuer.rstrip("/")
        if issuer.endswith("/oidc"):
            return issuer
        return f"{issuer}/oidc"

    def resolve_authing_redirect_uri(self) -> str:
        if self.authing_redirect_uri:
            return self.authing_redirect_uri
        base = (self.public_base_url or "http://127.0.0.1:8000").rstrip("/")
        return f"{base}/auth/callback"

    def resolve_authing_account_url(self) -> str:
        if self.authing_account_url:
            return self.authing_account_url
        return f"{self.authing_issuer_base().removesuffix('/oidc')}/u"

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
        if self.authing_configured:
            flags.append("authing")
        return tuple(flags)


settings = Settings()
