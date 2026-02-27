"""Integration tests for CLI commands."""

import os
import pytest
from typer.testing import CliRunner

from autopilot.models import Task, TaskStatus
from autopilot import main as cli_module


# Get the typer app properly
app = cli_module.app


@pytest.fixture
def cli_runner():
    """Provides a Typer CLI test runner."""
    return CliRunner()


class TestInitCommand:
    """Tests for 'autopilot init' command."""

    def test_init_creates_autopilot_directory(self, cli_runner, tmp_path):
        """init should create .autopilot directory."""
        from autopilot import db as db_module

        db_module.reset_engine()
        db_module.engine.dispose()

        result = cli_runner.invoke(app, ["init"], catch_exceptions=False)

        assert result.exit_code == 0
        assert os.path.exists(".autopilot")

    def test_init_creates_database(self, cli_runner, tmp_path):
        """init should create tasks.db."""
        from autopilot import db as db_module

        db_module.reset_engine()
        db_module.engine.dispose()

        result = cli_runner.invoke(app, ["init"], catch_exceptions=False)

        assert result.exit_code == 0
        assert os.path.exists(".autopilot/tasks.db")


class TestListCommand:
    """Tests for .autopilot list' command."""

    def test_list_empty(self, cli_runner, tmp_path):
        """list should show no tasks when empty."""
        from autopilot import db as db_module

        db_module.reset_engine()
        db_module.engine.dispose()

        # Init database first
        cli_runner.invoke(app, ["init"], catch_exceptions=False)

        result = cli_runner.invoke(app, ["list"], catch_exceptions=False)

        assert result.exit_code == 0

    def test_list_shows_tasks(self, cli_runner, tmp_path):
        """list should show tasks."""
        from autopilot import db as db_module

        db_module.reset_engine()
        db_module.engine.dispose()

        # Init database first
        cli_runner.invoke(app, ["init"], catch_exceptions=False)

        # Create a task directly
        task = Task(
            jira_id="TEST-1",
            title="Test Task",
            prompt_payload="Do something",
            status=TaskStatus.DRAFT,
            sort_order=1,
        )
        with db_module.get_session() as session:
            session.add(task)
            session.commit()

        result = cli_runner.invoke(app, ["list"], catch_exceptions=False)

        assert result.exit_code == 0
        assert "TEST-1" in result.output


class TestUpdateCommand:
    """Tests for .autopilot update' command."""

    def test_update_changes_status(self, cli_runner, tmp_path):
        """update should change task status."""
        from autopilot import db as db_module

        db_module.reset_engine()
        db_module.engine.dispose()

        # Init database first
        cli_runner.invoke(app, ["init"], catch_exceptions=False)

        # Create a task directly
        task = Task(
            jira_id="TEST-1",
            title="Task",
            prompt_payload="x",
            status=TaskStatus.DRAFT,
            sort_order=1,
        )
        with db_module.get_session() as session:
            session.add(task)
            session.commit()
            task_id = task.id

        result = cli_runner.invoke(
            app, ["update", str(task_id), "--status", "ready"], catch_exceptions=False
        )

        assert result.exit_code == 0

        # Verify the change
        with db_module.get_session() as session:
            updated_task = session.get(Task, task_id)
            assert updated_task.status == TaskStatus.READY
