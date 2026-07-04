import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.core.config import settings
from app.storage import db
from app.storage.db import initialize_database


@pytest.fixture(scope="session", autouse=True)
def _db() -> None:
    initialize_database()
    db.set_library_write_buffer_hours(settings.default_library_id, 0)


@pytest.fixture(autouse=True)
def _dev_auth_for_unit_tests(monkeypatch):
    monkeypatch.setenv("MA3_DEV_AUTH", "1")
    monkeypatch.setenv("MA3_DEV_API_KEY", "ma3dev")
    monkeypatch.setattr(settings, "dev_auth", True)
    monkeypatch.setattr(settings, "dev_api_key", "ma3dev")
