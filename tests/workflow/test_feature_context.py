"""Tests for feature context in workspace_acquire."""

import json
import pytest
from unittest.mock import MagicMock, patch
from sqlmodel import Session, select

from autopilot.models import Task, TaskStatus
from autopilot import db
from autopilot.server import tasks_create, workspace_acquire


@pytest.fixture(autouse=True)
def setup_db():
    """Ensure DB is initialized before each test."""
    db.init_db()


class TestFeatureContext:
    """Tests for feature context returned by workspace_acquire."""

    def test_workspace_acquire_includes_feature_tasks(self, tmp_path, monkeypatch):
        """Verify feature_tasks contains ALL tasks for feature."""
        monkeypatch.chdir(tmp_path)

        # Create feature with 3 tasks
        result = tasks_create(
            jira_id="PROJ-130",
            tasks=[
                {"title": "Task 1", "prompt_payload": "First task"},
                {"title": "Task 2", "prompt_payload": "Second task"},
                {"title": "Task 3", "prompt_payload": "Third task"},
            ],
        )
        assert "created" in result.lower()

        # Get task ID of task 2
        with Session(db.engine) as session:
            tasks = session.exec(select(Task).where(Task.jira_id == "PROJ-130")).all()
            assert len(tasks) == 3
            task_2 = next(t for t in tasks if t.title == "Task 2")
            task_id_2 = task_2.id

        # Acquire task 2
        mock_gm = MagicMock()
        mock_gm.create_worktree.return_value = str(tmp_path / "worktree")

        with patch("autopilot.server._get_git_manager", return_value=mock_gm):
            result = workspace_acquire(task_id=task_id_2)

        data = json.loads(result)

        # Verify structure
        assert "task" in data
        assert "feature_tasks" in data

        # Verify acquired task
        assert data["task"]["id"] == task_id_2
        assert data["task"]["title"] == "Task 2"

        # Verify feature context includes all tasks
        assert len(data["feature_tasks"]) == 3
        assert data["feature_tasks"][0]["title"] == "Task 1"
        assert data["feature_tasks"][1]["title"] == "Task 2"
        assert data["feature_tasks"][2]["title"] == "Task 3"

    def test_feature_tasks_sorted_by_sort_order(self, tmp_path, monkeypatch):
        """Verify feature_tasks is sorted by sort_order."""
        monkeypatch.chdir(tmp_path)

        # Create tasks with custom sort orders
        result = tasks_create(
            jira_id="PROJ-131",
            tasks=[
                {"title": "Task C", "prompt_payload": "..."},
                {"title": "Task A", "prompt_payload": "..."},
                {"title": "Task B", "prompt_payload": "..."},
            ],
        )
        assert "created" in result.lower()

        # Update sort orders
        with Session(db.engine) as session:
            tasks = session.exec(select(Task).where(Task.jira_id == "PROJ-131")).all()
            tasks[0].sort_order = 2
            tasks[1].sort_order = 0
            tasks[2].sort_order = 1
            session.add_all(tasks)
            session.commit()

        # Get task ID of Task A (sort_order 0)
        with Session(db.engine) as session:
            task_a = session.exec(
                select(Task).where(Task.jira_id == "PROJ-131", Task.title == "Task A")
            ).first()
            task_id = task_a.id

        # Acquire task and verify sorting
        mock_gm = MagicMock()
        mock_gm.create_worktree.return_value = str(tmp_path / "worktree")

        with patch("autopilot.server._get_git_manager", return_value=mock_gm):
            result = workspace_acquire(task_id=task_id)

        data = json.loads(result)

        assert data["feature_tasks"][0]["title"] == "Task A"
        assert data["feature_tasks"][1]["title"] == "Task B"
        assert data["feature_tasks"][2]["title"] == "Task C"

    def test_feature_tasks_excludes_transient_fields(self, tmp_path, monkeypatch):
        """Verify transient fields are excluded from feature_tasks."""
        monkeypatch.chdir(tmp_path)

        # Create task and acquire
        result = tasks_create(
            jira_id="PROJ-132",
            tasks=[
                {"title": "Task 1", "prompt_payload": "..."},
            ],
        )
        assert "created" in result.lower()

        # Get task ID
        with Session(db.engine) as session:
            task = session.exec(select(Task).where(Task.jira_id == "PROJ-132")).first()
            assert task is not None
            task_id = task.id

        # Acquire task
        mock_gm = MagicMock()
        mock_gm.create_worktree.return_value = str(tmp_path / "worktree")

        with patch("autopilot.server._get_git_manager", return_value=mock_gm):
            result = workspace_acquire(task_id=task_id)

        data = json.loads(result)

        # Verify feature_tasks has minimal fields
        feature_task = data["feature_tasks"][0]
        assert "id" in feature_task
        assert "jira_id" in feature_task
        assert "title" in feature_task
        assert "prompt_payload" in feature_task
        assert "status" in feature_task
        assert "sort_order" in feature_task

        # Verify transient fields excluded
        assert "worktree_path" not in feature_task
        assert "test_feedback" not in feature_task
        assert "security_feedback" not in feature_task
        assert "test_review_attempts" not in feature_task
        assert "security_review_attempts" not in feature_task

    def test_acquired_task_has_full_fields(self, tmp_path, monkeypatch):
        """Verify acquired task contains all fields."""
        monkeypatch.chdir(tmp_path)

        tasks_create(
            jira_id="PROJ-133", tasks=[{"title": "Task 1", "prompt_payload": "..."}]
        )

        # Get task ID
        with Session(db.engine) as session:
            task = session.exec(select(Task).where(Task.jira_id == "PROJ-133")).first()
            assert task is not None
            task_id = task.id

        # Acquire task
        mock_gm = MagicMock()
        mock_gm.create_worktree.return_value = str(tmp_path / "worktree")

        with patch("autopilot.server._get_git_manager", return_value=mock_gm):
            result = workspace_acquire(task_id=task_id)

        data = json.loads(result)
        acquired_task = data["task"]

        # Verify full task info included
        assert "worktree_path" in acquired_task
        assert "feature_branch" in acquired_task
        assert "branch_name" in acquired_task
        assert acquired_task["worktree_path"] == str(tmp_path / "worktree")
        assert acquired_task["feature_branch"] == "feat/PROJ-133"
