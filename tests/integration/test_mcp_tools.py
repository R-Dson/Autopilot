"""Integration tests for MCP tools (server functions)."""

import os
import pytest
from unittest.mock import MagicMock
from sqlmodel import select

from autopilot.models import Task, TaskStatus
from autopilot import db as db_module
from autopilot.server import (
    tasks_create,
    tasks_list,
    tasks_update,
    workspace_acquire,
    workspace_submit,
    review_approve,
    review_reject,
)


@pytest.fixture
def server_db_setup(tmp_path, monkeypatch):
    """Sets up database for MCP tool tests."""
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    db_module.reset_engine()
    db_module.init_db()
    yield
    os.chdir(original_cwd)
    db_module.reset_engine()


class TestTasksCreate:
    """Tests for tasks_create MCP tool."""

    def test_tasks_create_single_task(self, server_db_setup):
        """tasks_create should add a single task."""
        result = tasks_create(
            jira_id="PROJ-1",
            tasks=[
                {
                    "title": "Implement feature X",
                    "prompt_payload": "Add feature X to the codebase",
                    "sort_order": 1,
                }
            ],
        )

        assert "created" in result.lower()

        # Verify task was created
        with db_module.get_session() as session:
            tasks = session.exec(select(Task)).all()
            assert len(tasks) == 1
        assert tasks[0].title == "Implement feature X"
        assert tasks[0].status == TaskStatus.READY  # tasks_create creates READY tasks


class TestTasksList:
    """Tests for tasks_list MCP tool."""

    def test_tasks_list_returns_all(self, server_db_setup):
        """tasks_list should return all tasks."""
        # Create tasks
        tasks_create(
            jira_id="PROJ-1",
            tasks=[{"title": "Task 1", "prompt_payload": "x", "sort_order": 1}],
        )

        result = tasks_list()

        assert "Task 1" in str(result)

    def test_tasks_list_filters_by_status(self, server_db_setup):
        """tasks_list should filter by status."""
        # Create task in READY status
        with db_module.get_session() as session:
            task = Task(
                jira_id="PROJ-1",
                title="Ready Task",
                prompt_payload="x",
                status=TaskStatus.READY,
                sort_order=1,
            )
            session.add(task)
            session.commit()

        result = tasks_list(status="ready")

        assert "Ready Task" in str(result)


class TestTasksUpdate:
    """Tests for tasks_update MCP tool."""

    def test_tasks_update_changes_status(self, server_db_setup):
        """tasks_update should change task status."""
        # Create task
        tasks_create(
            jira_id="PROJ-1",
            tasks=[{"title": "Task", "prompt_payload": "x", "sort_order": 1}],
        )

        # Get task ID
        with db_module.get_session() as session:
            task = session.exec(select(Task)).one()
            task_id = task.id

        # Update status
        result = tasks_update(task_id=task_id, status="ready")

        assert "updated" in result.lower() or "success" in result.lower()

        # Verify
        with db_module.get_session() as session:
            task = session.get(Task, task_id)
            assert task.status == TaskStatus.READY


class TestWorkspaceAcquire:
    """Tests for workspace_acquire MCP tool."""

    def test_workspace_acquire_creates_worktree(self, server_db_setup):
        """workspace_acquire should create worktree and update task."""
        from autopilot import server

        # Setup mock
        mock_gm = MagicMock()
        mock_gm.create_worktree.return_value = "/path/to/worktree"
        server.git_manager = mock_gm

        try:
            # Create task directly in READY status
            with db_module.get_session() as session:
                task = Task(
                    jira_id="PROJ-1",
                    title="Task",
                    prompt_payload="x",
                    status=TaskStatus.READY,
                    sort_order=1,
                )
                session.add(task)
                session.commit()
                task_id = task.id

            # Acquire workspace
            result = workspace_acquire(task_id=task_id)

            assert "worktree" in result.lower() or "acquired" in result.lower()

            # Verify task was updated
            with db_module.get_session() as session:
                task = session.get(Task, task_id)
                assert task.status == TaskStatus.IN_PROGRESS
                assert task.worktree_path == "/path/to/worktree"
        finally:
            # Restore
            from autopilot.git_manager import GitManager

            server.git_manager = GitManager()


class TestWorkspaceSubmit:
    """Tests for workspace_submit MCP tool."""

    def test_workspace_submit_marks_for_review(self, server_db_setup):
        """workspace_submit should mark task for review."""
        from autopilot import server

        # Mock git_manager.commit_task to avoid actual git operations
        server.git_manager.commit_task = MagicMock()  # type: ignore[assignment]

        # Create task with worktree
        with db_module.get_session() as session:
            task = Task(
                jira_id="PROJ-1",
                title="Task",
                prompt_payload="x",
                status=TaskStatus.IN_PROGRESS,
                sort_order=1,
                worktree_path="/path/to/worktree",
                branch_name="feat/proj-1/1",
            )
            session.add(task)
            session.commit()
            task_id = task.id

        result = workspace_submit(task_id=task_id)

        assert "review" in result.lower() or "submitted" in result.lower()

        # Verify status changed
        with db_module.get_session() as session:
            task = session.get(Task, task_id)
            assert task.status == TaskStatus.IN_REVIEW


class TestReviewApprove:
    """Tests for review_approve MCP tool."""

    def test_review_approve_marks_done(self, server_db_setup):
        """review_approve should mark task as DONE."""
        # Create task in review
        with db_module.get_session() as session:
            task = Task(
                jira_id="PROJ-1",
                title="Task",
                prompt_payload="x",
                status=TaskStatus.IN_REVIEW,
                sort_order=1,
                worktree_path="/path/to/worktree",
                branch_name="feat/proj-1/1",
            )
            session.add(task)
            session.commit()
            task_id = task.id

        result = review_approve(task_id=task_id)

        assert "approved" in result.lower() or "done" in result.lower()

        # Verify status changed
        with db_module.get_session() as session:
            task = session.get(Task, task_id)
            assert task.status == TaskStatus.DONE


class TestReviewReject:
    """Tests for review_reject MCP tool."""

    def test_review_reject_returns_to_in_progress(self, server_db_setup):
        """review_reject should return task to IN_PROGRESS."""
        # Create task in review
        with db_module.get_session() as session:
            task = Task(
                jira_id="PROJ-1",
                title="Task",
                prompt_payload="x",
                status=TaskStatus.IN_REVIEW,
                sort_order=1,
                worktree_path="/path/to/worktree",
                branch_name="feat/proj-1/1",
            )
            session.add(task)
            session.commit()
            task_id = task.id

        result = review_reject(task_id=task_id, feedback="Fix the bug")

        assert "in_progress" in result.lower()

        # Verify status changed back to IN_PROGRESS
        with db_module.get_session() as session:
            task = session.get(Task, task_id)
            assert task.status == TaskStatus.IN_PROGRESS
            assert task.test_feedback == "Fix the bug"
