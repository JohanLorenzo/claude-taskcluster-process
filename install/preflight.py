import os

from .constants import CLAUDE_DIR, REPO_ROOT, RULES_DIR, SETTINGS_FILE, SKILLS_DIR
from .skills import replace_dir_warnings, stale_skill_warnings
from .symlinks import replace_file_warnings, stale_symlink_warnings


def old_shell_hook_warnings():
    old_hooks_dir = CLAUDE_DIR / "hooks"
    if not old_hooks_dir.is_dir():
        return []
    return [
        f"NOTE: Old shell hook {sh} has a Python replacement. "
        "Consider removing it after install."
        for sh in old_hooks_dir.glob("*.sh")
        if (REPO_ROOT / "hooks" / (sh.stem.replace("-", "_") + ".py")).exists()
    ]


def check_preflight_warnings(symlink_ops, skill_ops=None):
    if skill_ops is None:
        skill_ops = []
    warnings = [
        *replace_file_warnings(symlink_ops),
        *replace_dir_warnings(skill_ops),
        *old_shell_hook_warnings(),
        *stale_symlink_warnings(),
        *stale_skill_warnings(),
    ]
    errors = []
    if SETTINGS_FILE.exists() and not os.access(SETTINGS_FILE, os.W_OK):
        warnings.append(f"WARNING: {SETTINGS_FILE} is read-only.")
    if RULES_DIR.exists() and not RULES_DIR.is_dir():
        errors.append(f"ERROR: {RULES_DIR} exists but is not a directory.")
    if SKILLS_DIR.exists() and not SKILLS_DIR.is_dir():
        errors.append(f"ERROR: {SKILLS_DIR} exists but is not a directory.")
    return warnings, errors
