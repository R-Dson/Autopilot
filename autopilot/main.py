import typer
import os
import platform
from typing import Callable, Optional, List, cast
from importlib import resources
from .server import mcp
from . import db
from .models import Task, TaskStatus
from sqlmodel import Session, select

app = typer.Typer(help="Autopilot - Architect-First AI Orchestrator")

AGENT_REGISTRY = {
    "spec-writer": {
        "name": "Spec Writer",
        "description": "Creates and refines feature specifications",
        "mode": "primary",
        "user_invokable": True,
        "allowed_subagents": ["architect"],
    },
    "architect": {
        "name": "Architect",
        "description": "Translates specs into atomic tasks for Autopilot",
        "mode": "subagent",
        "user_invokable": False,
        "allowed_subagents": [],
    },
    "autopilot": {
        "name": "Autopilot",
        "description": "Runs the automation loop - coordinates Implementer and Code Reviewer agents",
        "mode": "primary",
        "user_invokable": True,
        "allowed_subagents": [
            "implementer",
            "test-reviewer",
            "code-reviewer",
            "security-reviewer",
        ],
    },
    "implementer": {
        "name": "Implementer",
        "description": "Implements atomic tasks from the Autopilot Kanban board",
        "mode": "subagent",
        "user_invokable": False,
        "allowed_subagents": [],
    },
    "code-reviewer": {
        "name": "Code Reviewer",
        "description": "Reviews and approves code changes",
        "mode": "subagent",
        "user_invokable": False,
        "allowed_subagents": [],
    },
    "test-reviewer": {
        "name": "Test Reviewer",
        "description": "Reviews test coverage and quality - verifies tests pass and cover real code",
        "mode": "subagent",
        "user_invokable": False,
        "allowed_subagents": [],
    },
    "security-reviewer": {
        "name": "Security Reviewer",
        "description": "Reviews code for security vulnerabilities with focus on OWASP Top 10, Zero Trust, and AI/ML security",
        "mode": "subagent",
        "user_invokable": False,
        "allowed_subagents": [],
    },
}


def format_permission_opencode(tools: dict) -> str:
    # Format as permission object (key: value pairs)
    lines = []
    for tool, perm in tools.items():
        lines.append(f"  {tool}: {perm}")
    return "permission:\n" + "\n".join(lines)


def format_tools_vscode(tools: dict) -> str:
    return "[" + ", ".join(tools.keys()) + "]"


def format_tools_claude(tools: dict) -> str:
    return ", ".join(tool.capitalize() for tool in tools.keys())


# Type alias for the tools formatter function
ToolsFormatter = Callable[[dict], str]


class EditorConfig:
    def __init__(
        self,
        target_dir: str | None,
        file_ext: str,
        frontmatter: str,
        permission_format: ToolsFormatter | None = None,
        handoffs: dict | None = None,
    ):
        self.target_dir = target_dir
        self.file_ext = file_ext
        self.frontmatter = frontmatter
        self.permission_format = permission_format
        self.handoffs = handoffs or {}


EDITOR_CONFIGS: dict[str, EditorConfig] = {
    "opencode": EditorConfig(
        target_dir="~/.config/opencode/agents/",
        file_ext=".md",
        frontmatter="""---
description: {description}
mode: {mode}
{permission}
---
{body}""",
        permission_format=format_permission_opencode,
    ),
    "vscode": EditorConfig(
        target_dir=None,  # Determined by OS
        file_ext=".agent.md",
        frontmatter="""---
description: {description}
name: {name}
user-invokable: {user_invokable}
{agents_list}{tools}
{handoffs}
---
{body}""",
        handoffs={
            "autopilot": """handoffs:
  - label: Implementer: Implement Task
    agent: implementer
    prompt: Please implement task {task_id}.
    send: true""",
            "implementer": "",
            "code-reviewer": "",
            "test-reviewer": "",
            "security-reviewer": "",
            "architect": "",
            "spec-writer": """handoffs:
  - label: Implement Specification
    agent: autopilot
    prompt: Please implement the feature described in this specification.
    send: true""",
        },
    ),
    "claude": EditorConfig(
        target_dir="~/.claude/agents/",
        file_ext=".md",
        frontmatter="""---
description: {description}
name: {name}
tools: {tools_list}
mcpServers: autopilot
---
{body}""",
    ),
}


