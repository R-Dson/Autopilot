"""Acceptance tests for organized worktree management."""

import pytest
import subprocess
from pathlib import Path
from autopilot.git_manager import GitManager


def _init_git_repo_with_commit(tmp_path):
    """Helper function to initialize a git repo with an initial commit."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", "main"], cwd=tmp_path, check=True, capture_output=True
    )

    # Create initial commit
    (tmp_path / "README.md").write_text("# Test Repo")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )


class TestWorktreeInWorktreesDir:
    """Tests for worktrees created in .worktrees directory."""

    def test_worktree_created_in_worktrees_dir(self, tmp_path, monkeypatch):
        """AT1: Verify worktree is created in .worktrees directory."""
        monkeypatch.chdir(tmp_path)

        # Initialize git repo
        _init_git_repo_with_commit(tmp_path)

        gm = GitManager(str(tmp_path))

        # Create worktree
        worktree_path = gm.create_worktree("FEAT-01")

        # Verify worktree is in .worktrees directory
        assert ".worktrees" in worktree_path
        assert "FEAT-01" in worktree_path
        assert str(tmp_path) in worktree_path

        # Verify .worktrees directory exists
        worktrees_dir = tmp_path / ".worktrees"
        assert worktrees_dir.exists()
        assert worktrees_dir.is_dir()

    def test_gitignore_updated(self, tmp_path, monkeypatch):
        """AT2: Verify .worktrees is added to .gitignore."""
        monkeypatch.chdir(tmp_path)

        # Initialize git repo without .gitignore
        _init_git_repo_with_commit(tmp_path)

        gm = GitManager(str(tmp_path))

        # Create worktree (should trigger .gitignore update)
        gm.create_worktree("FEAT-01")

        # Verify .gitignore exists and contains .worktrees
        gitignore_path = tmp_path / ".gitignore"
        assert gitignore_path.exists()

        gitignore_content = gitignore_path.read_text()
        assert ".worktrees" in gitignore_content

    def test_gitignore_preserves_existing_content(self, tmp_path, monkeypatch):
        """Verify .gitignore preserves existing content when adding .worktrees."""
        monkeypatch.chdir(tmp_path)

        # Initialize git repo
        _init_git_repo_with_commit(tmp_path)

        # Create .gitignore with existing content
        gitignore_path = tmp_path / ".gitignore"
        gitignore_path.write_text("node_modules/\n*.pyc\n")
        original_content = gitignore_path.read_text()

        gm = GitManager(str(tmp_path))

        # Create worktree (should trigger .gitignore update)
        gm.create_worktree("FEAT-01")

        # Verify original content is preserved
        gitignore_content = gitignore_path.read_text()
        assert "node_modules/" in gitignore_content
        assert "*.pyc" in gitignore_content

        # Verify .worktrees was added
        assert ".worktrees" in gitignore_content

    def test_gitignore_no_duplicate_entries(self, tmp_path, monkeypatch):
        """Verify .worktrees is not added twice to .gitignore."""
        monkeypatch.chdir(tmp_path)

        # Initialize git repo
        _init_git_repo_with_commit(tmp_path)

        gm = GitManager(str(tmp_path))

        # Create first worktree (adds .worktrees to .gitignore)
        gm.create_worktree("FEAT-01")

        gitignore_path = tmp_path / ".gitignore"
        first_content = gitignore_path.read_text()

        # Create second worktree (should not add duplicate)
        gm.create_worktree("FEAT-02")

        second_content = gitignore_path.read_text()

        # Verify .worktrees appears only once
        assert first_content == second_content
        assert second_content.count(".worktrees") == 1

    def test_multiple_worktrees_in_worktrees_dir(self, tmp_path, monkeypatch):
        """AT3: Verify multiple worktrees are created in .worktrees directory."""
        monkeypatch.chdir(tmp_path)

        # Initialize git repo
        _init_git_repo_with_commit(tmp_path)

        gm = GitManager(str(tmp_path))

        # Create multiple worktrees
        gm.create_worktree("FEAT-01")
        gm.create_worktree("FEAT-02")

        # Verify both are in .worktrees
        worktrees_dir = tmp_path / ".worktrees"
        worktrees = list(worktrees_dir.iterdir())

        assert len(worktrees) == 2
        assert any("FEAT-01" in w.name for w in worktrees)
        assert any("FEAT-02" in w.name for w in worktrees)

    def test_parallel_worktrees_in_worktrees_dir(self, tmp_path, monkeypatch):
        """AT4: Verify parallel worktrees use correct naming in .worktrees.

        NOTE: Git does not support multiple worktrees pointing to the same branch.
        This test verifies the naming convention only, not actual parallel execution.
        """
        monkeypatch.chdir(tmp_path)

        # Initialize git repo
        _init_git_repo_with_commit(tmp_path)

        gm = GitManager(str(tmp_path))

        # Create first parallel worktree
        worktree1 = gm.create_worktree("FEAT-03", parallel_id=1)

        # Verify naming convention (even though second one would fail to create)
        assert ".worktrees" in worktree1
        assert "FEAT-03-1" in worktree1

        # Cannot create second worktree for same branch due to git limitation
        # The naming convention would be: repo-FEAT-03-2
        with pytest.raises(RuntimeError, match="already used by worktree"):
            gm.create_worktree("FEAT-03", parallel_id=2)

    def test_worktree_path_clarity(self, tmp_path, monkeypatch):
        """AT5: Verify worktree path clearly identifies repo and feature."""
        monkeypatch.chdir(tmp_path)

        # Initialize git repo with specific name
        _init_git_repo_with_commit(tmp_path)

        gm = GitManager(str(tmp_path))

        # Create worktree
        worktree_path = gm.create_worktree("FEAT-04")

        # Extract components from path
        path_parts = Path(worktree_path).parts

        # Verify clarity: path contains repo name, ".worktrees", and feature ID
        assert tmp_path.name in path_parts or str(tmp_path) in worktree_path
        assert ".worktrees" in path_parts
        assert "FEAT-04" in str(worktree_path)

        # Verify reviewer can parse components
        assert "FEAT-04" in worktree_path
        assert ".worktrees" in worktree_path

    def test_worktrees_dir_created_if_not_exists(self, tmp_path, monkeypatch):
        """Verify .worktrees directory is created if it doesn't exist."""
        monkeypatch.chdir(tmp_path)

        # Initialize git repo
        _init_git_repo_with_commit(tmp_path)

        # Verify .worktrees doesn't exist initially
        worktrees_dir = tmp_path / ".worktrees"
        assert not worktrees_dir.exists()

        gm = GitManager(str(tmp_path))

        # Create worktree (should create .worktrees directory)
        worktree_path = gm.create_worktree("FEAT-01")

        # Verify .worktrees directory now exists
        assert worktrees_dir.exists()
        assert worktrees_dir.is_dir()

    def test_worktree_reuses_existing_in_worktrees_dir(self, tmp_path, monkeypatch):
        """Verify worktree reuse works with .worktrees directory."""
        monkeypatch.chdir(tmp_path)

        # Initialize git repo
        _init_git_repo_with_commit(tmp_path)

        gm = GitManager(str(tmp_path))

        # Create worktree first time
        worktree_path1 = gm.create_worktree("FEAT-01")

        # Create worktree second time (should reuse)
        worktree_path2 = gm.create_worktree("FEAT-01")

        # Verify both paths are the same
        assert worktree_path1 == worktree_path2

        # Verify only one worktree exists in .worktrees
        worktrees_dir = tmp_path / ".worktrees"
        worktrees = list(worktrees_dir.iterdir())
        assert len(worktrees) == 1
