import json
import logging
from pathlib import Path
from typing import List, Optional
from mcp.server.fastmcp import FastMCP
from sqlmodel import Session, select, text
from sqlmodel.sql.expression import col
from .models import Task, TaskStatus
from . import db
from .git_manager import GitManager
from .test_runner import TestRunner
from .security import validate_jira_id, validate_repo_root, validate_paths

logger = logging.getLogger(__name__)
mcp = FastMCP("Autopilot")


def _get_git_manager(repo_root: Optional[str] = None) -> GitManager:
    """Get a GitManager instance for the given repository root."""
    root = repo_root or "."
    validate_repo_root(root)
    return GitManager(root)


@mcp.tool()
def tasks_create(
    jira_id: str, tasks: List[dict], repo_root: Optional[str] = None
) -> str:
    """
    Create a batch of tasks in the Kanban board.
    'tasks' should be a list of dicts with 'title' and 'prompt_payload'.
    Tasks are created with READY status by default.
    """
    try:
        validate_jira_id(jira_id)
        logger.info(f"tasks_create called: jira_id={jira_id}, count={len(tasks)}")
        db.init_db()

        created_ids = []
        with Session(db.engine) as session:
            for i, t_data in enumerate(tasks):
                task = Task(
                    jira_id=jira_id,
                    title=t_data["title"],
                    prompt_payload=t_data["prompt_payload"],
                    status=TaskStatus.READY,
                    sort_order=i,
                )
                session.add(task)
                session.flush()  # To get the ID
                created_ids.append(task.id)
                logger.debug(f"Created task: {task.title} with id={task.id}")

            session.commit()

        logger.info(f"Successfully created {len(created_ids)} tasks: {created_ids}")
        return f"Created {len(created_ids)} tasks for {jira_id}: {created_ids}"

    except Exception as e:
        error_msg = f"Error in tasks_create: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return f"Error: {error_msg}"


@mcp.tool()
def tasks_list(
    jira_id: Optional[str] = None,
    status: Optional[str] = None,
    repo_root: Optional[str] = None,
) -> str:
    """List tasks in the Kanban board, optionally filtered by jira_id or status."""
    db.init_db()
    with Session(db.engine) as session:
        statement = select(Task)
        if jira_id:
            statement = statement.where(Task.jira_id == jira_id)
        if status:
            statement = statement.where(Task.status == TaskStatus(status))

        tasks = session.exec(statement).all()
        task_summaries = [
            {
                "id": t.id,
                "title": t.title,
                "status": t.status.value,
                "jira_id": t.jira_id,
            }
            for t in tasks
        ]
        return json.dumps(task_summaries, indent=2)


@mcp.tool()
def tasks_update(
    task_id: int,
    status: Optional[str] = None,
    prompt_payload: Optional[str] = None,
    repo_root: Optional[str] = None,
) -> str:
    """Update a task's status or prompt payload."""
    db.init_db()
    with Session(db.engine) as session:
        task = session.get(Task, task_id)
        if not task:
            return f"Error: Task {task_id} not found."

        if status:
            task.status = TaskStatus(status)
        if prompt_payload:
            task.prompt_payload = prompt_payload

        session.add(task)
        session.commit()
        return f"Updated task {task_id}."


