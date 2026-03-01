import pytest
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
from autopilot.security import validate_path, validate_repo_root
from autopilot.git_manager import GitManager
from autopilot.server import _get_git_manager, git_diff, git_restore, git_add


def test_validate_path_valid():
    validate_path("src/main.py")
    validate_path("README.md")
    validate_path("docs/index.html")


def test_validate_path_argument_injection():
    with pytest.raises(ValueError, match="Paths starting with '-' are prohibited"):
        validate_path("--no-index")
    with pytest.raises(ValueError, match="Paths starting with '-' are prohibited"):
        validate_path("-f")


def test_validate_path_traversal():
    with pytest.raises(ValueError, match="Path traversal with '..' is prohibited"):
        validate_path("../etc/passwd")
    with pytest.raises(ValueError, match="Path traversal with '..' is prohibited"):
        validate_path("src/../../etc/passwd")


def test_validate_path_absolute():
    with pytest.raises(ValueError, match="Absolute paths are prohibited"):
        validate_path("/etc/passwd")
    if os.name == "nt":
        with pytest.raises(ValueError, match="Absolute paths are prohibited"):
            validate_path("C:\\Windows\\system32\\drivers\\etc\\hosts")


def test_validate_repo_root_valid():
    # Assuming /var/home/me/git/ is the allowed base
    validate_repo_root("/var/home/me/git/Autopilot")
    validate_repo_root("/var/home/me/git/some-other-repo")


def test_validate_repo_root_invalid():
    with pytest.raises(ValueError, match="Repository must be located within"):
        validate_repo_root("/tmp/malicious")
    with pytest.raises(ValueError, match="Repository must be located within"):
        validate_repo_root("/var/home/me/secret")


def test_git_diff_security_validation():
    with patch("autopilot.server._get_git_manager") as mock_get_gm:
        mock_gm = MagicMock()
        mock_get_gm.return_value = mock_gm

        # This should fail validation before calling gm.get_diff
        result = git_diff(paths=["--no-index", "/etc/passwd"])
        assert "Error: Invalid path: '--no-index'" in result
        mock_gm.get_diff.assert_not_called()


def test_git_restore_security_validation():
    with patch("autopilot.server._get_git_manager") as mock_get_gm:
        mock_gm = MagicMock()
        mock_get_gm.return_value = mock_gm

        # This should fail validation before calling gm.restore
        result = git_restore(files=["../outside.py"])
        assert "Error: Invalid path: '../outside.py'" in result
        mock_gm.restore.assert_not_called()


def test_git_add_security_validation():
    with patch("autopilot.server._get_git_manager") as mock_get_gm:
        mock_gm = MagicMock()
        mock_get_gm.return_value = mock_gm

        # This should fail validation before calling gm.add
        result = git_add(files=["/absolute/path.py"])
        assert "Error: Invalid path: '/absolute/path.py'" in result
        mock_gm.add.assert_not_called()


def test_server_repo_root_validation():
    with pytest.raises(ValueError, match="Repository must be located within"):
        _get_git_manager("/tmp/outside")


@patch("autopilot.git_manager.Repo")
def test_git_manager_diff_uses_separator(mock_repo):
    gm = GitManager("/var/home/me/git/Autopilot")
    gm.get_diff(["file1.py", "file2.py"])

    # Check that git.diff was called with "--"
    gm.repo.git.diff.assert_called_with("--", "file1.py", "file2.py")


@patch("autopilot.git_manager.Repo")
def test_git_manager_restore_uses_separator(mock_repo):
    gm = GitManager("/var/home/me/git/Autopilot")
    gm.restore(["file1.py"])

    # Check that git.restore was called with "--"
    gm.repo.git.restore.assert_called_with("--", "file1.py")
