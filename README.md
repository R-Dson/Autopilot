# Autopilot

A local orchestration system for AI-assisted software development using the Model Context Protocol (MCP). Autopilot maintains a Kanban board in SQLite and coordinates AI agents through isolated Git worktrees.

## Setup (One-time)

1. **Install Autopilot**: `uv tool install -e .`
2. **Install Agents**: `autopilot install-agents opencode` (Options: opencode, vscode, claude)
3. **Connect MCP**: Add `autopilot server` to your editor's MCP settings (details below).

## Project Workflow

Run `autopilot init` in your project, then:

1. **Spec Writer**: Discuss your feature needs
2. **Architect**: Break down into atomic tasks. User approved
3. **Autopilot**: Spawns workers for each task
   - Implementer -> Test Reviewer -> Code Reviewer -> Security Reviewer
   - Agents handle handoffs automatically
   - You're notified when all tasks complete

You approve phases; agents handle the rest.

### The Quality Funnel

Every task must pass through four mandatory stages:
- **Implementer**: Writes code and tests in isolated worktrees
- **Test Reviewer**: Validates tests pass (coverage: 50-80% based on risk)
- **Code Reviewer**: Checks logic, maintainability, DRY/KISS principles
- **Security Reviewer**: Reviews for OWASP vulnerabilities and Zero Trust

Any rejection resets task for full re-review. Tasks fail after 10 test rejections or 5 security rejections.

---

## MCP Connection

### OpenCode (`opencode.jsonc`)
```json
    "mcp": {
        "autopilot": {
            "type": "local",
            "command": ["autopilot", "server"],
            "enabled": true
        }
    }
```

### VS Code Copilot (`~/.config/Code/User/mcp.json`)
```json
{
    "servers": {
        "autopilot-server": {
            "type": "stdio",
            "command": "autopilot",
            "args": ["server"]
        }
    },
    "inputs": []
}
```

### Claude Code
```bash
claude mcp add autopilot -- autopilot server
```

---

## CLI Reference

```bash
autopilot init                  # Initialize project state (.autopilot/tasks.db)
autopilot install-agents {ed}   # Install agent templates (opencode, vscode, claude)
autopilot list                 # View Kanban board
autopilot list --status ready  # View tasks ready for implementation
autopilot update 1 --status in_progress  # Manually update task status
autopilot server               # Start MCP server
```

## Structure

- `autopilot/`: Core orchestrator and agent templates.
- `.autopilot/`: Project state (SQLite database).
