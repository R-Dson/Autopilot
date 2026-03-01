import pytest
from sqlmodel import SQLModel, create_engine, Session
from autopilot.models import Task, TaskStatus
import autopilot.db


@pytest.fixture(autouse=True)
def mock_db(tmp_path, monkeypatch):
    """Use a temporary SQLite database for tests."""
    from autopilot.models import Task as _Task  # noqa: F401

    db_path = tmp_path / "test_autopilot.db"

    test_engine = create_engine(f"sqlite:///{db_path}")

    # Patch the engine in the db module so all other modules use it
    monkeypatch.setattr(autopilot.db, "engine", test_engine)

    # Initialize the test database
    SQLModel.metadata.create_all(test_engine)

    yield test_engine


@pytest.fixture
def session(mock_db):
    """Provides a SQLModel session for testing."""
    with Session(mock_db) as session:
        yield session


@pytest.fixture
def tmp_project(tmp_path, monkeypatch):
    """Creates a temporary project directory."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    return project_dir


@pytest.fixture
def sample_task(session):
    """Creates a sample task for testing."""
    task = Task(
        jira_id="TEST-1",
        title="Test Task",
        prompt_payload="Implement feature X",
        status=TaskStatus.READY,
        sort_order=1,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@pytest.fixture
def git_manager(tmp_path):
    """Provides a GitManager instance with a temp directory."""
    from autopilot.git_manager import GitManager

    return GitManager(repo_path=str(tmp_path))


@pytest.fixture
def mock_git_env(monkeypatch):
    """Mocks git commands for testing without actual git."""

    def mock_run(*args, **kwargs):
        return ""

    monkeypatch.setattr("autopilot.git_manager.GitManager._run_git", mock_run)
