from enum import Enum
from typing import Optional
from sqlmodel import SQLModel, Field


class TaskStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"
    FAILED = "failed"


class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    jira_id: str
    title: str
    prompt_payload: str
    status: TaskStatus = Field(default=TaskStatus.DRAFT)
    worktree_path: Optional[str] = None
    branch_name: Optional[str] = None
    feature_branch: Optional[str] = None
    test_feedback: Optional[str] = None
    test_review_attempts: int = Field(default=0)
    security_review_attempts: int = Field(default=0)
    security_feedback: Optional[str] = None
    sort_order: int = Field(default=0)
