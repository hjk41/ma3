import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.storage.db import initialize_database


@pytest.fixture(scope="session", autouse=True)
def _db() -> None:
    initialize_database()
