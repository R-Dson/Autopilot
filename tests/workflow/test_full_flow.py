"""End-to-end workflow tests."""

import os
import pytest
from unittest.mock import MagicMock
from sqlmodel import select

from autopilot.models import Task, TaskStatus
from autopilot import db as db_module
from autopilot.server import (
    tasks_create,
    tasks_update,
    workspace_acquire,
    workspace_submit,
    review_approve,
    review_reject,
)


@pytest.fixture
def workflow_db(tmp_path, monkeypatch):
    """Sets up database for workflow tests."""
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    db_module.reset_engine()
    db_module.init_db()
    yield
    os.chdir(original_cwd)
    db_module.reset_engine()


class TestFullWorkflow:
    """Tests the complete task workflow: DRAFT -> READY -> IN_PROGRESS -> IN_REVIEW -> DONE."""

    def test_complete_workflow(self, workflow_db):
        """Test the full task lifecycle."""
        # Phase 1: Create tasks (Architect creates them)
        result = tasks_create(
            jira_id="PROJ-1",
            tasks=[
                {
                    "title": "Implement feature X",
                    "prompt_payload": "Add feature X to codebase",
                    "sort_order": 1,
                }
            ],
        )
        assert "created" in result.lower()

        # Get task ID
        with db_module.get_session() as session:
            task = session.exec(select(Task)).one()
            task_id = task.id
            # tasks_create creates tasks in READY status
            assert task.status == TaskStatus.READY

        # Phase 2: Approve tasks (User approves, Architect sets to READY)
        result = tasks_update(task_id=task_id, status="ready")
        assert "updated" in result.lower() or "success" in result.lower()

        # Verify task is READY
        with db_module.get_session() as session:
            task = session.get(Task, task_id)
            assert task.status == TaskStatus.READY

        # Phase 3: Start work (Manager acquires worktree)
        from autopilot import server

        mock_gm = MagicMock()
        mock_gm.create_worktree.return_value = "/path/to/worktree"
        server.git_manager = mock_gm

        result = workspace_acquire(task_id=task_id)

        # Verify task is IN_PROGRESS with worktree
        with db_module.get_session() as session:
            task = session.get(Task, task_id)
            assert task.status == TaskStatus.IN_PROGRESS
            assert task.worktree_path == "/path/to/worktree"

        # Phase 4: Submit for review (Implementer submits)
        # Mock git commit to avoid real git operations
        mock_gm.commit_task = MagicMock()
        result = workspace_submit(task_id=task_id)
        assert "review" in result.lower()

        # Verify task is IN_REVIEW
        with db_module.get_session() as session:
            task = session.get(Task, task_id)
            assert task.status == TaskStatus.IN_REVIEW

        # Phase 5: Approve (Reviewer approves)
        result = review_approve(task_id=task_id)
        assert "approved" in result.lower() or "done" in result.lower()

        # Verify task is DONE
        with db_module.get_session() as session:
            task = session.get(Task, task_id)
            assert task.status == TaskStatus.DONE

    def test_rejection_workflow(self, workflow_db):
        """Test the rejection flow: IN_REVIEW -> READY -> IN_PROGRESS -> IN_REVIEW."""
        # Setup: Create task and move to IN_REVIEW
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

        # Phase 1: Reviewer rejects
        _ = review_reject(task_id=task_id, feedback="Tests failing")

        # Verify task returns to IN_PROGRESS (not READY - review rejection returns to implement for fixes)
        with db_module.get_session() as session:
            task = session.get(Task, task_id)
            assert task.status == TaskStatus.IN_PROGRESS
            assert task.test_feedback == "Tests failing"

        # Phase 2: Manager acquires worktree again
        from autopilot import server

        mock_gm = MagicMock()
        mock_gm.create_worktree.return_value = "/new/worktree"
        server.git_manager = mock_gm

        _ = workspace_acquire(task_id=task_id)

        # Verify task is IN_PROGRESS
        with db_module.get_session() as session:
            task = session.get(Task, task_id)
            assert task.status == TaskStatus.IN_PROGRESS

    def test_multiple_tasks_workflow(self, workflow_db):
        """Test workflow with multiple tasks."""
        # Create 3 tasks
        tasks_create(
            jira_id="PROJ-1",
            tasks=[
                {"title": "Task 1", "prompt_payload": "x", "sort_order": 1},
                {"title": "Task 2", "prompt_payload": "x", "sort_order": 2},
                {"title": "Task 3", "prompt_payload": "x", "sort_order": 3},
            ],
        )

        # Get all tasks
        from sqlmodel import col

        with db_module.get_session() as session:
            tasks = session.exec(select(Task).order_by(col(Task.sort_order))).all()
            assert len(tasks) == 3
            ids = [t.id for t in tasks]

        # Approve all
        for task_id in ids:
            tasks_update(task_id=task_id, status="ready")

        # Verify all are READY
        with db_module.get_session() as session:
            tasks = session.exec(
                select(Task).where(Task.status == TaskStatus.READY)
            ).all()
            assert len(tasks) == 3
