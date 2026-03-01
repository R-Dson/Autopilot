"""End-to-end workflow tests."""

import pytest
from unittest.mock import MagicMock, patch
from sqlmodel import Session, select

from autopilot.models import Task, TaskStatus
from autopilot import db
from autopilot.server import (
    tasks_create,
    tasks_update,
    workspace_acquire,
    workspace_submit,
    review_approve,
)


@pytest.fixture(autouse=True)
def setup_db():
    """Ensure DB is initialized before each test."""
    db.init_db()


class TestFullWorkflow:
    """Tests the complete task workflow: READY -> IN_PROGRESS -> IN_REVIEW -> DONE."""

    def test_complete_workflow(self, tmp_path, monkeypatch):
        """Test the full task lifecycle."""
        monkeypatch.chdir(tmp_path)

        # Phase 1: Create tasks (Architect creates them)
        result = tasks_create(
            jira_id="PROJ-1",
            tasks=[
                {
                    "title": "Implement feature X",
                    "prompt_payload": "Add feature X to codebase",
                }
            ],
        )
        assert "created" in result.lower()

        # Get task ID
        with Session(db.engine) as session:
            task = session.exec(select(Task)).first()
            assert task is not None
            task_id = task.id
            # tasks_create creates tasks in READY status
            assert task.status == TaskStatus.READY

        # Phase 2: Approve tasks (User approves, Architect sets to READY)
        # Note: Already READY, but we'll test update anyway
        result = tasks_update(task_id=task_id, status="ready")
        assert "updated" in result.lower()

        # Phase 3: Start work (Manager acquires worktree)
        mock_gm = MagicMock()
        mock_gm.create_worktree.return_value = str(tmp_path / "worktree")

        with patch("autopilot.server._get_git_manager", return_value=mock_gm):
            result = workspace_acquire(task_id=task_id)

        # Verify task is IN_PROGRESS with worktree
        with Session(db.engine) as session:
            session.expire_all()
            updated_task = session.get(Task, task_id)
            assert updated_task is not None
            assert updated_task.status == TaskStatus.IN_PROGRESS
            assert updated_task.worktree_path == str(tmp_path / "worktree")

        # Phase 4: Submit for review (Implementer submits)
        # Mock git commit to avoid real git operations
        mock_gm.commit_task = MagicMock()
        with patch("autopilot.server._get_git_manager", return_value=mock_gm):
            result = workspace_submit(task_id=task_id)
        assert "review" in result.lower()

        # Verify task is IN_REVIEW
        with Session(db.engine) as session:
            session.expire_all()
            updated_task = session.get(Task, task_id)
            assert updated_task is not None
            assert updated_task.status == TaskStatus.IN_REVIEW

        # Phase 5: Approve (Reviewer approves)
        result = review_approve(task_id=task_id)
        assert "done" in result.lower()

        # Verify task is DONE
        with Session(db.engine) as session:
            session.expire_all()
            updated_task = session.get(Task, task_id)
            assert updated_task is not None
            assert updated_task.status == TaskStatus.DONE
