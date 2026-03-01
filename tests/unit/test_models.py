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
    """Tests for Task Pydantic model."""

    def test_create_task_with_required_fields(self):
        """Task can be created with only required fields."""
        task = Task(
            id=1,
            jira_id="PROJ-1",
            title="Implement feature",
            prompt_payload="Do something specific",
            status=TaskStatus.DRAFT,
            sort_order=1,
        )

        assert task.id == 1
        assert task.jira_id == "PROJ-1"
        assert task.title == "Implement feature"
        assert task.status == TaskStatus.DRAFT

    def test_create_task_with_all_fields(self):
        """Task can be created with all fields."""
        task = Task(
            id=2,
            jira_id="PROJ-2",
            title="Full task",
            prompt_payload="Detailed prompt",
            status=TaskStatus.READY,
            sort_order=2,
            worktree_path="/path/to/worktree",
            branch_name="feat/proj-2/1",
            test_feedback="Tests passed",
            test_review_attempts=1,
            security_review_attempts=0,
            security_feedback=None,
        )

        assert task.id == 2
        assert task.worktree_path == "/path/to/worktree"
        assert task.branch_name == "feat/proj-2/1"
        assert task.test_feedback == "Tests passed"

    def test_task_default_status_is_draft(self):
        """Task should default to DRAFT status if not specified."""
        task = Task(
            id=3,
            jira_id="PROJ-3",
            title="Default status test",
            prompt_payload="Test",
            sort_order=1,
        )

        assert task.status == TaskStatus.DRAFT

    def test_task_serialization(self):
        """Task should serialize to dict correctly."""
        task = Task(
            id=1,
            jira_id="TEST-1",
            title="Test Task",
            prompt_payload="Test payload",
            status=TaskStatus.READY,
        )
        
        data = task.model_dump()
        assert data["id"] == 1
        assert data["jira_id"] == "TEST-1"
        assert data["status"] == TaskStatus.READY

    def test_task_json_roundtrip(self):
        """Task should serialize and deserialize from JSON."""
        task = Task(
            id=1,
            jira_id="TEST-1",
            title="Test Task",
            prompt_payload="Test payload",
            status=TaskStatus.READY,
        )
        
        json_str = task.model_dump_json()
        restored = Task.model_validate_json(json_str)
        
        assert restored.id == task.id
        assert restored.jira_id == task.jira_id
        assert restored.title == task.title

