# CLAUDE.md

Read [AGENTS.md](AGENTS.md) first. It holds the shared rules for every development agent (Claude Code and GPT/Codex), including the handoff procedure through GitHub Issues.

Minimal code and minimal design are virtues here (AGENTS.md §0).

Claude-specific notes:
- The operator's private meeting table is a separate local project: never copy its data or ledgers into this repository.
- Python 3.15 is installed. Run tools with `python -B` so that no `__pycache__` is written.
