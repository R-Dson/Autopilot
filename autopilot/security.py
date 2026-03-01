import re
from pathlib import Path
from typing import List, Optional


def validate_jira_id(jira_id: str) -> None:
    """
    Validates that jira_id only contains alphanumeric characters, dashes, and underscores.
    Rejects any jira_id containing '..', '/', or '\'.
    """
    if not re.match(r"^[a-zA-Z0-9_-]+$", jira_id):
        raise ValueError(
            f"Invalid JIRA ID: '{jira_id}'. "
            "JIRA ID must only contain alphanumeric characters, dashes, and underscores. "
            "Special characters like '/', '\\', or '..' are strictly prohibited."
        )


def validate_repo_root(
    repo_root: str, allowed_bases: Optional[List[str]] = None
) -> None:
    """
    Validates that the repository root is within allowed base directories.
    Defaults to current working directory and its subdirectories.
    Also allows parent directories (using '..') for convenience.
    """
    if allowed_bases is None:
        allowed_bases = ["."]

    repo_path = Path(repo_root).resolve()

    for base in allowed_bases:
        base_path = Path(base).resolve()
        valid = False

        # Check if repo_path is within base_path
        try:
            repo_path.relative_to(base_path)
            valid = True
        except ValueError:
            pass

        # Also check if base_path is within repo_path (allows parent directory access)
        try:
            base_path.relative_to(repo_path)
            valid = True
        except ValueError:
            pass

        if valid:
            return

    raise ValueError(
        f"Invalid repository root: '{repo_root}'. "
        f"Must be within one of the allowed directories or their parents: {allowed_bases}"
    )


def validate_paths(paths: List[str]) -> None:
    """
    Validates that file paths are safe:
    - Must be relative paths (no absolute paths)
    - Must not contain '..' (no path traversal)
    - Must not start with '-' (no flag injection)
    """
    for path in paths:
        if path.startswith("-"):
            raise ValueError(
                f"Invalid path: '{path}'. Paths cannot start with '-' to prevent flag injection."
            )

        if ".." in path:
            raise ValueError(
                f"Invalid path: '{path}'. Path traversal with '..' is not allowed."
            )

        # Check for absolute paths on Unix and Windows
        path_obj = Path(path)
        if path_obj.is_absolute():
            raise ValueError(f"Invalid path: '{path}'. Absolute paths are not allowed.")

        # Also check for Windows-style absolute paths (C:\, \\server\share)
        if len(path) >= 2:
            # Windows drive letter (e.g., "C:\")
            if path[1:2] == ":":
                raise ValueError(
                    f"Invalid path: '{path}'. Absolute paths are not allowed."
                )
            # UNC paths (e.g., "\\server\share")
            if path[:2] == "\\\\":
                raise ValueError(
                    f"Invalid path: '{path}'. Absolute paths are not allowed."
                )
