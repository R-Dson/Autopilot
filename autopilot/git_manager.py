import subprocess
from pathlib import Path


class GitManager:
    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path).resolve()

    def create_worktree(self, jira_id: str, task_id: int) -> str:
        """
        Creates a git worktree for the specific task.
        Branch: feat/{jira_id}/{task_id}
        Worktree: {repo_name}-{jira_id}-{task_id}
        """
        task_branch = f"feat/{jira_id}/{task_id}"
        base_branch = f"feat/{jira_id}"  # The main feature branch
        worktree_path = (
            self.repo_path.parent / f"{self.repo_path.name}-{jira_id}-{task_id}"
        )

        # Check if worktree already exists - return early if so
        if worktree_path.exists():
            return str(worktree_path.resolve())

        # Ensure base feature branch exists
        self._ensure_branch(base_branch)

        # Create worktree
        try:
            # Try to create new branch off base feature branch
            subprocess.run(
                [
                    "git",
                    "worktree",
                    "add",
                    str(worktree_path),
                    "-b",
                    task_branch,
                    base_branch,
                ],
                cwd=str(self.repo_path),
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            # If branch already exists, just checkout
            subprocess.run(
                ["git", "worktree", "add", str(worktree_path), task_branch],
                cwd=str(self.repo_path),
                check=True,
                capture_output=True,
            )

        return str(worktree_path.resolve())

    def _ensure_branch(self, branch_name: str):
        """Ensures a branch exists (creates from current HEAD if needed)."""
        try:
            subprocess.run(
                ["git", "rev-parse", "--verify", branch_name],
                cwd=str(self.repo_path),
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            subprocess.run(
                ["git", "branch", branch_name],
                cwd=str(self.repo_path),
                check=True,
            )

    def commit_task(
        self, worktree_path: str, jira_id: str, task_title: str, task_id: int
    ):
        """Creates an atomic commit for a completed task."""
        subprocess.run(["git", "add", "."], cwd=worktree_path, check=True)
        message = f"task({jira_id}): {task_title} [T-{task_id}]"
        subprocess.run(["git", "commit", "-m", message], cwd=worktree_path, check=True)

    def push_branch(self, jira_id: str):
        """Pushes the feature branch to remote."""
        branch_name = f"feat/{jira_id}"
        subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            cwd=str(self.repo_path),
            check=True,
            capture_output=True,
        )

    def merge_task(self, worktree_path: str, task_branch: str, target_branch: str):
        """Merges the task branch into the target branch."""
        # 1. Fetch latest state
        subprocess.run(["git", "fetch", "origin"], cwd=worktree_path, check=False)

        # 2. Checkout target branch in worktree
        subprocess.run(
            ["git", "checkout", target_branch], cwd=worktree_path, check=True
        )

        # 3. Merge task branch
        try:
            subprocess.run(
                ["git", "merge", task_branch, "--no-ff", "-m", f"Merge {task_branch}"],
                cwd=worktree_path,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            # If merge conflict, abort merge and raise error
            subprocess.run(["git", "merge", "--abort"], cwd=worktree_path, check=False)
            raise RuntimeError(
                f"Merge conflict: {e.stderr.decode() if e.stderr else str(e)}"
            )

    def cleanup_worktree(self, worktree_path: str):
        """Removes the worktree and cleans up."""
        subprocess.run(
            ["git", "worktree", "remove", "--force", worktree_path],
            cwd=str(self.repo_path),
            check=True,
        )