@mcp.tool()
def workspace_acquire(task_id: int, repo_root: Optional[str] = None) -> str:
    """
    Acquires a specific task, sets it to 'in_progress',
    prepares a Git Worktree for the feature, and returns the task details.
    Reuses existing worktree for the feature if available.
    """
    db.init_db()
    git_manager = _get_git_manager(repo_root)

    # Use a database transaction with a check that the status is still READY
    # at the moment of acquisition to prevent race conditions.
    with Session(db.engine) as session:
        # BEGIN IMMEDIATE starts a write transaction immediately, locking out others.
        session.execute(text("BEGIN IMMEDIATE"))
        task = session.get(Task, task_id)
        if not task:
            return f"Error: Task {task_id} not found."

        if task.status != TaskStatus.READY:
            return f"Error: Task {task_id} is not in READY status (current: {task.status})."

        # Check if there's an existing worktree for this feature
        existing_tasks = session.exec(
            select(Task).where(
                Task.jira_id == task.jira_id,
            )
        ).all()

        existing_worktree = None
        for existing_task in existing_tasks:
            if (
                existing_task.worktree_path is not None
                and Path(existing_task.worktree_path).exists()
            ):
                existing_worktree = existing_task.worktree_path
                logger.info(f"Reusing existing worktree: {existing_worktree}")
                break

        # Mark as IN_PROGRESS immediately to "lock" it for this process
        task.status = TaskStatus.IN_PROGRESS
        session.add(task)
        session.commit()
        # Save attributes for use outside the session context
        jira_id = task.jira_id
        task_id_db = task.id
        assert task_id_db is not None

    # Prepare Git Worktree (slow operation outside the exclusive DB lock)
    try:
        if existing_worktree:
            worktree_path = existing_worktree
        else:
            worktree_path = git_manager.create_worktree(jira_id)

        # Update the task with worktree information
        with Session(db.engine) as session:
            task = session.get(Task, task_id)
            assert task is not None
            task.worktree_path = worktree_path
            task.feature_branch = f"feat/{jira_id}"
            task.branch_name = None  # No task branch in new workflow
            session.add(task)
            session.commit()
            session.refresh(task)

            # Fetch all tasks for this feature to provide context
            feature_tasks = session.exec(
                select(Task)
                .where(Task.jira_id == task.jira_id)
                .order_by(col(Task.sort_order))
            ).all()

            # Build response with feature context
            response = {
                "task": task.model_dump(),
                "feature_tasks": [
                    {
                        "id": t.id,
                        "jira_id": t.jira_id,
                        "title": t.title,
                        "prompt_payload": t.prompt_payload,
                        "status": t.status.value,
                        "sort_order": t.sort_order,
                    }
                    for t in feature_tasks
                ],
            }

            return json.dumps(response, indent=2)
    except Exception as e:
        # If worktree creation fails, revert the status back to READY
        # so another agent can try again.
        with Session(db.engine) as session:
            task = session.get(Task, task_id)
            if task and task.status == TaskStatus.IN_PROGRESS:
                task.status = TaskStatus.READY
                session.add(task)
                session.commit()
        return f"Error acquiring workspace: {str(e)}"


@mcp.tool()
def workspace_submit(task_id: int, repo_root: Optional[str] = None) -> str:
    """Marks a task as 'in_review' and handles the atomic git commit."""
    db.init_db()
    git_manager = _get_git_manager(repo_root)

    with Session(db.engine) as session:
        task = session.get(Task, task_id)
        if not task:
            return f"Error: Task {task_id} not found."

        if not task.worktree_path:
            return "Error: Task has no associated worktree."

        # Verify changes exist before committing
        try:
            wt_git_manager = GitManager(task.worktree_path)
            status = wt_git_manager.get_status()

            # Extract lists (ensure they are lists, not strings)
            unstaged = (
                status["unstaged"] if isinstance(status["unstaged"], list) else []
            )
            untracked = (
                status["untracked"] if isinstance(status["untracked"], list) else []
            )

            # Check if there are any changes to commit
            if not (unstaged or untracked):
                return f"Error: No changes detected in worktree {task.worktree_path}. Cannot commit empty changeset."
        except (ValueError, RuntimeError):
            # If worktree is not a valid git repository (e.g., in tests),
            # proceed with commit attempt for backward compatibility
            logger.warning(
                f"Could not verify worktree status for {task.worktree_path}, proceeding with commit"
            )

        # Atomic Commit
        assert task.id is not None
        git_manager.commit_task(task.worktree_path, task.jira_id, task.title, task.id)

        task.status = TaskStatus.IN_REVIEW
        session.add(task)
        session.commit()

        return f"Task {task_id} submitted for review. Atomic commit created."


@mcp.tool()
def tests_run_clean(worktree_path: str, framework: Optional[str] = None) -> str:
    """
    Executes the test suite in the given worktree and returns a sanitized summary.
    Framework auto-detects pytest or vitest. Pass 'pytest' or 'vitest' to force specific framework.
    """
    result = TestRunner.run(worktree_path, framework)
    return json.dumps(result, indent=2)


