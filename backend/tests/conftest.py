"""
Pytest fixtures and environment configuration
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["SCANFORGE_ENGINE"] = "mock"

import pytest
from app.db.session import init_db


@pytest.fixture(autouse=True)
def setup_database():
    """Ensure database tables are initialized before tests run."""
    init_db()
