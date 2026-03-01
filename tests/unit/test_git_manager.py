"""Unit tests for GitManager."""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import git

from autopilot.git_manager import GitManager


class TestGitManagerInit:
    """Tests for GitManager initialization."""

    @patch("autopilot.git_manager.Repo")
    def test_init_with_default_path(self, mock_repo, tmp_path):
        """GitManager should initialize with current directory."""
        with patch("pathlib.Path.resolve", return_value=tmp_path):
            gm = GitManager()
            assert gm.repo_path == tmp_path
            mock_repo.assert_called_once_with(tmp_path)

    @patch("autopilot.git_manager.Repo")
    def test_init_with_custom_path(self, mock_repo, tmp_path):
        """GitManager should initialize with custom path."""
        gm = GitManager(repo_path=str(tmp_path))
        assert gm.repo_path == tmp_path
        mock_repo.assert_called_once_with(tmp_path)

    @patch("autopilot.git_manager.Repo")
    def test_init_invalid_repo(self, mock_repo, tmp_path):
        """GitManager should raise ValueError for invalid repo."""
        mock_repo.side_effect = git.exc.InvalidGitRepositoryError("Invalid repo")
        with pytest.raises(ValueError, match="Invalid git repository"):
            GitManager(repo_path=str(tmp_path))


class TestGitManagerWorktree:
    """Tests for worktree operations."""

    @patch("autopilot.git_manager.Repo")
    def test_create_worktree_calls_gitpython(self, mock_repo_class, tmp_path):
        """create_worktree should call repo.git.worktree."""
        mock_repo = mock_repo_class.return_value
        gm = GitManager(repo_path=str(tmp_path))

        with patch.object(gm, "_ensure_branch"):
            with patch.object(Path, "exists", return_value=False):
                _ = gm.create_worktree("PROJ-1", 1)

        # Should have called repo.git.worktree('add', ...)
        mock_repo.git.worktree.assert_called()
        args, _ = mock_repo.git.worktree.call_args
        assert "add" in args

    @patch("autopilot.git_manager.Repo")
    def test_create_worktree_returns_path(self, mock_repo_class, tmp_path):
        """create_worktree should return the worktree path."""
        gm = GitManager(repo_path=str(tmp_path))

        # Mock exists to return False (worktree doesn't exist yet)
        with patch.object(Path, "exists", return_value=False):
            with patch.object(gm, "_ensure_branch"):
                result = gm.create_worktree("PROJ-1", 1)

        # Result should contain the jira_id and task_id
        assert "PROJ-1" in result
        assert "1" in result

    @patch("autopilot.git_manager.Repo")
    def test_create_worktree_reuses_existing(self, mock_repo_class, tmp_path):
        """create_worktree should reuse existing worktree."""
        mock_repo = mock_repo_class.return_value
        gm = GitManager(repo_path=str(tmp_path))

        # Mock exists to return True (worktree already exists)
        with patch.object(Path, "exists", return_value=True):
            result = gm.create_worktree("PROJ-1", 1)

        # Should return path without creating new worktree
        assert "PROJ-1" in result
        # Should NOT call repo.git.worktree or _ensure_branch if worktree exists
        mock_repo.git.worktree.assert_not_called()

    @patch("autopilot.git_manager.Repo")
    def test_ensure_branch_creates_if_missing(self, mock_repo_class, tmp_path):
        """_ensure_branch should create branch if it doesn't exist."""
        mock_repo = mock_repo_class.return_value
        mock_repo.heads = {}  # Branch doesn't exist

        gm = GitManager(repo_path=str(tmp_path))
        gm._ensure_branch("feat/PROJ-1")

        # Should have called create_head
        mock_repo.create_head.assert_called_once_with("feat/PROJ-1")

    @patch("autopilot.git_manager.Repo")
    def test_commit_task_calls_gitpython(self, mock_repo_class, tmp_path):
        """commit_task should add and commit changes using GitPython."""
        # We need to mock the Repo(worktree_path) call inside commit_task
        with patch("autopilot.git_manager.Repo") as mock_repo_init:
            mock_wt_repo = MagicMock()
            mock_repo_init.side_effect = [
                MagicMock(),
                mock_wt_repo,
            ]  # First for gm.__init__, second for commit_task

            gm = GitManager(repo_path=str(tmp_path))
            gm.commit_task("/fake/path", "PROJ-1", "Fix bug", 1)

            # Should have called git add and commit on the worktree repo
            mock_wt_repo.git.add.assert_called_once_with(A=True)
            mock_wt_repo.index.commit.assert_called()

    @patch("autopilot.git_manager.Repo")
    def test_merge_task_checkouts_and_merges(self, mock_repo_class, tmp_path):
        """merge_task should checkout and merge."""
        with patch("autopilot.git_manager.Repo") as mock_repo_init:
            mock_wt_repo = MagicMock()
            mock_repo_init.side_effect = [MagicMock(), mock_wt_repo]

            gm = GitManager(repo_path=str(tmp_path))
            gm.merge_task("/fake/path", "feat/proj-1-T1", "main")

            # Should have called checkout and merge
            mock_wt_repo.git.checkout.assert_called_with("main")
            mock_wt_repo.git.merge.assert_called()

    @patch("autopilot.git_manager.Repo")
    def test_cleanup_worktree_removes_worktree(self, mock_repo_class, tmp_path):
        """cleanup_worktree should remove the worktree."""
        mock_repo = mock_repo_class.return_value
        gm = GitManager(repo_path=str(tmp_path))
        gm.cleanup_worktree("/fake/path")

        # Should have called repo.git.worktree('remove', ...)
        mock_repo.git.worktree.assert_called()
        args, _ = mock_repo.git.worktree.call_args
        assert "remove" in args


class TestGitManagerPush:
    """Tests for push operations."""

    @patch("autopilot.git_manager.Repo")
    def test_push_branch_calls_git_push(self, mock_repo_class, tmp_path):
        """push_branch should call git push."""
        mock_repo = mock_repo_class.return_value
        mock_remote = MagicMock()
        mock_repo.remote.return_value = mock_remote

        gm = GitManager(repo_path=str(tmp_path))
        gm.push_branch("PROJ-1")

        # Should have called push on the remote
        mock_repo.remote.assert_called_once_with(name="origin")
        mock_remote.push.assert_called_once()
