import git
from git import Repo
from pathlib import Path
import logging
from typing import List, Optional, Dict

from .security import validate_jira_id

logger = logging.getLogger(__name__)


class GitManager:
    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path).resolve()
        try:
            self.repo = Repo(self.repo_path)
        except (git.exc.InvalidGitRepositoryError, git.exc.NoSuchPathError) as e:
            raise ValueError(f"Invalid git repository at: {self.repo_path}") from e

    def create_worktree(
        self,
        jira_id: str,
        task_id: Optional[int] = None,
        parallel_id: Optional[int] = None,
    ) -> str:
        """
        Creates a git worktree for the feature.
        Branch: feat/{jira_id} (feature-centric workflow, no task branches)
        Worktree: {repo_name}-{jira_id} or {repo_name}-{jira_id}-{parallel_id}

        Args:
            jira_id: JIRA identifier for the feature
            task_id: Task ID (kept for backward compatibility, unused in new workflow)
            parallel_id: Optional parallel worker ID (for parallel execution)

        Returns:
            Path to the created/reused worktree
        """
        validate_jira_id(jira_id)
        feature_branch = f"feat/{jira_id}"

        if parallel_id is not None:
            worktree_path = (
                self.repo_path.parent / f"{self.repo_path.name}-{jira_id}-{parallel_id}"
            )
        else:
            worktree_path = self.repo_path.parent / f"{self.repo_path.name}-{jira_id}"

        # Check if worktree already exists - return early if so
        if worktree_path.exists():
            logger.info(f"Worktree already exists: {worktree_path}")
            return str(worktree_path.resolve())

        # Ensure feature branch exists
        self._ensure_branch(feature_branch)

        # Create worktree pointing to feature branch (no new branch creation)
        try:
            self.repo.git.worktree("add", str(worktree_path), feature_branch)
            logger.info(f"Created worktree for feature branch: {worktree_path}")
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

    def get_status(self) -> Dict[str, List[str] | str]:
        """Returns the current status of the repository."""
        try:
            # Staged changes (diff between HEAD and Index)
            # Handle case where HEAD might not exist (new repo)
            try:
                staged = [
                    item.a_path for item in self.repo.index.diff("HEAD") if item.a_path
                ]
            except (git.exc.BadName, git.exc.GitCommandError):
                # Fallback for new repo: use git command to get staged files
                try:
                    staged_output = self.repo.git.diff("--cached", "--name-only")
                    staged = staged_output.splitlines() if staged_output else []
                except git.exc.GitCommandError:
                    staged = []

            # Unstaged changes (diff between Index and Worktree)
            unstaged = [
                item.a_path for item in self.repo.index.diff(None) if item.a_path
            ]
            # Untracked files
            untracked = self.repo.untracked_files

            branch = "DETACHED"
            try:
                branch = self.repo.active_branch.name
            except (TypeError, git.exc.GitCommandError):
                pass  # HEAD is detached or doesn't exist yet

            return {
                "staged": sorted(list(set(staged))),
                "unstaged": sorted(list(set(unstaged))),
                "untracked": sorted(untracked),
                "branch": branch,
            }
        except Exception as e:
            error_msg = f"Failed to get git status: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def get_diff(self, paths: Optional[List[str]] = None) -> str:
        """Returns the diff for the specified paths or the entire worktree."""
        try:
            if paths:
                return self.repo.git.diff("--", *paths)
            return self.repo.git.diff()
        except git.exc.GitCommandError as e:
            error_msg = f"Failed to get git diff: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def add(self, files: List[str]):
        """Stages specific files."""
        try:
            self.repo.index.add(files)
            logger.info(f"Staged files: {files}")
        except git.exc.GitCommandError as e:
            error_msg = f"Failed to stage files {files}: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def restore(self, files: List[str]):
        """Discards changes in the specified files."""
        try:
            self.repo.git.restore("--", *files)
            logger.info(f"Restored files: {files}")
        except git.exc.GitCommandError as e:
            error_msg = f"Failed to restore files {files}: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def sync_feature_branch(self, worktree_path: str, feature_branch: str):
        """
        Pulls latest changes for feature branch from remote.
        Used in parallel execution to sync changes between workers.
        """
        try:
            wt_repo = Repo(worktree_path)
            wt_repo.remote(name="origin").fetch()
            try:
                wt_repo.git.merge(f"origin/{feature_branch}")
                logger.info(
                    f"Synced feature branch {feature_branch} in {worktree_path}"
                )
            except git.exc.GitCommandError as e:
                if "conflict" in str(e).lower():
                    error_msg = f"Merge conflict when syncing feature branch {feature_branch}: {str(e)}"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg) from e
                else:
                    error_msg = (
                        f"Failed to sync feature branch {feature_branch}: {str(e)}"
                    )
                    logger.error(error_msg)
                    raise RuntimeError(error_msg) from e
        except (
            git.exc.InvalidGitRepositoryError,
            git.exc.GitCommandError,
            ValueError,
        ) as e:
            error_msg = f"Invalid repository or error during sync: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def merge_to_main(self, feature_branch: str) -> str:
        """
        Merges the feature branch into the main branch.
        Returns the merge commit message.
        """
        try:
            # Ensure we're on main branch
            self.repo.git.checkout("main")

            # Pull latest main
            try:
                origin = self.repo.remote(name="origin")
                origin.pull()
            except (git.exc.GitCommandError, ValueError):
                pass  # Ignore if origin not set up

            # Merge feature branch
            self.repo.git.merge(feature_branch, no_ff=True, m=f"Merge {feature_branch}")
            logger.info(f"Merged {feature_branch} into main")
            return f"Successfully merged {feature_branch} into main"
        except git.exc.GitCommandError as e:
            # If merge conflict, abort merge and raise error
            try:
                self.repo.git.merge(abort=True)
            except git.exc.GitCommandError:
                pass
            error_msg = (
                f"Merge conflict when merging {feature_branch} into main: {str(e)}"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
        except (git.exc.InvalidGitRepositoryError, ValueError) as e:
            error_msg = f"Invalid repository or error during merge: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
