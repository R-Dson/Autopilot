"""Unit tests for database module."""

from sqlmodel import Session, select

from autopilot.models import Task
from autopilot import db as db_module


class TestInitDb:
    """Tests for init_db function."""

    def test_init_db_creates_autopilot_directory(self, tmp_path, monkeypatch):
        """init_db should create .autopilot directory."""
        monkeypatch.chdir(tmp_path)
        db_module.reset_engine()

        db_module.init_db()

        assert (tmp_path / ".autopilot").exists()
        assert (tmp_path / ".autopilot" / "tasks.db").exists()

    def test_init_db_creates_tables(self, tmp_path, monkeypatch):
        """init_db should create all tables."""
        monkeypatch.chdir(tmp_path)
        db_module.reset_engine()

        db_module.init_db()

        # Should be able to query (table exists)
        with Session(db_module.get_engine()) as session:
            # This will fail if tables don't exist
            result = session.exec(select(Task)).all()
            assert result == []


class TestGetSession:
    """Tests for get_session function."""

    def test_get_session_returns_session(self, tmp_path, monkeypatch):
        """get_session should return a Session context manager."""
        monkeypatch.chdir(tmp_path)
        db_module.init_db()

        with db_module.get_session() as session:
            assert isinstance(session, Session)
