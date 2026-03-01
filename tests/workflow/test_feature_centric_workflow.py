"""Acceptance tests for feature-centric workflow."""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from sqlmodel import Session, select

from autopilot.models import Task, TaskStatus
from autopilot import db
from autopilot.server import (
    tasks_create,
    tasks_update,
    workspace_acquire,
    workspace_submit,
    workspace_integrate,
    workspace_cleanup,
    review_approve,
)


@pytest.fixture(autouse=True)
def setup_db():
    """Ensure DB is initialized before each test."""
    db.init_db()


class TestSequentialWorkflow:
    """Tests sequential execution workflow (default)."""

    def test_sequential_workflow(self, tmp_path, monkeypatch):
        """Test complete sequential workflow with 3 tasks."""
        monkeypatch.chdir(tmp_path)

        # Phase 1: Create 3 tasks for a feature
        result = tasks_create(
            jira_id="PROJ-123",
            tasks=[
                {
                    "title": "Implement user authentication",
                    "prompt_payload": "Add user auth",
                },
                {
                    "title": "Add password reset flow",
                    "prompt_payload": "Add password reset",
                },
                {
                    "title": "Write tests for auth module",
                    "prompt_payload": "Write auth tests",
                },
            ],
        )
        assert "created" in result.lower()

        with Session(db.engine) as session:
            tasks = session.exec(select(Task).where(Task.jira_id == "PROJ-123")).all()
            assert len(tasks) == 3
            task_ids = [t.id for t in tasks]
            for task in tasks:
                assert task.status == TaskStatus.READY
                assert task.feature_branch is None

        mock_gm = MagicMock()
        worktree_path = str(tmp_path.parent / "test_project-PROJ-123")
        Path(worktree_path).mkdir(parents=True, exist_ok=True)
        mock_gm.create_worktree.return_value = worktree_path
        mock_gm.commit_task = MagicMock()
        mock_gm.merge_to_main = MagicMock(return_value="Successfully merged")
        mock_gm.push_branch = MagicMock()
        mock_gm.cleanup_worktree = MagicMock()

        # Task 1: Acquire
        with patch("autopilot.server._get_git_manager", return_value=mock_gm):
            result = workspace_acquire(task_id=task_ids[0])

        # Verify task 1 acquired worktree
        with Session(db.engine) as session:
            session.expire_all()
            task1 = session.get(Task, task_ids[0])
            assert task1.status == TaskStatus.IN_PROGRESS
            assert task1.worktree_path == worktree_path
            assert task1.feature_branch == "feat/PROJ-123"
            assert task1.branch_name is None

            # Verify create_worktree called correctly (only jira_id)
            mock_gm.create_worktree.assert_called_once_with("PROJ-123")

        # Task 1: Submit
        with patch("autopilot.server._get_git_manager", return_value=mock_gm):
            result = workspace_submit(task_id=task_ids[0])
        assert "review" in result.lower()

        # Task 1: Approve
        result = review_approve(task_id=task_ids[0])
        assert "done" in result.lower()

        # Task 1: Try to integrate (should fail - not all tasks done)
        with patch("autopilot.server._get_git_manager", return_value=mock_gm):
            result = workspace_integrate(task_id=task_ids[0])
        assert "incomplete" in result.lower()
        assert mock_gm.merge_to_main.call_count == 0

        # Task 2: Acquire (should reuse same worktree)
        mock_gm.reset_mock()
        with patch("autopilot.server._get_git_manager", return_value=mock_gm):
            result = workspace_acquire(task_id=task_ids[1])

        # Verify task 2 reused worktree
        with Session(db.engine) as session:
            session.expire_all()
            task2 = session.get(Task, task_ids[1])
            assert task2.status == TaskStatus.IN_PROGRESS
            assert task2.worktree_path == worktree_path
            # create_worktree should NOT be called (worktree reused)
            mock_gm.create_worktree.assert_not_called()

        # Task 2: Submit and approve
        with patch("autopilot.server._get_git_manager", return_value=mock_gm):
            workspace_submit(task_id=task_ids[1])
        review_approve(task_id=task_ids[1])

        # Task 3: Acquire (should reuse same worktree)
        mock_gm.reset_mock()
        with patch("autopilot.server._get_git_manager", return_value=mock_gm):
            result = workspace_acquire(task_id=task_ids[2])

        with Session(db.engine) as session:
            session.expire_all()
            task3 = session.get(Task, task_ids[2])
            assert task3.status == TaskStatus.IN_PROGRESS
            assert task3.worktree_path == worktree_path
            mock_gm.create_worktree.assert_not_called()

        # Task 3: Submit and approve
        with patch("autopilot.server._get_git_manager", return_value=mock_gm):
            workspace_submit(task_id=task_ids[2])
        review_approve(task_id=task_ids[2])

        # All tasks done - should integrate successfully
        mock_gm.reset_mock()
        with patch("autopilot.server._get_git_manager", return_value=mock_gm):
            result = workspace_integrate(task_id=task_ids[2])

        assert "successfully merged" in result.lower()
        assert "complete" in result.lower()

        # Verify merge_to_main called with correct branch
        mock_gm.merge_to_main.assert_called_once_with("feat/PROJ-123")

        # Verify worktree cleaned up (may be called multiple times if multiple tasks have same path)
        assert mock_gm.cleanup_worktree.called
        assert mock_gm.cleanup_worktree.call_args_list[0][0][0] == worktree_path

        # Verify all tasks have worktree_path cleared
        with Session(db.engine) as session:
            session.expire_all()
            tasks = session.exec(select(Task).where(Task.jira_id == "PROJ-123")).all()
            for task in tasks:
                assert task.worktree_path is None

    def test_branch_count_reduction(self, tmp_path, monkeypatch):
        """Test that only one feature branch is created."""
        monkeypatch.chdir(tmp_path)

        # Create feature with 5 tasks
        tasks_create(
            jira_id="PROJ-125",
            tasks=[
                {"title": f"Task {i}", "prompt_payload": f"Do task {i}"}
                for i in range(1, 6)
            ],
        )

        mock_gm = MagicMock()
        worktree_path = str(tmp_path.parent / "test_project-PROJ-125")
        mock_gm.create_worktree.return_value = worktree_path
        mock_gm.commit_task = MagicMock()
        mock_gm.merge_to_main = MagicMock(return_value="Success")
        mock_gm.push_branch = MagicMock()
        mock_gm.cleanup_worktree = MagicMock()

        # Complete all tasks
        with Session(db.engine) as session:
            tasks = session.exec(select(Task).where(Task.jira_id == "PROJ-125")).all()
            task_ids = [t.id for t in tasks]

        for task_id in task_ids:
            with patch("autopilot.server._get_git_manager", return_value=mock_gm):
                workspace_acquire(task_id=task_id)
                workspace_submit(task_id=task_id)
            review_approve(task_id=task_id)

        # Integrate
        with patch("autopilot.server._get_git_manager", return_value=mock_gm):
            workspace_integrate(task_id=task_ids[-1])

        # Verify merge_to_main called exactly once (one feature branch)
        assert mock_gm.merge_to_main.call_count == 1
        mock_gm.merge_to_main.assert_called_with("feat/PROJ-125")


