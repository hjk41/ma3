import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    service_name: str = "马妈妈 (ma3)"
    service_version: str = "0.3.0"
    min_client_version: str = "0.3.0"  # oldest client version still fully compatible
    app_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parents[1])
    project_dir: Path = field(init=False)
    data_dir: Path = field(init=False)
    db_path: Path = field(init=False)
    database_url: str | None = field(init=False)
    db_backend: str = field(init=False)
    seed_path: Path = field(init=False)
    api_key: str | None = field(init=False)

    def __post_init__(self) -> None:
        project_dir = self.app_dir.parent
        data_dir = Path(os.environ.get("MA3_DATA_DIR", project_dir / "data"))
        db_path = Path(os.environ.get("MA3_DB_PATH", data_dir / "ma3.db"))
        database_url = os.environ.get("MA3_DATABASE_URL") or None
        seed_path = Path(
            os.environ.get("MA3_SEED_PATH", project_dir / "data" / "seed_records.json")
        )
        api_key = os.environ.get("MA3_API_KEY") or None
        db_backend = "postgresql" if database_url else "sqlite"
        object.__setattr__(self, "project_dir", project_dir)
        object.__setattr__(self, "data_dir", data_dir)
        object.__setattr__(self, "db_path", db_path)
        object.__setattr__(self, "database_url", database_url)
        object.__setattr__(self, "db_backend", db_backend)
        object.__setattr__(self, "seed_path", seed_path)
        object.__setattr__(self, "api_key", api_key)


settings = Settings()
