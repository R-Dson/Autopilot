import os
from autopilot import db
from sqlmodel import Session, select
from autopilot.models import Task


def test_init_db_correctly_determines_path(tmp_path, monkeypatch):
    """Verify that init_db() correctly determines path and initializes schema."""
    # Setup temp project root
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Configure env var for project root
    monkeypatch.setattr(
        os, "environ", {**os.environ, "AUTOPILOT_ROOT": str(project_root)}
    )

    # Reset engine to pick up new root
    db.reset_engine()

    expected_db_path = project_root / ".autopilot.db"
    assert db.DB_PATH == expected_db_path
    assert not expected_db_path.exists()

    # Run init_db - this uses the REAL engine (pointing to temp path)
    db.init_db()

    # Verify file exists
    assert expected_db_path.exists()

    # Verify schema is initialized by trying to use it with the module's engine
    with Session(db.engine) as session:
        task = Task(jira_id="TEST", title="Test", prompt_payload="Test")
        session.add(task)
        session.commit()

        # Verify we can read it back
        saved_task = session.exec(select(Task)).first()
        assert saved_task is not None
        assert saved_task.jira_id == "TEST"


def test_init_db_is_idempotent(tmp_path, monkeypatch):
    """Verify that init_db() can be called multiple times without error."""
    project_root = tmp_path / "project_idempotent"
    project_root.mkdir()
    monkeypatch.setattr(
        os, "environ", {**os.environ, "AUTOPILOT_ROOT": str(project_root)}
    )
    db.reset_engine()

    db.init_db()
    db.init_db()  # Should not raise

    assert (project_root / ".autopilot.db").exists()
