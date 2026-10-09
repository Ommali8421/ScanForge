"""
Database Session and Engine Management
"""

import os
from pathlib import Path
from sqlmodel import SQLModel, create_engine, Session
from app.config import settings

# Parse database URL
db_url = settings.SCANFORGE_DB_URL

# For SQLite, ensure parent directory exists
if db_url.startswith("sqlite"):
    # Strip sqlite:/// or sqlite:////
    clean_path = db_url.replace("sqlite:////", "/").replace("sqlite:///", "")
    db_file_path = Path(clean_path)
    
    # Check if directory can be written
    try:
        db_file_path.parent.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError):
        # Fallback to data_path inside workspace
        fallback_file = settings.data_path / "scanforge.db"
        fallback_file.parent.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite:///{fallback_file.as_posix()}"

# Create engine
connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
engine = create_engine(db_url, echo=settings.DEBUG, connect_args=connect_args)


def init_db():
    """Create all SQLModel database tables."""
    # Ensure models are imported
    from app.models.job import Job  # noqa: F401
    from app.models.artifact import Artifact  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session():
    """Dependency for obtaining a database session."""
    with Session(engine) as session:
        yield session
