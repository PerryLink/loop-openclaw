# Config Plan — Default Mode

## Project
- **name**: default
- **mode**: sequential

## Agents
| ID | Role | Model |
|----|------|-------|
| orchestrator | Orchestrator | claude-sonnet-4-20250514 |
| worker-1 | Developer | claude-sonnet-4-20250514 |
| worker-2 | Reviewer | claude-sonnet-4-20250514 |

## Permissions
- file_read: ./workspace
- file_write: ./workspace
- command_exec: git, npm, pip, python, node

## Settings
- max_cycles: 20
- convergence_rounds: 3
- max_duration_minutes: 120
