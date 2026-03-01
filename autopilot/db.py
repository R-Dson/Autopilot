from pathlib import Path
from sqlmodel import SQLModel, create_engine, Session

# DB setup
# Use a hidden database file in the project root for simplicity and cleanliness.
BASE_DIR = Path(__file__).parent.parent.resolve()
DB_PATH = BASE_DIR / ".autopilot.db"
DB_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DB_URL, echo=False, connect_args={"check_same_thread": False})


def init_db():
    from .models import Task  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
