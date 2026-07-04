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


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw.strip())
    except ValueError:
        return default


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

    # Search ranking (design/12 — Scheme B Gate-Then-Nudge). See validate_ranking_config().
    search_wilson_z: float = field(default_factory=lambda: _env_float("MA3_SEARCH_WILSON_Z", 1.96))
    search_t_high: float = field(default_factory=lambda: _env_float("MA3_SEARCH_T_HIGH", 0.65))
    search_t_mid: float = field(default_factory=lambda: _env_float("MA3_SEARCH_T_MID", 0.5))
    search_t_floor: float = field(default_factory=lambda: _env_float("MA3_SEARCH_T_FLOOR", 0.25))
    search_rel_min: float = field(default_factory=lambda: _env_float("MA3_SEARCH_REL_MIN", 0.35))
    search_epsilon: float = field(default_factory=lambda: _env_float("MA3_SEARCH_EPSILON", 0.05))
    search_delta: float = field(default_factory=lambda: _env_float("MA3_SEARCH_DELTA", 0.10))
    search_q_verified: float = field(default_factory=lambda: _env_float("MA3_SEARCH_Q_VERIFIED", 0.02))
    search_q_lean: float = field(default_factory=lambda: _env_float("MA3_SEARCH_Q_LEAN", 0.02))
    search_recency_tau_days: float = field(
        default_factory=lambda: _env_float("MA3_SEARCH_RECENCY_TAU_DAYS", 180.0)
    )
    search_hide_clearly_wrong: bool = field(
        default_factory=lambda: _env_bool("MA3_SEARCH_HIDE_CLEARLY_WRONG", True)
    )

    @property
    def search_cap(self) -> float:
        """clearly-wrong relevance ceiling = rel_min - delta."""
        return self.search_rel_min - self.search_delta
    embedding_model: str = field(
        default_factory=lambda: _env_str("MA3_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    )
    embedding_dim: int = field(default_factory=lambda: int(os.environ.get("MA3_EMBEDDING_DIM", "384")))

    authing_enabled: bool = field(default_factory=lambda: _env_bool("MA3_AUTHING_ENABLED", False))
    authing_issuer: str = field(default_factory=lambda: _env_str("MA3_AUTHING_ISSUER", ""))
    authing_app_id: str = field(default_factory=lambda: _env_str("MA3_AUTHING_APP_ID", ""))
    authing_app_secret: str = field(default_factory=lambda: _env_str("MA3_AUTHING_APP_SECRET", ""))
    authing_redirect_uri: str = field(default_factory=lambda: _env_str("MA3_AUTHING_REDIRECT_URI", ""))
    authing_post_logout_redirect_uri: str = field(
        default_factory=lambda: _env_str("MA3_AUTHING_POST_LOGOUT_REDIRECT_URI", "")
    )
    authing_account_url: str = field(default_factory=lambda: _env_str("MA3_AUTHING_ACCOUNT_URL", ""))
    auth_session_cookie: str = field(default_factory=lambda: _env_str("MA3_AUTH_SESSION_COOKIE", "ma3_session"))
    auth_oauth_state_cookie: str = field(default_factory=lambda: _env_str("MA3_AUTH_OAUTH_STATE_COOKIE", "ma3_oauth_state"))
    auth_admin_users: tuple[str, ...] = field(default_factory=lambda: tuple())
    auth_userinfo_cache_ttl_seconds: int = field(
        default_factory=lambda: int(os.environ.get("MA3_AUTH_USERINFO_CACHE_TTL_SECONDS", "60"))
    )

    default_org_id: str = "org_default"
    default_library_id: str = "lib_default"
    max_keys_per_principal: int = field(
        default_factory=lambda: int(os.environ.get("MA3_MAX_KEYS_PER_PRINCIPAL", "10"))
    )
    paid_principal_ids: tuple[str, ...] = field(default_factory=lambda: tuple())
    api_key_encryption_secret: str = field(
        default_factory=lambda: _env_str("MA3_API_KEY_ENCRYPTION_SECRET", "")
    )

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
        raw_paid = os.environ.get("MA3_PAID_PRINCIPAL_IDS", "")
        if raw_paid.strip():
            object.__setattr__(
                self,
                "paid_principal_ids",
                tuple(item.strip() for item in raw_paid.split(",") if item.strip()),
            )
        ma3_hf_home = os.environ.get("MA3_HF_HOME", "").strip()
        if ma3_hf_home and not os.environ.get("HF_HOME", "").strip():
            os.environ["HF_HOME"] = ma3_hf_home
        validate_ranking_config(self)

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

    def resolve_authing_post_logout_redirect_uri(self) -> str:
        if self.authing_post_logout_redirect_uri:
            return self.authing_post_logout_redirect_uri
        base = (self.public_base_url or "http://127.0.0.1:8000").rstrip("/")
        return f"{base}/ui/observatory/"

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


class RankingConfigError(ValueError):
    """Raised when search-ranking hyperparameters violate the GTN invariants."""


def validate_ranking_config(s: "Settings") -> None:
    """Fail fast if MA3_SEARCH_* config breaks the Scheme B invariants (design/12 §4).

    Runs at startup (via ``__post_init__``) so a bad env/deploy config crashes
    immediately instead of silently mis-ranking. Also reused by tests as the guard.
    """
    q = max(s.search_q_verified, s.search_q_lean)
    # Core invariant: 2·max(|q|) < epsilon < delta (trust nudge can never flip a
    # relevance gap of epsilon, and clearly-wrong cap sits a full delta below rel_min).
    if not (2 * q < s.search_epsilon < s.search_delta):
        raise RankingConfigError(
            f"ranking invariant violated: 2*max(q)={2 * q} must be < epsilon={s.search_epsilon} "
            f"< delta={s.search_delta}"
        )
    if abs(s.search_cap - (s.search_rel_min - s.search_delta)) > 1e-9:
        raise RankingConfigError(
            f"cap={s.search_cap} must equal rel_min-delta={s.search_rel_min - s.search_delta}"
        )
    if not (0.0 <= s.search_t_floor < s.search_t_mid < s.search_t_high <= 1.0):
        raise RankingConfigError(
            f"thresholds must satisfy 0<=t_floor<t_mid<t_high<=1; got "
            f"floor={s.search_t_floor}, mid={s.search_t_mid}, high={s.search_t_high}"
        )
    if s.search_q_verified < 0 or s.search_q_lean < 0:
        raise RankingConfigError("q_verified and q_lean are magnitudes and must be >= 0")
    if not (0.0 < s.search_rel_min <= 1.0):
        raise RankingConfigError(f"rel_min must be in (0,1]; got {s.search_rel_min}")


settings = Settings()
