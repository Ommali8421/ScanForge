"""
Pytest fixtures and environment configuration
Enforces strict test isolation: all tests run against a dedicated temporary SQLite
database and isolated data directory, preventing test jobs from polluting the
production/live database (/data/scanforge.db).
"""

import os
import shutil
import tempfile
from pathlib import Path

# 1. Initialize isolated temporary directory for tests
_test_tmp_dir = tempfile.mkdtemp(prefix="scanforge_test_")
_test_db_path = Path(_test_tmp_dir) / "test_scanforge.db"

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["SCANFORGE_ENGINE"] = "mock"
os.environ["SCANFORGE_DB_URL"] = f"sqlite:///{_test_db_path.as_posix()}"
os.environ["SCANFORGE_DATA_DIR"] = _test_tmp_dir

import pytest
from sqlmodel import create_engine
import app.db.session as db_session
from app.db.session import init_db

# 2. Redirect session engine to the isolated test database
db_session.db_url = os.environ["SCANFORGE_DB_URL"]
db_session.engine = create_engine(
    db_session.db_url,
    connect_args={"check_same_thread": False}
)


@pytest.fixture(autouse=True)
def setup_database():
    """Ensure database tables are initialized before tests run."""
    init_db()


def pytest_sessionfinish(session, exitstatus):
    """Clean up temporary test directory after test run."""
    shutil.rmtree(_test_tmp_dir, ignore_errors=True)
