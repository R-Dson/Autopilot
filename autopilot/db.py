import os
from sqlmodel import SQLModel, Session, create_engine
from typing import Optional, Any

DB_PATH = ".autopilot/tasks.db"
_engine: Optional[Any] = None


def get_engine():
    """Get database engine with absolute path to current working directory."""
    global _engine
    if _engine is None:
        abs_db_path = os.path.abspath(DB_PATH)
        sqlite_url = f"sqlite:///{abs_db_path}"
        _engine = create_engine(sqlite_url)
    return _engine


def reset_engine():
    """Reset the cached engine. Useful for tests."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def init_db():
    os.makedirs(".autopilot", exist_ok=True)
    SQLModel.metadata.create_all(get_engine())


def get_session():
    return Session(get_engine())


# For backward compatibility
engine = get_engine()
