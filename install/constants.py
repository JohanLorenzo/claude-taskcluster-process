from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_DIR = Path.home() / ".claude"
RULES_DIR = CLAUDE_DIR / "rules"
SETTINGS_FILE = CLAUDE_DIR / "settings.json"
HOOKS_CONFIG_FILE = REPO_ROOT / "hooks-config.json"
LOCAL_CONFIG_FILE = REPO_ROOT / "CLAUDE.local.md"
