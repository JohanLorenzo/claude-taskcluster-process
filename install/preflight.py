import os

from .constants import CLAUDE_DIR, REPO_ROOT, RULES_DIR, SETTINGS_FILE
from .symlinks import _replace_file_warnings, _stale_symlink_warnings


def _old_shell_hook_warnings():
    old_hooks_dir = CLAUDE_DIR / "hooks"
    if not old_hooks_dir.is_dir():
        return []
    return [
        f"NOTE: Old shell hook {sh} has a Python replacement. "
        "Consider removing it after install."
        for sh in old_hooks_dir.glob("*.sh")
        if (REPO_ROOT / "hooks" / (sh.stem.replace("-", "_") + ".py")).exists()
    ]


def _check_preflight_warnings(ops):
    warnings = [
        *_replace_file_warnings(ops),
        *_old_shell_hook_warnings(),
        *_stale_symlink_warnings(),
    ]
    errors = []
    if SETTINGS_FILE.exists() and not os.access(SETTINGS_FILE, os.W_OK):
        warnings.append(f"WARNING: {SETTINGS_FILE} is read-only.")
    if RULES_DIR.exists() and not RULES_DIR.is_dir():
        errors.append(f"ERROR: {RULES_DIR} exists but is not a directory.")
    return warnings, errors