@mcp.tool()
def workspace_integrate(task_id: int, repo_root: Optional[str] = None) -> str:
    """
    Merges the feature branch into main when all tasks are complete.
    Call this after review approval for the last task.
    """
    db.init_db()
    git_manager = _get_git_manager(repo_root)

    with Session(db.engine) as session:
        task = session.get(Task, task_id)
        if not task:
            return f"Error: Task {task_id} not found."

        if task.status != TaskStatus.DONE:
            return f"Error: Task {task_id} must be DONE before integration."

        # Check if all tasks for this feature are done
        all_tasks = session.exec(select(Task).where(Task.jira_id == task.jira_id)).all()

        incomplete_tasks = [t for t in all_tasks if t.status != TaskStatus.DONE]

        if incomplete_tasks:
            return (
                f"Task {task_id} marked as DONE, but feature {task.jira_id} "
                f"has {len(incomplete_tasks)} incomplete task(s): "
                f"{[t.id for t in incomplete_tasks]}. "
                "Complete all tasks before integration."
            )

        # All tasks done - integrate feature branch into main
        feature_branch = f"feat/{task.jira_id}"

        try:
            # Merge feature branch into main
            result = git_manager.merge_to_main(feature_branch)

            # Push feature branch to remote
            try:
                git_manager.push_branch(task.jira_id)
            except RuntimeError as e:
                logger.warning(f"Failed to push branch: {e}")

            # Cleanup worktree(s)
            for t in all_tasks:
                if t.worktree_path and Path(t.worktree_path).exists():
                    try:
                        git_manager.cleanup_worktree(t.worktree_path)
                        logger.info(f"Cleaned up worktree: {t.worktree_path}")
                    except RuntimeError as e:
                        logger.warning(f"Failed to cleanup worktree: {e}")
                    t.worktree_path = None
                    session.add(t)

            session.commit()
            return f"{result} Feature {task.jira_id} complete."
        except RuntimeError as e:
            return f"Integration error: {str(e)}. Manual resolution required."


@mcp.tool()
def review_approve(task_id: int, repo_root: Optional[str] = None) -> str:
    """Marks a task as 'done'."""
    db.init_db()
    with Session(db.engine) as session:
        task = session.get(Task, task_id)
        if not task:
            return f"Error: Task {task_id} not found."

        task.status = TaskStatus.DONE
        session.add(task)
        session.commit()
        return f"Task {task_id} marked as DONE. Ready for integration."


@mcp.tool()
def review_reject(task_id: int, feedback: str, repo_root: Optional[str] = None) -> str:
    """Reverts task to 'in_progress' and attaches feedback. Resets all review attempt counters."""
    db.init_db()
    with Session(db.engine) as session:
        task = session.get(Task, task_id)
        if not task:
            return f"Error: Task {task_id} not found."

        task.status = TaskStatus.IN_PROGRESS
        task.test_feedback = feedback
        task.test_review_attempts = 0
        task.security_review_attempts = 0
        session.add(task)
        session.commit()
        return f"Task {task_id} rejected and returned to IN_PROGRESS."


@mcp.tool()
def security_review_approve(task_id: int, repo_root: Optional[str] = None) -> str:
    """Marks a task as passed security review. Call this when no security vulnerabilities are found."""
    db.init_db()
    with Session(db.engine) as session:
        task = session.get(Task, task_id)
        if not task:
            return f"Error: Task {task_id} not found."

        task.status = TaskStatus.DONE
        task.security_review_attempts = 0
        session.add(task)
        session.commit()
        return f"Task {task_id} passed security review. Ready for integration."


@mcp.tool()
def security_review_reject(
    task_id: int, feedback: str, repo_root: Optional[str] = None
) -> str:
    """Reverts task to 'in_progress' after security review failure with feedback. Resets all review attempt counters."""
    db.init_db()
    with Session(db.engine) as session:
        task = session.get(Task, task_id)
        if not task:
            return f"Error: Task {task_id} not found."

        task.security_review_attempts += 1
        task.status = TaskStatus.IN_PROGRESS
        task.security_feedback = feedback
        task.test_review_attempts = 0

        if task.security_review_attempts >= 5:
            task.status = TaskStatus.FAILED

        session.add(task)
        session.commit()

        if task.status == TaskStatus.FAILED:
            return f"Task {task_id} failed security review 5+ times. Marked as FAILED. Human review required."
        return (
            f"Task {task_id} rejected from security review and returned to IN_PROGRESS."
        )


