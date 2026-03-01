import pytest
import os
import json
import git
from pathlib import Path
from unittest.mock import patch
from autopilot.server import git_status, git_diff, git_add, git_restore
from autopilot.git_manager import GitManager


@pytest.fixture
def temp_repo(tmp_path):
    """Creates a temporary git repository for testing."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    repo = git.Repo.init(repo_path)

    # Configure git for test
    with repo.config_writer() as config:
        config.set_value("user", "name", "Test User")
        config.set_value("user", "email", "test@example.com")

    # Create an initial commit
    test_file = repo_path / "initial.txt"
    test_file.write_text("initial content")
    repo.index.add(["initial.txt"])
    repo.index.commit("Initial commit")

    return repo_path


def test_git_status_tool(temp_repo):
    # Mock security validation to allow temp paths in tests
    with patch("autopilot.server.validate_repo_root"):
        with patch("autopilot.server.validate_paths"):
            # Add a new untracked file
            new_file = temp_repo / "new.txt"
            new_file.write_text("new content")

            # Modify an existing file
            initial_file = temp_repo / "initial.txt"
            initial_file.write_text("modified content")

            result = git_status(repo_root=str(temp_repo))

            assert "initial.txt" in result["unstaged"]
            assert "new.txt" in result["untracked"]
            assert "branch" in result


def test_git_add_tool(temp_repo):
    # Mock security validation to allow temp paths in tests
    with patch("autopilot.server.validate_repo_root"):
        with patch("autopilot.server.validate_paths"):
            new_file = temp_repo / "new.txt"
            new_file.write_text("new content")

            git_add(files=["new.txt"], repo_root=str(temp_repo))

            result = git_status(repo_root=str(temp_repo))

            assert "new.txt" in result["staged"]
            assert "new.txt" not in result["untracked"]


def test_git_status_new_repo(tmp_path):
    """Test git_status on a new repo with no commits."""
    # Mock security validation to allow temp paths in tests
    with patch("autopilot.server.validate_repo_root"):
        with patch("autopilot.server.validate_paths"):
            repo_path = tmp_path / "new_repo"
            repo_path.mkdir()
            repo = git.Repo.init(repo_path)

            # No commits yet
            new_file = repo_path / "new.txt"
            new_file.write_text("new content")

            result = git_status(repo_root=str(repo_path))

            assert "new.txt" in result["untracked"]
            assert result["staged"] == []
            assert result["unstaged"] == []


def test_git_diff_tool(temp_repo):
    # Mock security validation to allow temp paths in tests
    with patch("autopilot.server.validate_repo_root"):
        with patch("autopilot.server.validate_paths"):
            initial_file = temp_repo / "initial.txt"
            initial_file.write_text("modified content")

            diff = git_diff(repo_root=str(temp_repo))
            assert "+modified content" in diff
            assert "-initial content" in diff


def test_git_restore_tool(temp_repo):
    # Mock security validation to allow temp paths in tests
    with patch("autopilot.server.validate_repo_root"):
        with patch("autopilot.server.validate_paths"):
            initial_file = temp_repo / "initial.txt"
            initial_file.write_text("modified content")

            # Verify it is modified
            diff_before = git_diff(repo_root=str(temp_repo))
            assert "+modified content" in diff_before

            git_restore(files=["initial.txt"], repo_root=str(temp_repo))

            # Verify it is restored
            diff_after = git_diff(repo_root=str(temp_repo))
            assert diff_after == ""
            assert initial_file.read_text() == "initial content"
