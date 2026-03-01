import re
from pathlib import Path
import os


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


def validate_path(path_str: str) -> None:
    """
    Validates that path_str:
    1. Does not start with '-' (prevent argument injection).
    2. Does not contain '..' (prevent path traversal).
    3. Is a relative path (prevent path traversal).
    """
    if path_str.startswith("-"):
        raise ValueError(
            f"Invalid path: '{path_str}'. Paths starting with '-' are prohibited to prevent argument injection."
        )

    if ".." in path_str:
        raise ValueError(
            f"Invalid path: '{path_str}'. Path traversal with '..' is prohibited."
        )

    if os.path.isabs(path_str):
        raise ValueError(f"Invalid path: '{path_str}'. Absolute paths are prohibited.")


def validate_repo_root(root_path: str) -> None:
    """
    Validates that root_path:
    1. Is an absolute path.
    2. Starts with an allowed base directory (default: /var/home/me/git/).
    """
    # Allowed base directory
    allowed_base = Path("/var/home/me/git/").resolve()
    target_path = Path(root_path).resolve()

    if not target_path.is_relative_to(allowed_base):
        raise ValueError(
            f"Invalid repo root: '{root_path}'. Repository must be located within '{allowed_base}'."
        )