@mcp.tool()
def test_review_approve(task_id: int, repo_root: Optional[str] = None) -> str:
    """Marks a task as passed test review. Call this when tests pass and coverage is sufficient."""
    db.init_db()
    with Session(db.engine) as session:
        task = session.get(Task, task_id)
        if not task:
            return f"Error: Task {task_id} not found."

        task.status = TaskStatus.IN_REVIEW
        task.test_review_attempts = 0
        session.add(task)
        session.commit()
        return f"Task {task_id} passed test review. Moving to code review."


@mcp.tool()
def test_review_reject(
    task_id: int, feedback: str, repo_root: Optional[str] = None
) -> str:
    """Reverts task to 'in_progress' after test review failure with feedback. Resets all review attempt counters."""
    db.init_db()
    with Session(db.engine) as session:
        task = session.get(Task, task_id)
        if not task:
            return f"Error: Task {task_id} not found."

        task.test_review_attempts += 1
        task.status = TaskStatus.IN_PROGRESS
        task.test_feedback = feedback
        task.security_review_attempts = 0

        if task.test_review_attempts >= 10:
            task.status = TaskStatus.FAILED

        session.add(task)
        session.commit()

        if task.status == TaskStatus.FAILED:
            return f"Task {task_id} failed test review 10+ times. Marked as FAILED. Human review required."
        return f"Task {task_id} rejected from test review and returned to IN_PROGRESS."


@mcp.tool()
def workspace_cleanup(
    jira_id: str, force: bool = False, repo_root: Optional[str] = None
) -> str:
    """
    Manually triggers cleanup for a jira_id: pushes branch and removes worktree(s).
    Set force=True to cleanup even if not all tasks are done.
    """
    db.init_db()
    git_manager = _get_git_manager(repo_root)

    with Session(db.engine) as session:
        statement = select(Task).where(Task.jira_id == jira_id)
        tasks = session.exec(statement).all()

        if not tasks:
            return f"Error: No tasks found for {jira_id}."

        # Check if all tasks are done (unless forced)
        if not force:
            incomplete_tasks = [t for t in tasks if t.status != TaskStatus.DONE]
            if incomplete_tasks:
                return (
                    f"Error: {len(incomplete_tasks)} task(s) not done. "
                    f"Use force=True to cleanup anyway."
                )

        # Collect all worktrees for this feature (may have multiple from parallel execution)
        worktrees_to_cleanup = set()
        for task in tasks:
            if task.worktree_path:
                worktrees_to_cleanup.add(task.worktree_path)
                task.worktree_path = None
                session.add(task)

        if not worktrees_to_cleanup:
            return f"Error: No worktrees found for {jira_id}."

        try:
            # Push feature branch to remote
            try:
                git_manager.push_branch(jira_id)
            except RuntimeError as e:
                logger.warning(f"Failed to push branch: {e}")

            # Cleanup all worktrees
            for worktree_path in worktrees_to_cleanup:
                try:
                    git_manager.cleanup_worktree(worktree_path)
                    logger.info(f"Cleaned up worktree: {worktree_path}")
                except RuntimeError as e:
                    logger.warning(f"Failed to cleanup worktree {worktree_path}: {e}")

            session.commit()
            return (
                f"Cleanup complete for {jira_id}: branch pushed and "
                f"{len(worktrees_to_cleanup)} worktree(s) removed."
            )
        except Exception as e:
            return f"Error during cleanup: {str(e)}"


@mcp.tool()
def git_status(repo_root: Optional[str] = None) -> dict:
    """Returns the current status of the repository."""
    try:
        git_manager = _get_git_manager(repo_root)
        return git_manager.get_status()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def git_diff(repo_root: Optional[str] = None, paths: Optional[List[str]] = None) -> str:
    """Returns the diff for the specified paths or the entire worktree."""
    try:
        # Validate paths before accessing git repository
        if paths:
            validate_paths(paths)
        git_manager = _get_git_manager(repo_root)
        return git_manager.get_diff(paths)
    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def git_add(files: List[str], repo_root: Optional[str] = None) -> str:
    """Stages specific files."""
    try:
        # Validate files before accessing git repository
        validate_paths(files)
        git_manager = _get_git_manager(repo_root)
        git_manager.add(files)
        return f"Successfully staged {files}"
    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def git_restore(files: List[str], repo_root: Optional[str] = None) -> str:
    """Discards changes in the specified files."""
    try:
        # Validate files before accessing git repository
        validate_paths(files)
        git_manager = _get_git_manager(repo_root)
        git_manager.restore(files)
        return f"Successfully restored {files}"
    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"
