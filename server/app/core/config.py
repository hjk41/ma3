import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    service_name: str = "马妈妈 (ma3)"
    service_version: str = "0.4.0"
    min_client_version: str = "0.4.0"  # oldest client version still fully compatible
    recommended_client_version: str = "0.4.0"  # preferred bundled client/skill version
    feature_flags: tuple[str, ...] = (
        "immediate_visibility",
        "delete_record",
        "legacy_promote_supported",
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
    op_log_dir: Path = field(init=False)
    log_archive_dir: Path | None = field(init=False)
    log_local_retention_days: int = field(init=False)
    log_redact_raw: bool = field(init=False)

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
        op_log_dir = Path(os.environ.get("MA3_OP_LOG_DIR", "/var/log/ma3/ops"))
        log_archive = os.environ.get("MA3_LOG_ARCHIVE_DIR") or None
        log_local_retention_days = int(os.environ.get("MA3_LOG_LOCAL_RETENTION_DAYS", "2"))
        log_redact_raw = os.environ.get("MA3_LOG_REDACT_RAW", "1") != "0"
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
        object.__setattr__(self, "op_log_dir", op_log_dir)
        object.__setattr__(self, "log_archive_dir", Path(log_archive) if log_archive else None)
        object.__setattr__(self, "log_local_retention_days", log_local_retention_days)
        object.__setattr__(self, "log_redact_raw", log_redact_raw)


settings = Settings()