def get_editor_target_dir(editor: str) -> str:
    """Get the target directory for the editor based on OS."""
    if editor == "opencode":
        return os.path.expanduser("~/.config/opencode/agents/")
    elif editor == "claude":
        return os.path.expanduser("~/.claude/agents/")
    elif editor == "vscode":
        system = platform.system()
        if system == "Linux":
            return os.path.expanduser("~/.config/Code/User/prompts/")
        elif system == "Darwin":
            return os.path.expanduser(
                "~/Library/Application Support/Code/User/prompts/"
            )
        elif system == "Windows":
            return os.path.join(os.environ["APPDATA"], "Code", "User", "prompts")
    raise ValueError(f"Unsupported editor: {editor}")


def compose_agent_file(
    agent_id: str,
    editor: str,
    core_body: str,
    tools: dict,
    mode: str = "all",
) -> str:
    """Compose a complete agent file for the specified editor."""
    config = EDITOR_CONFIGS[editor]
    agent_meta = AGENT_REGISTRY[agent_id]

    name = agent_meta["name"]
    description = agent_meta["description"]

    # Format permission/tools based on editor
    if editor == "opencode" and config.permission_format:
        perm_str = config.permission_format(tools)
    elif editor in ("vscode", "claude"):
        perm_str = "[" + ", ".join(tools.keys()) + "]"
    else:
        perm_str = config.permission_format(tools) if config.permission_format else ""

    if editor == "vscode":
        handoffs = config.handoffs.get(agent_id, "")
        user_invokable = agent_meta.get("user_invokable", True)

        allowed_subagents = cast(List[str], agent_meta.get("allowed_subagents", []))

        # Format agents list (only include if non-empty)
        if allowed_subagents:
            agents_list = f"agents: {allowed_subagents}\n"
        else:
            agents_list = ""

        # Format tools line
        tools_line = f"tools: {list(tools.keys())}" if tools else ""

        # Format handoffs (remove leading newline if empty)
        handoffs_str = f"{handoffs}\n" if handoffs else ""

        return config.frontmatter.format(
            description=description,
            name=name,
            user_invokable=str(user_invokable).lower(),
            agents_list=agents_list,
            tools=tools_line,
            handoffs=handoffs_str,
            body=core_body,
        ).replace("\n\n---", "\n---")
    elif editor == "claude":
        user_invokable = agent_meta.get("user_invokable", True)
        allowed_subagents = cast(List[str], agent_meta.get("allowed_subagents", []))

        # Build tools list from provided tools
        # Keep tool names as they are provided (often lowercase from MCP)
        tool_names = list(tools.keys())

        if allowed_subagents:
            # Coordinator (main agent): restrict Task to specific subagents
            agents_list_str = ", ".join(f'"{agent}"' for agent in allowed_subagents)
            tools_str = f"Task({agents_list_str}), " + ", ".join(tool_names)
        elif user_invokable:
            # Regular main agent (can be invoked): include unrestricted Task
            tools_str = "Task, " + ", ".join(tool_names)
        else:
            # Subagent-only (cannot spawn): exclude Task entirely
            tools_str = ", ".join(tool_names)

        return config.frontmatter.format(
            description=description,
            name=name,
            tools_list=tools_str,
            body=core_body,
        )
    else:
        return config.frontmatter.format(
            description=description,
            mode=mode,
            permission=perm_str,
            body=core_body,
        )


@app.command()
def server():
    """Run the MCP server. Waits for editor connection via stdio."""
    mcp.run()