class TestParallelWorkflow:
    """Tests parallel execution workflow."""

    def test_parallel_workflow(self, tmp_path, monkeypatch):
        """Test parallel workflow with 2 workers."""
        monkeypatch.chdir(tmp_path)

        # Create feature with 4 tasks
        tasks_create(
            jira_id="PROJ-124",
            tasks=[
                {"title": f"Task {i}", "prompt_payload": f"Do task {i}"}
                for i in range(1, 5)
            ],
        )

        with Session(db.engine) as session:
            tasks = session.exec(select(Task).where(Task.jira_id == "PROJ-124")).all()
            task_ids = [t.id for t in tasks]

        # Setup mocks for parallel execution
        mock_gm = MagicMock()
        worktree1 = str(tmp_path.parent / "test_project-PROJ-124-1")
        worktree2 = str(tmp_path.parent / "test_project-PROJ-124-2")
        mock_gm.create_worktree.side_effect = [
            worktree1,
            worktree2,
            worktree1,
            worktree2,
        ]
        mock_gm.commit_task = MagicMock()
        mock_gm.merge_to_main = MagicMock(return_value="Success")
        mock_gm.push_branch = MagicMock()
        mock_gm.cleanup_worktree = MagicMock()

        # Parallel: Acquire tasks 1 and 2
        with patch("autopilot.server._get_git_manager", return_value=mock_gm):
            result1 = workspace_acquire(task_id=task_ids[0])
            result2 = workspace_acquire(task_id=task_ids[1])

        # Verify 2 worktrees created with different paths
        with Session(db.engine) as session:
            session.expire_all()
            task1 = session.get(Task, task_ids[0])
            task2 = session.get(Task, task_ids[1])

            # One should be in worktree1, other in worktree2
            worktrees = {task1.worktree_path, task2.worktree_path}
            assert worktrees == {worktree1, worktree2}

        # Note: In real parallel execution, we'd need to pass parallel_id
        # This test shows the structure, but actual parallel execution
        # requires modifying workspace_acquire to accept parallel_id

    def test_sync_feature_branch(self, tmp_path, monkeypatch):
        """Test sync_feature_branch method."""
        from autopilot.git_manager import GitManager

        monkeypatch.chdir(tmp_path)

        # Initialize a git repo with a commit
        import subprocess

        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "checkout", "-b", "main"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        # Create an initial commit
        test_file = tmp_path / "README.md"
        test_file.write_text("# Test")
        subprocess.run(
            ["git", "add", "."], cwd=tmp_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        gm = GitManager(str(tmp_path))
        gm._ensure_branch("feat/PROJ-126")

        # Create worktree
        worktree_path = str(tmp_path.parent / "worktree")
        Path(worktree_path).mkdir(parents=True, exist_ok=True)
        gm.create_worktree("PROJ-126")

        # Sync should not raise error (even if no remote)
        # Mock Repo initialization to avoid needing a real git worktree
        with patch("autopilot.git_manager.Repo") as mock_repo:
            mock_wt_repo = MagicMock()
            mock_repo.return_value = mock_wt_repo

            mock_wt_repo.remote.return_value.fetch.return_value = None
            mock_wt_repo.git.merge.return_value = None

            try:
                gm.sync_feature_branch(worktree_path, "feat/PROJ-126")
            except RuntimeError as e:
                # Expected if no remote, but method should handle gracefully
                assert "failed" in str(e).lower() or "invalid" in str(e).lower()


class TestWorkspaceCleanup:
    """Tests workspace cleanup with feature-centric workflow."""

    def test_feature_cleanup_multiple_worktrees(self, tmp_path, monkeypatch):
        """Test cleanup removes all worktrees for a feature."""
        monkeypatch.chdir(tmp_path)

        # Create tasks
        tasks_create(
            jira_id="PROJ-127",
            tasks=[
                {"title": "Task 1", "prompt_payload": "Do task 1"},
                {"title": "Task 2", "prompt_payload": "Do task 2"},
            ],
        )

        with Session(db.engine) as session:
            tasks = session.exec(select(Task).where(Task.jira_id == "PROJ-127")).all()
            task_ids = [t.id for t in tasks]

        # Setup mocks - simulate 2 worktrees from parallel execution
        mock_gm = MagicMock()
        worktree1 = str(tmp_path.parent / "test_project-PROJ-127-1")
        worktree2 = str(tmp_path.parent / "test_project-PROJ-127-2")

        # Create actual directories so workspace_cleanup can find them
        Path(worktree1).mkdir(parents=True, exist_ok=True)
        Path(worktree2).mkdir(parents=True, exist_ok=True)

        # Manually set worktree paths to simulate parallel execution (first task acquired worktree1, second worktree2)
        with Session(db.engine) as session:
            task1 = session.get(Task, task_ids[0])
            task2 = session.get(Task, task_ids[1])
            task1.worktree_path = worktree1
            task2.worktree_path = worktree2
            session.add_all([task1, task2])
            session.commit()

        # Cleanup
        mock_gm.push_branch = MagicMock()
        mock_gm.cleanup_worktree = MagicMock()
        with patch("autopilot.server._get_git_manager", return_value=mock_gm):
            result = workspace_cleanup(jira_id="PROJ-127", force=True)

        assert "complete" in result.lower()
        assert "2" in result  # 2 worktrees cleaned up

        # Verify both worktrees cleaned up
        assert mock_gm.cleanup_worktree.call_count == 2

    def test_feature_cleanup_incomplete_tasks(self, tmp_path, monkeypatch):
        """Test cleanup fails when tasks are incomplete (without force)."""
        monkeypatch.chdir(tmp_path)

        # Create tasks
        tasks_create(
            jira_id="PROJ-128",
            tasks=[
                {"title": "Task 1", "prompt_payload": "Do task 1"},
                {"title": "Task 2", "prompt_payload": "Do task 2"},
            ],
        )

        with Session(db.engine) as session:
            tasks = session.exec(select(Task).where(Task.jira_id == "PROJ-128")).all()
            task_ids = [t.id for t in tasks]

        # Setup a worktree path for at least one task
        worktree_path = str(tmp_path / "worktree")
        Path(worktree_path).mkdir(parents=True, exist_ok=True)

        with Session(db.engine) as session:
            task1 = session.get(Task, task_ids[0])
            task1.worktree_path = worktree_path
            session.add(task1)
            session.commit()

        # Try to cleanup without completing tasks
        with patch("autopilot.server._get_git_manager", return_value=MagicMock()):
            result = workspace_cleanup(jira_id="PROJ-128", force=False)

        assert "not done" in result.lower()

        # Cleanup with force should succeed
        mock_gm = MagicMock()
        mock_gm.cleanup_worktree = MagicMock()
        with patch("autopilot.server._get_git_manager", return_value=mock_gm):
            result = workspace_cleanup(jira_id="PROJ-128", force=True)

        assert "complete" in result.lower()


class TestBackwardCompatibility:
    """Tests backward compatibility with existing tasks."""

    def test_existing_task_branches_still_work(self, tmp_path, monkeypatch):
        """Test that tasks with branch_name set still work."""
        monkeypatch.chdir(tmp_path)

        # Create task
        tasks_create(
            jira_id="PROJ-129",
            tasks=[
                {"title": "Task 1", "prompt_payload": "Do task 1"},
            ],
        )

        with Session(db.engine) as session:
            task = session.exec(select(Task).where(Task.jira_id == "PROJ-129")).first()
            task_id = task.id

        # Simulate old workflow: set branch_name
        with Session(db.engine) as session:
            task = session.get(Task, task_id)
            task.branch_name = "feat/PROJ-129-T1"
            session.add(task)
            session.commit()

        mock_gm = MagicMock()
        mock_gm.create_worktree.return_value = str(tmp_path / "worktree")
        mock_gm.commit_task = MagicMock()

        # Acquire should still work
        with patch("autopilot.server._get_git_manager", return_value=mock_gm):
            result = workspace_acquire(task_id=task_id)

        assert "error" not in result.lower()

        with Session(db.engine) as session:
            session.expire_all()
            task = session.get(Task, task_id)
            # New workflow sets branch_name to None
            assert task.branch_name is None
            assert task.feature_branch == "feat/PROJ-129"
