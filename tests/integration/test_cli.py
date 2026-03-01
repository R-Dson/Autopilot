"""Integration tests for CLI commands."""

import os
import pytest
from typer.testing import CliRunner
from autopilot.models import Task, TaskStatus
from autopilot import main as cli_module
from autopilot import db


# Get the typer app properly
app = cli_module.app


@pytest.fixture
def cli_runner():
    """Provides a Typer CLI test runner."""
    return CliRunner()


@pytest.fixture(autouse=True)
def setup_db():
    """Ensure DB is initialized before each test."""
    db.init_db()


class TestInitCommand:
    """Tests for 'autopilot init' command."""

    def test_init_succeeds(self, cli_runner, tmp_path):
        """init should succeed and initialize the database."""
        os.chdir(tmp_path)
        result = cli_runner.invoke(app, ["init"], catch_exceptions=False)

        assert result.exit_code == 0
        assert "initialized" in result.output.lower()


class TestListCommand:
    """Tests for 'autopilot list' command."""

    def test_list_empty(self, cli_runner, tmp_path):
        """list should show no tasks when empty."""
        os.chdir(tmp_path)
        result = cli_runner.invoke(app, ["list"], catch_exceptions=False)

        assert result.exit_code == 0
        assert "no tasks found" in result.output.lower()

    def test_list_shows_tasks(self, cli_runner, tmp_path, session):
        """list should show tasks."""
        os.chdir(tmp_path)

        # Create a task directly
        task = Task(
            jira_id="TEST-1",
            title="Test Task",
            prompt_payload="Do something",
            status=TaskStatus.DRAFT,
            sort_order=1,
        )
        session.add(task)
        session.commit()

        result = cli_runner.invoke(app, ["list"], catch_exceptions=False)

        assert result.exit_code == 0
        assert "TEST-1" in result.output


class TestUpdateCommand:
    """Tests for 'autopilot update' command."""

    def test_update_changes_status(self, cli_runner, tmp_path, session):
        """update should change task status."""
        os.chdir(tmp_path)

        # Create a task directly
        task = Task(
            jira_id="TEST-1",
            title="Task",
            prompt_payload="x",
            status=TaskStatus.DRAFT,
            sort_order=1,
        )
        session.add(task)
        session.commit()
        session.refresh(task)
        task_id = task.id

        result = cli_runner.invoke(
            app, ["update", str(task_id), "--status", "ready"], catch_exceptions=False
        )

        assert result.exit_code == 0
        assert "updated" in result.output.lower()

        # Verify the task was updated
        session.expire_all()
        updated_task = session.get(Task, task_id)
        assert updated_task is not None
        assert updated_task.status == TaskStatus.READY
