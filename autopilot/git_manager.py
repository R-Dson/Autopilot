import git
from git import Repo
from pathlib import Path
import logging

from .security import validate_jira_id

logger = logging.getLogger(__name__)


class GitManager:
    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path).resolve()
        try:
            self.repo = Repo(self.repo_path)
        except (git.exc.InvalidGitRepositoryError, git.exc.NoSuchPathError) as e:
            raise ValueError(f"Invalid git repository at: {self.repo_path}") from e

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
            self.repo.git.worktree(
                "add", str(worktree_path), "-b", task_branch, base_branch
            )
            logger.info(f"Created new worktree: {worktree_path}")
        except git.exc.GitCommandError:
            # If branch already exists, just checkout
            try:
                self.repo.git.worktree("add", str(worktree_path), task_branch)
                logger.info(f"Created worktree from existing branch: {worktree_path}")
            except git.exc.GitCommandError as e:
                error_msg = f"Failed to create worktree at {worktree_path}: {str(e)}"
                logger.error(error_msg)
                raise RuntimeError(error_msg) from e

        return str(worktree_path.resolve())

    def _ensure_branch(self, branch_name: str):
        """Ensures a branch exists (creates from current HEAD if needed)."""
        if branch_name in self.repo.heads:
            logger.info(f"Branch exists: {branch_name}")
            return

        try:
            self.repo.create_head(branch_name)
            logger.info(f"Created branch: {branch_name}")
        except git.exc.GitCommandError as e:
            error_msg = f"Failed to create branch {branch_name}: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def commit_task(
        self, worktree_path: str, jira_id: str, task_title: str, task_id: int
    ):
        """Creates an atomic commit for a completed task."""
        try:
            wt_repo = Repo(worktree_path)
            wt_repo.git.add(A=True)  # Equivalent to git add .
            message = f"task({jira_id}): {task_title} [T-{task_id}]"
            wt_repo.index.commit(message)
            logger.info(f"Committed task {task_id} in worktree: {worktree_path}")
        except (git.exc.InvalidGitRepositoryError, git.exc.GitCommandError) as e:
            error_msg = f"Failed to commit task {task_id} at {worktree_path}: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def push_branch(self, jira_id: str):
        """Pushes the feature branch to remote."""
        validate_jira_id(jira_id)
        branch_name = f"feat/{jira_id}"
        try:
            origin = self.repo.remote(name="origin")
            origin.push(refspec=f"{branch_name}:{branch_name}", set_upstream=True)
            logger.info(f"Pushed branch: {branch_name}")
        except (git.exc.GitCommandError, ValueError) as e:
            error_msg = f"Failed to push branch {branch_name}: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def merge_task(self, worktree_path: str, task_branch: str, target_branch: str):
        """Merges the task branch into the target branch."""
        wt_repo = None
        try:
            wt_repo = Repo(worktree_path)
            # 1. Fetch latest state
            try:
                wt_repo.remote(name="origin").fetch()
            except (git.exc.GitCommandError, ValueError):
                pass  # Ignore fetch errors if origin not set up correctly in test

            # 2. Checkout target branch in worktree
            wt_repo.git.checkout(target_branch)

            # 3. Merge task branch
            wt_repo.git.merge(task_branch, no_ff=True, m=f"Merge {task_branch}")
            logger.info(f"Merged {task_branch} into {target_branch}")
        except git.exc.GitCommandError as e:
            # If merge conflict, abort merge and raise error
            if wt_repo:
                try:
                    wt_repo.git.merge(abort=True)
                except git.exc.GitCommandError:
                    pass
            error_msg = f"Merge conflict or error: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
        except (git.exc.InvalidGitRepositoryError, ValueError) as e:
            error_msg = f"Invalid repository or configuration for merge: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def cleanup_worktree(self, worktree_path: str):
        """Removes the worktree and cleans up."""
        try:
            self.repo.git.worktree("remove", "--force", worktree_path)
            logger.info(f"Cleaned up worktree: {worktree_path}")
        except git.exc.GitCommandError as e:
            error_msg = f"Failed to remove worktree {worktree_path}: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
