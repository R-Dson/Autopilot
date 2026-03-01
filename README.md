# Autopilot

A local orchestration system for AI-assisted software development using the Model Context Protocol (MCP). Autopilot maintains a Kanban board in SQLite and coordinates AI agents through isolated Git worktrees.

## Setup (One-time)

1. **Install Autopilot**: `uv tool install -e .`
2. **Install Agents**: `autopilot install-agents opencode` (Options: opencode, vscode)
3. **Connect MCP**: Add `autopilot server` to your editor's MCP settings (details below).

## Project Workflow

Run `autopilot init` in your project, then:

### With Planner (Optional)

1. **Planner**: Interviews you to understand feature vision → creates `concepts/{feature}.md`
2. **Spec Writer**: Reads concept → creates technical spec in `specs/`
3. **Architect**: Breaks spec into atomic tasks
4. **Autopilot**: Coordinates implementation
   - Implementer → Test Reviewer → Code Reviewer → Security Reviewer
   - Agents handle handoffs automatically
   - You're notified when all tasks complete

### Without Planner (Optional)

1. **Spec Writer**: Discuss your feature needs directly
2. **Architect**: Break down into atomic tasks
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

---

## CLI Reference

```bash
autopilot init                  # Initialize project state (.autopilot.db)
autopilot install-agents {ed}   # Install agent templates (opencode, vscode)
autopilot list                 # View Kanban board
autopilot list --status ready  # View tasks ready for implementation
autopilot update 1 --status in_progress  # Manually update task status
autopilot server               # Start MCP server
```

---

## Directory Structure

```
project/
├── autopilot/           # Core orchestrator and agent templates
├── concepts/           # Feature concepts (optional output from Planner)
├── specs/              # Technical specifications (from Spec Writer)
├── .worktrees/         # Isolated worktrees for each feature (gitignored)
│   └── project-FEAT-01/
├── .autopilot.db       # SQLite database (auto-created)
└── .gitignore          # Includes .worktrees
```

---

## Key Features

### Feature-Centric Workflow
- All tasks for a feature work on a single branch (`feat/{jira_id}`)
- No per-task branches - reduces Git clutter
- Worktrees persist for the feature lifetime

### Feature Context for Agents
- Implementers and reviewers receive ALL tasks for the feature
- Agents understand the bigger picture, not just their specific task
- Reduces back-and-forth during reviews

### Organized Worktrees
- Worktrees created in `.worktrees/` folder (inside repo)
- Crystal-clear paths: `project/.worktrees/project-FEAT-01/`
- Reviewers instantly know which repo and feature they're reviewing
- `.worktrees` is gitignored - never committed

### Planner Agent (Optional)
- Interviews you to clarify feature vision
- Creates structured Feature Concept document
- Focuses on product intent (not technical details)
- Output: `concepts/{feature}.md`

### Handoff System
- Each agent guides you to the next step
- Clear "Next step: Switch to X agent" instructions
- VSCode Copilot supports quick agent switching via handoffs
