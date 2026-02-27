from sqlmodel import select

from autopilot.models import Task, TaskStatus


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_task_status_has_all_expected_values(self):
        """TaskStatus should have all required states."""
        expected = {"draft", "ready", "in_progress", "in_review", "done", "failed"}
        actual = {status.value for status in TaskStatus}
        assert actual == expected

    def test_task_status_can_compare_strings(self):
        """TaskStatus should be comparable with string values."""
        assert TaskStatus.DRAFT == "draft"
        assert TaskStatus.READY == "ready"
        assert TaskStatus.IN_PROGRESS == "in_progress"
        assert TaskStatus.IN_REVIEW == "in_review"
        assert TaskStatus.DONE == "done"


class TestTaskModel:
    """Tests for Task SQLModel."""

    def test_create_task_with_required_fields(self, session):
        """Task can be created with only required fields."""
        task = Task(
            jira_id="PROJ-1",
            title="Implement feature",
            prompt_payload="Do something specific",
            status=TaskStatus.DRAFT,
            sort_order=1,
        )
        session.add(task)
        session.commit()

        assert task.id is not None
        assert task.jira_id == "PROJ-1"
        assert task.title == "Implement feature"
        assert task.status == TaskStatus.DRAFT

    def test_create_task_with_all_fields(self, session):
        """Task can be created with all fields."""
        task = Task(
            jira_id="PROJ-2",
            title="Full task",
            prompt_payload="Detailed prompt",
            status=TaskStatus.READY,
            sort_order=2,
            worktree_path="/path/to/worktree",
            branch_name="feat/proj-2/1",
            test_feedback="Tests passed",
        )
        session.add(task)
        session.commit()
        session.refresh(task)

        assert task.id is not None
        assert task.worktree_path == "/path/to/worktree"
        assert task.branch_name == "feat/proj-2/1"
        assert task.test_feedback == "Tests passed"

    def test_task_default_status_is_draft(self, session):
        """Task should default to DRAFT status if not specified."""
        task = Task(
            jira_id="PROJ-3",
            title="Default status test",
            prompt_payload="Test",
            sort_order=1,
        )
        session.add(task)
        session.commit()
        session.refresh(task)

        assert task.status == TaskStatus.DRAFT

    def test_task_query_by_jira_id(self, session, sample_task):
        """Can query tasks by jira_id."""
        result = session.exec(select(Task).where(Task.jira_id == "TEST-1")).one()
        assert result.id == sample_task.id

    def test_task_query_by_status(self, session, sample_task):
        """Can query tasks by status."""
        result = session.exec(select(Task).where(Task.status == TaskStatus.DRAFT)).one()
        assert result.id == sample_task.id

    def test_task_update_status(self, session, sample_task):
        """Can update task status."""
        sample_task.status = TaskStatus.READY
        session.commit()
        session.refresh(sample_task)

        assert sample_task.status == TaskStatus.READY

    def test_task_delete(self, session, sample_task):
        """Can delete a task."""
        task_id = sample_task.id
        session.delete(sample_task)
        session.commit()

        result = session.get(Task, task_id)
        assert result is None
