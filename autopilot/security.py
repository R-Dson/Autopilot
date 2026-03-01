import re


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
