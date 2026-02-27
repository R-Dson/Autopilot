import os
import pytest
from sqlmodel import Session

from autopilot.models import Task, TaskStatus
from autopilot import db as db_module


@pytest.fixture(autouse=True)
def reset_db():
    """Reset database engine before each test for isolation."""
    original_cwd = os.getcwd()
    db_module.reset_engine()
    yield
    db_module.reset_engine()
    os.chdir(original_cwd)


@pytest.fixture
def tmp_project(tmp_path):
    """Creates a temporary project directory with .autopilot/ initialized."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()

    autopilot_dir = project_dir / ".autopilot"
    autopilot_dir.mkdir()

    # Change to project directory so database is created there
    os.chdir(project_dir)

    # Reset engine to use new project directory
    db_module.reset_engine()

    # Initialize database
    db_module.init_db()

    yield project_dir


@pytest.fixture
def session(tmp_project):
    """Provides a database session for tests."""
    with Session(db_module.get_engine()) as ses:
        yield ses
        ses.rollback()


@pytest.fixture
def sample_task(session):
    """Creates a sample task for testing."""
    task = Task(
        jira_id="TEST-1",
        title="Test Task",
        prompt_payload="Implement feature X",
        status=TaskStatus.DRAFT,
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