@app.command()
def init():
    """Initialize the Autopilot project state (SQLite storage)."""
    db.init_db()
    print("Autopilot project state initialized (SQLite database).")


@app.command()
def install_agents(
    editor: str = typer.Argument(
        ..., help="Editor to install agents for (opencode, vscode, claude)"
    ),
):
    """Install agent templates for the specified editor (user-wide)."""
    editor = editor.lower()

    if editor not in EDITOR_CONFIGS:
        print(
            f"Error: Unknown editor '{editor}'. Supported: {', '.join(EDITOR_CONFIGS.keys())}"
        )
        raise typer.Exit(code=1)

    target_dir = get_editor_target_dir(editor)
    os.makedirs(target_dir, exist_ok=True)

    print(f"Installing {editor} agents to {target_dir}...")

    # Agent-specific permissions (OpenCode format)
    # These override the default tools to enforce workflow
    agent_permissions = {
        "opencode": {
            "spec-writer": {
                "read": "allow",
                "edit": "allow",
                "write": "allow",
                "bash": "deny",
                "task": "allow",
                "question": "allow",
                "mcp": "allow",
            },
            "architect": {
                "read": "allow",
                "edit": "deny",
                "write": "deny",
                "bash": "deny",
                "task": "allow",
                "question": "allow",
                "mcp": "allow",
            },
            "autopilot": {
                "read": "allow",
                "edit": "deny",
                "write": "deny",
                "bash": "deny",
                "task": "allow",
                "question": "allow",
                "mcp": "allow",
            },
            "implementer": {
                "read": "allow",
                "edit": "allow",
                "write": "allow",
                "bash": "allow",
                "task": "deny",
                "question": "allow",
                "mcp": "allow",
            },
            "code-reviewer": {
                "read": "allow",
                "edit": "deny",
                "write": "deny",
                "bash": "allow",
                "task": "deny",
                "question": "allow",
                "mcp": "allow",
            },
            "test-reviewer": {
                "read": "allow",
                "edit": "deny",
                "write": "deny",
                "bash": "allow",
                "task": "deny",
                "question": "allow",
                "mcp": "allow",
            },
            "security-reviewer": {
                "read": "allow",
                "edit": "deny",
                "write": "deny",
                "bash": "allow",
                "task": "deny",
                "question": "allow",
                "mcp": "allow",
            },
        },
        "vscode": {
            "spec-writer": {
                "vscode": "true",
                "execute": "true",
                "read": "true",
                "agent": "true",
                "edit": "true",
                "search": "true",
                "web": "true",
                "todo": "true",
                "autopilot-server/*": "true",
            },
            "architect": {
                "read": "true",
                "search": "true",
                "autopilot-server/*": "true",
                "task": "true",
                "question": "true",
            },
            "autopilot": {
                "vscode": "true",
                "agent": "true",
                "web": "true",
                "autopilot-server/*": "true",
                "todo": "true",
            },
            "implementer": {
                "vscode": "true",
                "execute": "true",
                "read": "true",
                "agent": "true",
                "edit": "true",
                "search": "true",
                "web": "true",
                "todo": "true",
                "bash": "true",
                "autopilot-server/*": "true",
            },
            "code-reviewer": {
                "read": "true",
                "search": "true",
                "execute": "true",
                "bash": "true",
                "autopilot-server/*": "true",
                "question": "true",
            },
            "test-reviewer": {
                "read": "true",
                "search": "true",
                "execute": "true",
                "bash": "true",
                "autopilot-server/*": "true",
                "question": "true",
            },
            "security-reviewer": {
                "read": "true",
                "search": "true",
                "execute": "true",
                "bash": "true",
                "autopilot-server/*": "true",
                "question": "true",
            },
        },
        "claude": {
            "spec-writer": {
                "Read": "true",
                "Grep": "true",
                "Glob": "true",
                "Task": "true",
                "Question": "true",
            },
            "architect": {
                "Read": "true",
                "Grep": "true",
                "Glob": "true",
                "Task": "true",
                "Question": "true",
            },
            "autopilot": {
                "Read": "true",
                "Grep": "true",
                "Glob": "true",
                "Task": "true",
                "Question": "true",
            },
            "implementer": {
                "Read": "true",
                "Grep": "true",
                "Glob": "true",
                "Bash": "true",
                "Question": "true",
            },
            "code-reviewer": {
                "Read": "true",
                "Grep": "true",
                "Glob": "true",
                "Bash": "true",
                "Question": "true",
            },
            "test-reviewer": {
                "Read": "true",
                "Grep": "true",
                "Glob": "true",
                "Bash": "true",
                "Question": "true",
            },
            "security-reviewer": {
                "Read": "true",
                "Grep": "true",
                "Glob": "true",
                "Bash": "true",
                "Question": "true",
            },
        },
    }

    core_dir = resources.files("autopilot") / "agents_templates" / "core"

    for agent_id in AGENT_REGISTRY.keys():
        core_file = core_dir / f"{agent_id.replace(' ', '-').lower()}.md"
        if not core_file.is_file():
            print(f"  ! Warning: Core template for '{agent_id}' not found, skipping.")
            continue

        core_body = core_file.read_text(encoding="utf-8")
        # Use agent-specific permissions for opencode, default tools for others
        tools = agent_permissions.get(editor, {}).get(agent_id, {})
        mode = str(AGENT_REGISTRY[agent_id].get("mode", "subagent"))

        output = compose_agent_file(agent_id, editor, core_body, tools, mode)

        output_file = os.path.join(
            target_dir,
            f"{agent_id.replace(' ', '-').lower()}{EDITOR_CONFIGS[editor].file_ext}",
        )
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(output)

        print(f"  + {os.path.basename(output_file)}")

    print(f"\nSuccessfully installed {editor} agents user-wide.")


