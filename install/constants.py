from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_REPOS = {
    "taskcluster": "https://github.com/taskcluster/taskcluster",
    "taskgraph": "https://github.com/taskcluster/taskgraph",
    "mozilla-taskgraph": "https://github.com/mozilla-releng/mozilla-taskgraph",
    "fxci-config": "https://github.com/mozilla-releng/fxci-config",
}
CLAUDE_DIR = Path.home() / ".claude"
RULES_DIR = CLAUDE_DIR / "rules"
SKILLS_DIR = CLAUDE_DIR / "skills"
SETTINGS_FILE = CLAUDE_DIR / "settings.json"
HOOKS_CONFIG_FILE = REPO_ROOT / "hooks-config.json"
PERMISSIONS_CONFIG_FILE = REPO_ROOT / "permissions-config.json"
LOCAL_CONFIG_FILE = REPO_ROOT / "CLAUDE.local.md"
SANDBOX_CONFIG_FILE = REPO_ROOT / "sandbox-config.json"
