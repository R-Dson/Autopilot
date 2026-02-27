---
title: Rename "vscode" to "copilot"
status: draft
owner:
---

## Overview

Rename all code references to "vscode" to "copilot" throughout the project, including CLI arguments, configuration keys, function names, test names, and documentation. File system paths (e.g., `~/.config/Code/User/prompts/`) must remain unchanged.

## Scope

### Must Change

**autopilot/main.py:**
- Function: `format_tools_vscode` → `format_tools_copilot`
- EDITOR_CONFIGS dictionary key: `"vscode"` → `"copilot"`
- CLI argument help text: `(opencode, vscode, claude)` → `(opencode, copilot, claude)`
- default_tools dictionary key: `"vscode"` → `"copilot"`
- Conditional checks: `elif editor == "vscode":` → `elif editor == "copilot":`

**tests/integration/test_install_agents.py:**
- Test names containing "vscode" → "copilot"
- Assertion strings and comments referencing "vscode"

**README.md:**
- Documentation mentioning vscode → copilot

### Must NOT Change

- File system paths:
  - `~/.config/Code/User/prompts/`
  - `~/Library/Application Support/Code/User/prompts/`
  - `%APPDATA%\Code\User\prompts`
- Platform detection logic (Linux/Darwin/Windows)
- Any external Microsoft paths

## Requirements

1. **Backward Compatibility**: Remove "vscode" entirely. Only "copilot" will be a valid option.
2. **Consistency**: All references must be renamed consistently across code, tests, and docs.
3. **Functionality**: The `install_agents copilot` command must work exactly as `install_agents vscode` did.

## Design Approach

1. Rename the string literal `"vscode"` to `"copilot"` in all locations.
2. Rename function `format_tools_vscode` to `format_tools_copilot`.
3. Update test names to reflect the new naming.
4. Update documentation to reference "copilot" instead of "vscode".

## Acceptance Criteria

- [ ] `autopilot/main.py` contains no references to "vscode"
- [ ] `tests/integration/test_install_agents.py` contains no references to "vscode"
- [ ] `README.md` contains no references to "vscode"
- [ ] `autopilot install-agents copilot` works correctly
- [ ] File system paths remain unchanged (still point to Code/User/prompts)
