import subprocess
from pathlib import Path
import logging
from typing import Optional
from .security import validate_jira_id

logger = logging.getLogger(__name__)


class GitManager:
    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path).resolve()
        if not self.repo_path.exists():
            raise ValueError(f"Repository path does not exist: {self.repo_path}")

    def _run_git(
        self, args: list, cwd: Optional[str] = None, check: bool = True
    ) -> str:
        """Run a git command and return stdout, or raise RuntimeError on failure."""
        if cwd is None:
            cwd = str(self.repo_path)
        try:
            result = subprocess.run(
                args,
                cwd=cwd,
                check=check,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            error_msg = f"Git command failed: {' '.join(args)}\n"
            if e.stderr:
                error_msg += f"Error: {e.stderr}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def create_worktree(self, jira_id: str, task_id: int) -> str:
        """
        Creates a git worktree for the specific task.
        Branch: feat/{jira_id}-T{task_id}
        Worktree: {repo_name}-{jira_id}-{task_id}
        """
        validate_jira_id(jira_id)
        task_branch = f"feat/{jira_id}-T{task_id}"
        base_branch = f"feat/{jira_id}"  # The main feature branch
        worktree_path = (
            self.repo_path.parent / f"{self.repo_path.name}-{jira_id}-{task_id}"
        )

        # Check if worktree already exists - return early if so
        if worktree_path.exists():
            logger.info(f"Worktree already exists: {worktree_path}")
            return str(worktree_path.resolve())

        # Ensure base feature branch exists
        self._ensure_branch(base_branch)

        # Create worktree
        try:
            # Try to create new branch off base feature branch
            self._run_git(
                [
                    "git",
                    "worktree",
                    "add",
                    str(worktree_path),
                    "-b",
                    task_branch,
                    base_branch,
                ]
            )
            logger.info(f"Created new worktree: {worktree_path}")
        except RuntimeError:
            # If branch already exists, just checkout
            try:
                self._run_git(
                    ["git", "worktree", "add", str(worktree_path), task_branch]
                )
                logger.info(f"Created worktree from existing branch: {worktree_path}")
            except RuntimeError as e:
                logger.error(f"Failed to create worktree: {e}")
                raise

        return str(worktree_path.resolve())

    def _ensure_branch(self, branch_name: str):
        """Ensures a branch exists (creates from current HEAD if needed)."""
        try:
            self._run_git(["git", "rev-parse", "--verify", branch_name])
            logger.info(f"Branch exists: {branch_name}")
        except RuntimeError:
            try:
                self._run_git(["git", "branch", branch_name])
                logger.info(f"Created branch: {branch_name}")
            except RuntimeError as e:
                logger.error(f"Failed to create branch {branch_name}: {e}")
                raise

    def commit_task(
        self, worktree_path: str, jira_id: str, task_title: str, task_id: int
    ):
        """Creates an atomic commit for a completed task."""
        self._run_git(["git", "add", "."], cwd=worktree_path)
        message = f"task({jira_id}): {task_title} [T-{task_id}]"
        self._run_git(["git", "commit", "-m", message], cwd=worktree_path)
        logger.info(f"Committed task {task_id} in worktree: {worktree_path}")

    def push_branch(self, jira_id: str):
        """Pushes the feature branch to remote."""
        validate_jira_id(jira_id)
        branch_name = f"feat/{jira_id}"
        self._run_git(["git", "push", "-u", "origin", branch_name])
        logger.info(f"Pushed branch: {branch_name}")

    def merge_task(self, worktree_path: str, task_branch: str, target_branch: str):
        """Merges the task branch into the target branch."""
        # 1. Fetch latest state
        self._run_git(["git", "fetch", "origin"], cwd=worktree_path, check=False)

        # 2. Checkout target branch in worktree
        self._run_git(["git", "checkout", target_branch], cwd=worktree_path)

        # 3. Merge task branch
        try:
            self._run_git(
                ["git", "merge", task_branch, "--no-ff", "-m", f"Merge {task_branch}"],
                cwd=worktree_path,
            )
            logger.info(f"Merged {task_branch} into {target_branch}")
        except RuntimeError as e:
            # If merge conflict, abort merge and raise error
            try:
                self._run_git(
                    ["git", "merge", "--abort"], cwd=worktree_path, check=False
                )
            except RuntimeError:
                pass
            raise RuntimeError(f"Merge conflict: {str(e)}") from e

    def cleanup_worktree(self, worktree_path: str):
        """Removes the worktree and cleans up."""
        self._run_git(["git", "worktree", "remove", "--force", worktree_path])
        logger.info(f"Cleaned up worktree: {worktree_path}")
