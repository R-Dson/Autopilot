"""Integration tests for MCP tools (server functions)."""

import pytest
from unittest.mock import MagicMock, patch
from sqlmodel import Session, select

from autopilot.models import Task, TaskStatus
from autopilot import db
from autopilot.server import (
    tasks_create,
    tasks_list,
    tasks_update,
    workspace_acquire,
    workspace_submit,
    review_approve,
    review_reject,
)


@pytest.fixture(autouse=True)
def setup_db():
    """Ensure DB is initialized before each test."""
    db.init_db()


class TestTasksCreate:
    """Tests for tasks_create MCP tool."""

    def test_tasks_create_single_task(self):
        """tasks_create should add a single task."""
        result = tasks_create(
            jira_id="PROJ-1",
            tasks=[
                {
                    "title": "Implement feature X",
                    "prompt_payload": "Add feature X to the codebase",
                }
            ],
        )

        assert "created" in result.lower()

        # Verify task was created
        with Session(db.engine) as session:
            tasks = session.exec(select(Task)).all()
            assert len(tasks) == 1
            assert tasks[0].title == "Implement feature X"
            assert tasks[0].status == TaskStatus.READY


class TestTasksList:
    """Tests for tasks_list MCP tool."""

    def test_tasks_list_returns_all(self):
        """tasks_list should return all tasks."""
        # Create tasks
        tasks_create(
            jira_id="PROJ-1",
            tasks=[{"title": "Task 1", "prompt_payload": "x"}],
        )

        result = tasks_list()

        assert "Task 1" in str(result)

    def test_tasks_list_filters_by_status(self, session):
        """tasks_list should filter by status."""
        # Create task
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

    def test_tasks_update_changes_status(self):
        """tasks_update should change task status."""
        # Create task
        tasks_create(
            jira_id="PROJ-1",
            tasks=[{"title": "Task", "prompt_payload": "x"}],
        )

        # Get task ID
        with Session(db.engine) as session:
            task = session.exec(select(Task)).first()
            assert task is not None
            task_id = task.id

        # Update status
        result = tasks_update(task_id=task_id, status="in_progress")

        assert "updated" in result.lower()

        # Verify
        with Session(db.engine) as session:
            session.expire_all()
            updated_task = session.get(Task, task_id)
            assert updated_task is not None
            assert updated_task.status == TaskStatus.IN_PROGRESS


class TestWorkspaceAcquire:
    """Tests for workspace_acquire MCP tool."""

    def test_workspace_acquire_creates_worktree(self, session):
        """workspace_acquire should create worktree and update task."""
        # Setup mock for _get_git_manager to return a mocked GitManager
        mock_gm = MagicMock()
        mock_gm.create_worktree.return_value = "/path/to/worktree"

        with patch("autopilot.server._get_git_manager", return_value=mock_gm):
            # Create task directly in READY status
            task = Task(
                jira_id="PROJ-1",
                title="Task",
                prompt_payload="x",
                status=TaskStatus.READY,
                sort_order=1,
            )
            session.add(task)
            session.commit()
            session.refresh(task)

            task_id = task.id

            # Acquire workspace
            result = workspace_acquire(task_id=task_id)

            assert "/path/to/worktree" in result

            # Verify task was updated
            session.expire_all()
            updated_task = session.get(Task, task_id)
            assert updated_task.status == TaskStatus.IN_PROGRESS
            assert updated_task.worktree_path == "/path/to/worktree"


class TestWorkspaceSubmit:
    """Tests for workspace_submit MCP tool."""

    def test_workspace_submit_marks_for_review(self, session):
        """workspace_submit should mark task for review."""
        # Mock _get_git_manager to avoid actual git operations
        mock_gm = MagicMock()
        mock_gm.commit_task = MagicMock()

        with patch("autopilot.server._get_git_manager", return_value=mock_gm):
            # Create task with worktree
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
            session.refresh(task)
            task_id = task.id

            result = workspace_submit(task_id=task_id)

            assert "review" in result.lower()

            # Verify status changed
            session.expire_all()
            updated_task = session.get(Task, task_id)
            assert updated_task.status == TaskStatus.IN_REVIEW


class TestReviewApprove:
    """Tests for review_approve MCP tool."""

    def test_review_approve_marks_done(self, session):
        """review_approve should mark task as DONE."""
        # Create task in review
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
        session.refresh(task)
        task_id = task.id

        result = review_approve(task_id=task_id)

        assert "done" in result.lower()

        # Verify status changed
        session.expire_all()
        updated_task = session.get(Task, task_id)
        assert updated_task.status == TaskStatus.DONE


class TestReviewReject:
    """Tests for review_reject MCP tool."""

    def test_review_reject_returns_to_in_progress(self, session):
        """review_reject should return task to IN_PROGRESS."""
        # Create task in review
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
        session.refresh(task)
        task_id = task.id

        result = review_reject(task_id=task_id, feedback="Fix the bug")

        assert "in_progress" in result.lower()

        # Verify status changed back to IN_PROGRESS
        session.expire_all()
        updated_task = session.get(Task, task_id)
        assert updated_task.status == TaskStatus.IN_PROGRESS
        assert updated_task.test_feedback == "Fix the bug"
