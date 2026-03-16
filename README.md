# claude-taskcluster-process

Version-controlled Claude Code configuration for Taskcluster work: rules, safety hooks, and install tooling.

## Setup

```bash
git clone https://github.com/JohanLorenzo/claude-taskcluster-process ~/git/hub/JohanLorenzo/claude-taskcluster-process
cd ~/git/hub/JohanLorenzo/claude-taskcluster-process
python install.py
```

`install.py` will:
1. Check required CLI tools are installed (`git`, `gh`, `uv`, `taskcluster`).
2. Generate `CLAUDE.local.md` from `CLAUDE.local.md.template` if it doesn't exist yet (interactive).
3. Show a unified diff of every change it will make to `~/.claude/`.
4. Prompt before applying anything.

## Populating the repo list from fxci-config

The `install.py` setup wizard discovers tracked repositories automatically. It:
1. Searches your repo root for a taskgraph checkout (looks for `pyproject.toml` with `name = "taskgraph"` or `taskgraph/__init__.py`).
2. Searches for an fxci-config checkout (looks for an `environments/firefoxci/` subdirectory).
3. If fxci-config is found, parses project configs under `config/projects/` to extract repo slugs.
4. Searches your repo root for matching local clones (by directory name or `.git/config` remote URL).
5. Writes discovered paths into `CLAUDE.local.md`.

## Development

```bash
uv run pre-commit install
uv run pytest
```
