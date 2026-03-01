"""Integration tests for install-agents command (SPOT system)."""

import pytest
import tempfile
from pathlib import Path

from autopilot.main import (
    AGENT_REGISTRY,
    EDITOR_CONFIGS,
    install_agents,
    compose_agent_file,
)


class TestAgentRegistry:
    """Tests for AGENT_REGISTRY."""

    def test_registry_has_all_agents(self):
        """Registry should have all agents."""
        expected = {
            "spec-writer",
            "architect",
            "autopilot",
            "implementer",
            "code-reviewer",
            "test-reviewer",
            "security-reviewer",
        }
        assert set(AGENT_REGISTRY.keys()) == expected

    def test_registry_has_required_fields(self):
        """Each agent should have name, description, mode."""
        for agent_id, config in AGENT_REGISTRY.items():
            assert "name" in config
            assert "description" in config
            assert "mode" in config

    def test_spec_writer_and_autopilot_are_primary(self):
        """Spec Writer and Autopilot should be primary mode."""
        assert AGENT_REGISTRY["spec-writer"]["mode"] == "primary"
        assert AGENT_REGISTRY["autopilot"]["mode"] == "primary"

    def test_worker_agents_are_subagent(self):
        """Worker agents should be subagent mode."""
        assert AGENT_REGISTRY["architect"]["mode"] == "subagent"
        assert AGENT_REGISTRY["implementer"]["mode"] == "subagent"
        assert AGENT_REGISTRY["code-reviewer"]["mode"] == "subagent"


class TestEditorConfigs:
    """Tests for EDITOR_CONFIGS."""

    def test_has_all_editors(self):
        """Should support opencode, vscode, claude."""
        assert "opencode" in EDITOR_CONFIGS
        assert "vscode" in EDITOR_CONFIGS
        assert "claude" in EDITOR_CONFIGS

    def test_opencode_has_permission_format(self):
        """OpenCode permission format should produce permission records."""
        tools = {"mcp": True, "task": True}
        formatter = EDITOR_CONFIGS["opencode"].permission_format
        assert formatter is not None
        result = formatter(tools)

        assert "permission:" in result
        assert "mcp:" in result
        assert "task:" in result

    def test_vscode_handoffs_exist(self):
        """VSCode editor should have handoffs defined."""
        handoffs = EDITOR_CONFIGS["vscode"].handoffs
        assert handoffs is not None
        assert "autopilot" in handoffs
        assert "Implementer" in handoffs["autopilot"]

    def test_claude_no_handoffs(self):
        """Claude editor should not have handoffs defined."""
        handoffs = EDITOR_CONFIGS["claude"].handoffs
        assert handoffs is None or handoffs == {}


class TestComposeAgentFile:
    """Tests for compose_agent function."""

    def test_compose_opencode_has_frontmatter(self):
        """OpenCode should have YAML frontmatter."""
        result = compose_agent_file(
            agent_id="spec-writer",
            editor="opencode",
            core_body="# Agent content",
            tools={"write": True},
            mode="primary",
        )

        assert result.startswith("---")
        assert "description:" in result
        assert "mode: primary" in result
        assert "permission:" in result  # OpenCode uses "permission:" not "tools:"
        assert "# Agent content" in result

    def test_compose_vscode_has_handoffs(self):
        """VSCode Autopilot should have handoffs."""
        result = compose_agent_file(
            agent_id="autopilot",
            editor="vscode",
            core_body="# Agent content",
            tools={"mcp": True},
            mode="subagent",
        )

        assert "handoffs:" in result
        assert "Implementer" in result

    def test_compose_claude_tools_format(self):
        """Claude should use tools list format."""
        result = compose_agent_file(
            agent_id="implementer",
            editor="claude",
            core_body="# Agent content",
            tools={"bash": True},
            mode="subagent",
        )

        assert "bash" in result  # Tool names are lowercase in tools list


class TestInstallAgents:
    """Tests for install_agents function."""

    def test_install_agents_creates_files(self, tmp_path):
        """install_agents should create agent files."""
        # Use a temp directory for output
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock get_editor_target_dir to use temp_dir
            import autopilot.main as main_module

            original_func = main_module.get_editor_target_dir
            main_module.get_editor_target_dir = lambda editor: temp_dir  # type: ignore[assignment]

            try:
                install_agents("opencode")

                # Check files were created
                for agent_id in AGENT_REGISTRY.keys():
                    file_path = Path(temp_dir) / f"{agent_id}.md"
                    assert file_path.exists(), f"{agent_id}.md not created"
            finally:
                main_module.get_editor_target_dir = original_func

    def test_installed_files_have_content(self, tmp_path):
        """Installed files should have proper content."""
        with tempfile.TemporaryDirectory() as temp_dir:
            import autopilot.main as main_module

            original_func = main_module.get_editor_target_dir
            main_module.get_editor_target_dir = lambda editor: temp_dir  # type: ignore[assignment]

            try:
                install_agents("opencode")

                # Check architect has mode from registry
                architect_file = Path(temp_dir) / "architect.md"
                content = architect_file.read_text()

                assert "mode: subagent" in content
            finally:
                main_module.get_editor_target_dir = original_func


class TestCoreTemplatesExist:
    """Tests for core template files."""

    def test_core_templates_exist(self):
        """All core templates should exist."""
        from importlib import resources

        for agent_id in AGENT_REGISTRY.keys():
            # Try to find the core template
            try:
                file = (
                    resources.files("autopilot")
                    / "agents_templates"
                    / "core"
                    / f"{agent_id}.md"
                )
                assert file.is_file(), f"Core template for {agent_id} not found"
            except Exception as e:
                pytest.fail(f"Could not find core template for {agent_id}: {e}")