@app.command()
def create(
    jira_id: str = typer.Argument(..., help="JIRA ID for the tasks"),
    title: str = typer.Argument(..., help="Title of the task"),
    prompt: str = typer.Argument(..., help="Prompt payload for the task"),
):
    """Create a single task in the Kanban board."""
    db.init_db()
    with Session(db.engine) as session:
        task = Task(
            jira_id=jira_id,
            title=title,
            prompt_payload=prompt,
            status=TaskStatus.READY,
        )
        session.add(task)
        session.commit()
        session.refresh(task)
        print(f"Created task {task.id} for {jira_id}.")


@app.command("list")
def list_tasks(
    jira_id: Optional[str] = typer.Option(None, help="Filter by JIRA ID"),
    status_filter: Optional[str] = typer.Option(None, help="Filter by status"),
):
    """List tasks in the Kanban board."""
    db.init_db()
    with Session(db.engine) as session:
        statement = select(Task)
        if jira_id:
            statement = statement.where(Task.jira_id == jira_id)
        if status_filter:
            statement = statement.where(Task.status == TaskStatus(status_filter))

        results = session.exec(statement).all()

        if not results:
            print("No tasks found.")
            return

        print(f"\n{'ID':<5} {'JIRA':<12} {'Status':<12} {'Title'}")
        print("-" * 80)
        for task in results:
            print(
                f"{task.id:<5} {task.jira_id:<12} {task.status.value:<12} {task.title}"
            )
        print()


@app.command()
def update(
    task_id: int = typer.Argument(..., help="ID of the task to update"),
    status: TaskStatus = typer.Option(..., help="New status for the task"),
):
    """Update a task's status (e.g., to 'ready' for implementation)."""
    db.init_db()
    with Session(db.engine) as session:
        task = session.get(Task, task_id)

        if not task:
            print(f"Error: Task {task_id} not found.")
            raise typer.Exit(code=1)

        task.status = status
        session.add(task)
        session.commit()
        print(f"Task {task_id} updated to {status.value}.")


if __name__ == "__main__":
    app()
