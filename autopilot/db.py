import os
from pathlib import Path
from sqlmodel import SQLModel, create_engine, Session

# DB setup
# Use a hidden database file in the project root for simplicity and cleanliness.
BASE_DIR = Path(
    os.environ.get("AUTOPILOT_ROOT", Path(__file__).parent.parent.resolve())
)
DB_PATH = BASE_DIR / ".autopilot.db"
DB_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DB_URL, echo=False, connect_args={"check_same_thread": False})


def reset_engine():
    """Reset the engine, e.g. for testing with a different root."""
    global BASE_DIR, DB_PATH, DB_URL, engine
    BASE_DIR = Path(
        os.environ.get("AUTOPILOT_ROOT", Path(__file__).parent.parent.resolve())
    )
    DB_PATH = BASE_DIR / ".autopilot.db"
    DB_URL = f"sqlite:///{DB_PATH}"
    engine = create_engine(
        DB_URL, echo=False, connect_args={"check_same_thread": False}
    )


def init_db():
    from .models import Task  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
