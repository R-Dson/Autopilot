import pytest
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
from autopilot.security import validate_paths, validate_repo_root
from autopilot.git_manager import GitManager
from autopilot.server import _get_git_manager, git_diff, git_restore, git_add


def test_validate_paths_valid():
    validate_paths(["src/main.py"])
    validate_paths(["README.md"])
    validate_paths(["docs/index.html"])
    validate_paths(["src/main.py", "tests/test.py"])


def test_validate_paths_argument_injection():
    with pytest.raises(ValueError, match="Paths cannot start with"):
        validate_paths(["--no-index"])
    with pytest.raises(ValueError, match="Paths cannot start with"):
        validate_paths(["-f"])
    with pytest.raises(ValueError, match="Paths cannot start with"):
        validate_paths(["valid.py", "--evil"])


def test_validate_paths_traversal():
    with pytest.raises(ValueError, match="Path traversal with '..' is not allowed"):
        validate_paths(["../etc/passwd"])
    with pytest.raises(ValueError, match="Path traversal with '..' is not allowed"):
        validate_paths(["src/../../etc/passwd"])


def test_validate_paths_absolute():
    with pytest.raises(ValueError, match="Absolute paths are not allowed"):
        validate_paths(["/etc/passwd"])
    if os.name == "nt":
        with pytest.raises(ValueError, match="Absolute paths are not allowed"):
            validate_paths(["C:\\Windows\\system32\\drivers\\etc\\hosts"])


def test_validate_repo_root_valid():
    validate_repo_root("/var/home/me/git/Autopilot", allowed_bases=["/var/home/me/git"])
    validate_repo_root(
        "/var/home/me/git/some-other-repo", allowed_bases=["/var/home/me/git"]
    )
    validate_repo_root(
        "/var/home/me/git/Autopilot", allowed_bases=["/var/home/me/git/Autopilot"]
    )
    validate_repo_root(
        "/var/home/me/git/Autopilot",
        allowed_bases=["/var/home/me/git/Autopilot/subdir"],
    )  # Parent allowed


def test_validate_repo_root_invalid():
    with pytest.raises(
        ValueError, match="Must be within one of the allowed directories"
    ):
        validate_repo_root("/tmp/malicious", allowed_bases=["/var/home/me/git"])
    with pytest.raises(
        ValueError, match="Must be within one of the allowed directories"
    ):
        validate_repo_root("/var/home/me/secret", allowed_bases=["/var/home/me/git"])


def test_git_diff_security_validation():
    with patch("autopilot.server._get_git_manager") as mock_get_gm:
        mock_gm = MagicMock()
        mock_get_gm.return_value = mock_gm

        result = git_diff(paths=["--no-index", "/etc/passwd"])
        assert "Error: Invalid path: '--no-index'" in result
        mock_gm.get_diff.assert_not_called()


def test_git_restore_security_validation():
    with patch("autopilot.server._get_git_manager") as mock_get_gm:
        mock_gm = MagicMock()
        mock_get_gm.return_value = mock_gm

        result = git_restore(files=["../outside.py"])
        assert "Error: Invalid path: '../outside.py'" in result
        mock_gm.restore.assert_not_called()


def test_git_add_security_validation():
    with patch("autopilot.server._get_git_manager") as mock_get_gm:
        mock_gm = MagicMock()
        mock_get_gm.return_value = mock_gm

        result = git_add(files=["/absolute/path.py"])
        assert "Error: Invalid path: '/absolute/path.py'" in result
        mock_gm.add.assert_not_called()


def test_server_repo_root_validation():
    with pytest.raises(
        ValueError, match="Must be within one of the allowed directories"
    ):
        _get_git_manager("/tmp/outside")


@patch("autopilot.git_manager.Repo")
def test_git_manager_diff_uses_separator(mock_repo):
    gm = GitManager("/var/home/me/git/Autopilot")
    gm.get_diff(["file1.py", "file2.py"])

    gm.repo.git.diff.assert_called_with("--", "file1.py", "file2.py")


@patch("autopilot.git_manager.Repo")
def test_git_manager_restore_uses_separator(mock_repo):
    gm = GitManager("/var/home/me/git/Autopilot")
    gm.restore(["file1.py"])

    gm.repo.git.restore.assert_called_with("--", "file1.py")
