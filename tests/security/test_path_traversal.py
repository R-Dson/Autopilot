import pytest
from sqlmodel import Session, select
from autopilot.models import Task
from autopilot import db
from autopilot.server import tasks_create
from autopilot.security import validate_jira_id


@pytest.fixture(autouse=True)
def setup_db():
    """Ensure DB is initialized before each test."""
    db.init_db()


def test_validate_jira_id_valid():
    """Valid JIRA IDs should not raise ValueError."""
    validate_jira_id("STABLE-101")
    validate_jira_id("WEB_DASH_001")
    validate_jira_id("12345")
    validate_jira_id("PROJ-99-new")


def test_validate_jira_id_invalid_traversal():
    """JIRA IDs with path traversal attempts should raise ValueError."""
    with pytest.raises(
        ValueError,
        match="Special characters like '/', '\\\\', or '\\.\\.' are strictly prohibited",
    ):
        validate_jira_id("../etc/passwd")


def test_validate_jira_id_invalid_slash():
    """JIRA IDs with slashes should raise ValueError."""
    with pytest.raises(
        ValueError,
        match="Special characters like '/', '\\\\', or '\\.\\.' are strictly prohibited",
    ):
        validate_jira_id("feat/STABLE-101")


def test_validate_jira_id_invalid_backslash():
    """JIRA IDs with backslashes should raise ValueError."""
    with pytest.raises(
        ValueError,
        match="Special characters like '/', '\\\\', or '\\.\\.' are strictly prohibited",
    ):
        validate_jira_id("C:\\Windows")


def test_validate_jira_id_invalid_dotdot():
    """JIRA IDs with double dots should raise ValueError (even if no slash)."""
    with pytest.raises(
        ValueError,
        match="Special characters like '/', '\\\\', or '\\.\\.' are strictly prohibited",
    ):
        validate_jira_id("STABLE..101")


def test_tasks_create_validation():
    """tasks_create tool should validate jira_id and return error message."""
    result = tasks_create(
        jira_id="../malicious", tasks=[{"title": "test", "prompt_payload": "test"}]
    )
    assert "Invalid JIRA ID" in result

    # Verify no task was created with that JIRA ID

    with Session(db.engine) as session:
        statement = select(Task).where(Task.jira_id == "../malicious")
        tasks = session.exec(statement).all()
        assert len(tasks) == 0


def test_workspace_acquire_naming_collision_prevention():
    """
    Test that workspace_acquire uses the new naming convention (dash instead of slash)
    to avoid ref name collisions.
    """
    from unittest.mock import MagicMock, patch
    from autopilot.server import workspace_acquire
    from autopilot.models import TaskStatus

    # Mock GitManager to avoid actual git operations
    mock_gm = MagicMock()
    mock_gm.create_worktree.return_value = "/tmp/worktree-STABLE-102-3"

    with patch("autopilot.server._get_git_manager", return_value=mock_gm):
        with Session(db.engine) as session:
            # Create a task
            task = Task(
                jira_id="STABLE-102",
                title="Collision Test",
                prompt_payload="test",
                status=TaskStatus.READY,
                sort_order=1,
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            task_id = task.id

        # Acquire workspace
        result_json = workspace_acquire(task_id=task_id)
        import json

        result = json.loads(result_json)

        # In new workflow, branch_name is None, feature_branch is set
        # Note: result structure is now {task: {...}, feature_tasks: [...]}
        assert result["task"]["branch_name"] is None
        assert result["task"]["feature_branch"] == "feat/STABLE-102"
        assert "STABLE-102" in result["task"]["worktree_path"]

        # Also verify feature_tasks is present
        assert "feature_tasks" in result
        assert len(result["feature_tasks"]) == 1
