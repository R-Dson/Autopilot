import json
import logging
from typing import List, Optional
from mcp.server.fastmcp import FastMCP
from sqlmodel import Session, select, text
from .models import Task, TaskStatus
from . import db
from .git_manager import GitManager
from .test_runner import TestRunner
from .security import validate_jira_id

logger = logging.getLogger(__name__)
mcp = FastMCP("Autopilot")


def _get_git_manager(repo_root: Optional[str] = None) -> GitManager:
    """Get a GitManager instance for the given repository root."""
    return GitManager(repo_root or ".")


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
    prepares a unique Git Worktree, and returns the task details.
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

        # Mark as IN_PROGRESS immediately to "lock" it for this process
        task.status = TaskStatus.IN_PROGRESS
        session.add(task)
        session.commit()
        # Save attributes for use outside the session context
        jira_id = task.jira_id
        task_id_db = task.id
        assert task_id_db is not None
        session.commit()

    # Prepare Git Worktree (slow operation outside the exclusive DB lock)
    try:
        worktree_path = git_manager.create_worktree(jira_id, task_id_db)

        # Update the task with worktree information
        with Session(db.engine) as session:
            task = session.get(Task, task_id)
            assert task is not None
            task.worktree_path = worktree_path
            # Use T{task_id} suffix to avoid ref name collisions with JIRA ID branches
            task.branch_name = f"feat/{task.jira_id}-T{task_id}"
            session.add(task)
            session.commit()
            session.refresh(task)
            return json.dumps(task.model_dump(), indent=2)
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
    Merges a completed task branch into the main feature branch.
    Call this after review approval.
    """
    db.init_db()
    git_manager = _get_git_manager(repo_root)

    with Session(db.engine) as session:
        task = session.get(Task, task_id)
        if not task:
            return f"Error: Task {task_id} not found."

        if task.status != TaskStatus.DONE:
            return f"Error: Task {task_id} must be DONE before integration."

        if not task.worktree_path or not task.branch_name:
            return "Error: Task missing worktree/branch info."

        target_branch = f"feat/{task.jira_id}"

        try:
            git_manager.merge_task(task.worktree_path, task.branch_name, target_branch)
            git_manager.push_branch(task.jira_id)
            git_manager.cleanup_worktree(task.worktree_path)

            task.worktree_path = None
            session.add(task)
            session.commit()

            return f"Task {task_id} successfully integrated into {target_branch}."
        except RuntimeError as e:
            return f"Merge Conflict: {str(e)}. Please resolve in {task.worktree_path}."


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
    Manually triggers cleanup for a jira_id: pushes branch and removes worktree.
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
                return f"Error: {len(incomplete_tasks)} task(s) not done. Use force=True to cleanup anyway."

        # Find worktree path from any task
        worktree_path = None
        for task in tasks:
            if task.worktree_path:
                worktree_path = task.worktree_path
                task.worktree_path = None
                session.add(task)

        if not worktree_path:
            return f"Error: No worktree found for {jira_id}."

        try:
            git_manager.push_branch(jira_id)
            git_manager.cleanup_worktree(worktree_path)
            session.commit()
            return (
                f"Cleanup complete for {jira_id}: branch pushed and worktree removed."
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
        git_manager = _get_git_manager(repo_root)
        return git_manager.get_diff(paths)
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def git_add(files: List[str], repo_root: Optional[str] = None) -> str:
    """Stages specific files."""
    try:
        git_manager = _get_git_manager(repo_root)
        git_manager.add(files)
        return f"Successfully staged {files}"
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def git_restore(files: List[str], repo_root: Optional[str] = None) -> str:
    """Discards changes in the specified files."""
    try:
        git_manager = _get_git_manager(repo_root)
        git_manager.restore(files)
        return f"Successfully restored {files}"
    except Exception as e:
        return f"Error: {str(e)}"
