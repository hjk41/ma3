import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class Settings:
    service_name: str = "马妈妈 (ma3)"
    service_version: str = "4.0.0"
    skill_version: str = "4.0.0"
    min_client_version: str = "4.0.0"
    recommended_client_version: str = "4.0.0"
    feature_flags: tuple[str, ...] = (
        "immediate_visibility",
        "delete_record",
        "org_libraries",
        "api_key_grants",
    )
    app_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parents[1])
    project_dir: Path = field(init=False)
    data_dir: Path = field(init=False)
    db_path: Path = field(init=False)
    database_url: str | None = field(init=False)
    db_backend: str = field(init=False)
    seed_path: Path = field(init=False)
    api_key: str | None = field(init=False)
    public_base_url: str | None = field(init=False)
    instance_id: str | None = field(init=False)
    git_commit: str | None = field(init=False)
    job_name: str | None = field(init=False)
    started_at: str = field(init=False)
    started_at_epoch: int = field(init=False)
    op_log_dir: Path = field(init=False)
    log_archive_dir: Path | None = field(init=False)
    log_local_retention_days: int = field(init=False)
    log_redact_raw: bool = field(init=False)
    db_pool_min_size: int = field(init=False)
    db_pool_max_size: int = field(init=False)
    db_pool_timeout_seconds: float = field(init=False)
    db_pool_enabled: bool = field(init=False)
    search_batch_graph_enabled: bool = field(init=False)
    search_index_mode: str = field(init=False)
    auth_verify_url: str | None = field(init=False)
    auth_login_url: str = field(init=False)
    auth_verify_timeout_seconds: float = field(init=False)
    auth_verify_cache_ttl_seconds: int = field(init=False)
    auth_verify_cache_max_entries: int = field(init=False)
    auth_jwt_cookie: str = field(init=False)
    auth_admin_users: tuple[str, ...] = field(init=False)
    xyz_library_id: str | None = field(init=False)
    api_version: str = field(init=False)
    dev_auth_enabled: bool = field(init=False)
    free_member_seat_limit: int = field(init=False)
    session_cookie: str = field(init=False)
    hf_home: Path = field(init=False)

    def __post_init__(self) -> None:
        project_dir = self.app_dir.parent
        data_dir = Path(os.environ.get("MA3_DATA_DIR", project_dir / "data"))
        db_path = Path(os.environ.get("MA3_DB_PATH", data_dir / "ma3.db"))
        database_url = os.environ.get("MA3_DATABASE_URL") or None
        seed_path = Path(
            os.environ.get("MA3_SEED_PATH", project_dir / "data" / "seed_records.json")
        )
        api_key = os.environ.get("MA3_API_KEY") or None
        public_base_url = os.environ.get("MA3_PUBLIC_BASE_URL") or None
        instance_id = os.environ.get("MA3_INSTANCE_ID") or None
        git_commit = os.environ.get("MA3_GIT_COMMIT") or None
        job_name = (
            os.environ.get("MA3_JOB_NAME")
            or os.environ.get("PAI_JOB_NAME")
            or os.environ.get("MA3_INSTANCE_NAME")
            or None
        )
        started_at_epoch = int(time.time())
        started_at = datetime.fromtimestamp(started_at_epoch, tz=timezone.utc).isoformat()
        op_log_dir = Path(os.environ.get("MA3_OP_LOG_DIR", "/var/log/ma3/ops"))
        log_archive = os.environ.get("MA3_LOG_ARCHIVE_DIR") or None
        log_local_retention_days = int(os.environ.get("MA3_LOG_LOCAL_RETENTION_DAYS", "2"))
        log_redact_raw = os.environ.get("MA3_LOG_REDACT_RAW", "1") != "0"
        db_pool_min_size = int(os.environ.get("MA3_DB_POOL_MIN_SIZE", "1"))
        db_pool_max_size = int(os.environ.get("MA3_DB_POOL_MAX_SIZE", "8"))
        db_pool_timeout_seconds = float(os.environ.get("MA3_DB_POOL_TIMEOUT_SECONDS", "5"))
        db_pool_enabled = os.environ.get("MA3_DB_POOL_ENABLED", "1") != "0"
        search_batch_graph_enabled = os.environ.get("MA3_SEARCH_BATCH_GRAPH_ENABLED", "1") != "0"
        search_index_mode = os.environ.get("MA3_SEARCH_INDEX_MODE", "jsonb_runtime").strip() or "jsonb_runtime"
        api_version = os.environ.get("MA3_API_VERSION", "v4").strip().lower() or "v4"
        dev_auth_enabled = os.environ.get("MA3_DEV_AUTH", "0") == "1"
        free_member_seat_limit = int(os.environ.get("MA3_FREE_MEMBER_SEAT_LIMIT", "1"))
        session_cookie = os.environ.get("MA3_SESSION_COOKIE", "ma3_session").strip() or "ma3_session"
        auth_verify_url_raw = os.environ.get("MA3_AUTH_VERIFY_URL", "").strip()
        auth_verify_url = auth_verify_url_raw or None
        if auth_verify_url:
            parsed = urlparse(auth_verify_url)
            is_loopback_http = (
                parsed.scheme == "http"
                and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
            )
            if parsed.scheme != "https" and not is_loopback_http:
                raise ValueError(
                    "MA3_AUTH_VERIFY_URL must be https://, except http:// loopback URLs in tests"
                )
        auth_login_url = os.environ.get("MA3_AUTH_LOGIN_URL", "").strip()
        auth_verify_timeout_seconds = float(os.environ.get("MA3_AUTH_VERIFY_TIMEOUT_SECONDS", "2.0"))
        auth_verify_cache_ttl_seconds = int(os.environ.get("MA3_AUTH_VERIFY_CACHE_TTL_SECONDS", "60"))
        auth_verify_cache_max_entries = int(os.environ.get("MA3_AUTH_VERIFY_CACHE_MAX_ENTRIES", "2048"))
        auth_jwt_cookie = os.environ.get("MA3_AUTH_JWT_COOKIE", "gateway_token").strip() or "gateway_token"
        auth_admin_users = tuple(
            item.strip()
            for item in os.environ.get("MA3_AUTH_ADMIN_USERS", "").split(",")
            if item.strip()
        )
        xyz_library_id = os.environ.get("MA3_XYZ_LIBRARY_ID") or None
        db_backend = "postgresql" if database_url else "sqlite"
        object.__setattr__(self, "project_dir", project_dir)
        object.__setattr__(self, "data_dir", data_dir)
        object.__setattr__(self, "db_path", db_path)
        object.__setattr__(self, "database_url", database_url)
        object.__setattr__(self, "db_backend", db_backend)
        object.__setattr__(self, "seed_path", seed_path)
        object.__setattr__(self, "api_key", api_key)
        object.__setattr__(self, "public_base_url", public_base_url)
        object.__setattr__(self, "instance_id", instance_id)
        object.__setattr__(self, "git_commit", git_commit)
        object.__setattr__(self, "job_name", job_name)
        object.__setattr__(self, "started_at", started_at)
        object.__setattr__(self, "started_at_epoch", started_at_epoch)
        object.__setattr__(self, "op_log_dir", op_log_dir)
        object.__setattr__(self, "log_archive_dir", Path(log_archive) if log_archive else None)
        object.__setattr__(self, "log_local_retention_days", log_local_retention_days)
        object.__setattr__(self, "log_redact_raw", log_redact_raw)
        object.__setattr__(self, "db_pool_min_size", db_pool_min_size)
        object.__setattr__(self, "db_pool_max_size", db_pool_max_size)
        object.__setattr__(self, "db_pool_timeout_seconds", db_pool_timeout_seconds)
        object.__setattr__(self, "db_pool_enabled", db_pool_enabled)
        object.__setattr__(self, "search_batch_graph_enabled", search_batch_graph_enabled)
        object.__setattr__(self, "search_index_mode", search_index_mode)
        object.__setattr__(self, "auth_verify_url", auth_verify_url)
        object.__setattr__(self, "auth_login_url", auth_login_url)
        object.__setattr__(self, "auth_verify_timeout_seconds", auth_verify_timeout_seconds)
        object.__setattr__(self, "auth_verify_cache_ttl_seconds", auth_verify_cache_ttl_seconds)
        object.__setattr__(self, "auth_verify_cache_max_entries", auth_verify_cache_max_entries)
        object.__setattr__(self, "auth_jwt_cookie", auth_jwt_cookie)
        object.__setattr__(self, "auth_admin_users", auth_admin_users)
        object.__setattr__(self, "xyz_library_id", xyz_library_id)
        object.__setattr__(self, "api_version", api_version)
        object.__setattr__(self, "dev_auth_enabled", dev_auth_enabled)
        object.__setattr__(self, "free_member_seat_limit", free_member_seat_limit)
        object.__setattr__(self, "session_cookie", session_cookie)
        hf_home = Path(os.environ.get("MA3_HF_HOME", data_dir / "hf-cache"))
        hf_home.mkdir(parents=True, exist_ok=True)
        hub_cache = hf_home / "hub"
        hub_cache.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HF_HOME", str(hf_home))
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(hub_cache))
        os.environ.setdefault("TRANSFORMERS_CACHE", str(hf_home / "transformers"))
        object.__setattr__(self, "hf_home", hf_home)


settings = Settings()
