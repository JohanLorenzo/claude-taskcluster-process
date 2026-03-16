import json
import subprocess
import sys
from dataclasses import dataclass, field

from .constants import LOCAL_CONFIG_FILE, RULES_DIR, SETTINGS_FILE
from .local_config import _compute_local_config_update, _generate_local_config
from .preflight import _check_preflight_warnings
from .settings import (
    _compute_new_settings,
    _load_hooks_config,
    _load_settings,
    _settings_diff,
)
from .symlinks import _compute_symlink_ops, _print_symlink_ops
from .tools import _check_tools


@dataclass
class _Plan:
    local_config_diff: list
    new_local_content: str | None
    settings_diff: list
    new_settings: dict
    symlink_ops: list
    actionable_ops: list
    warnings: list = field(default_factory=list)

    @property
    def has_changes(self):
        return bool(self.local_config_diff or self.settings_diff or self.actionable_ops)


def _plan_changes():
    settings = _load_settings()
    hooks_config = _load_hooks_config()
    symlink_ops = _compute_symlink_ops()
    warnings, errors = _check_preflight_warnings(symlink_ops)
    for e in errors:
        print(e, file=sys.stderr)
    if errors:
        sys.exit(1)
    local_config_diff, new_local_content, new_repos = _compute_local_config_update()
    new_repo_paths = [r["path"] for r in new_repos]
    new_settings = _compute_new_settings(
        settings, hooks_config, repo_paths=new_repo_paths
    )
    return _Plan(
        local_config_diff=local_config_diff,
        new_local_content=new_local_content,
        settings_diff=_settings_diff(settings, new_settings),
        new_settings=new_settings,
        symlink_ops=symlink_ops,
        actionable_ops=[op for op in symlink_ops if op[0] != "noop"],
        warnings=warnings,
    )


def _preview_changes(plan):
    for w in plan.warnings:
        print(w)
    for path, diff in [
        (LOCAL_CONFIG_FILE, plan.local_config_diff),
        (SETTINGS_FILE, plan.settings_diff),
    ]:
        if diff:
            print(f"\n--- {path} ---")
            print("".join(diff))
        else:
            print(f"\n= no change: {path}")
    if plan.symlink_ops:
        print("\n--- rules/ symlinks ---")
        _print_symlink_ops(plan.symlink_ops)


def _write_files(plan):
    if plan.local_config_diff:
        LOCAL_CONFIG_FILE.write_text(plan.new_local_content)
        print(f"Updated: {LOCAL_CONFIG_FILE}")
    SETTINGS_FILE.write_text(json.dumps(plan.new_settings, indent=2) + "\n")
    print(f"Updated: {SETTINGS_FILE}")


def _apply_symlink_op(op):
    kind, src, target = op[0], op[1], op[2]
    if target.is_symlink() or target.exists():
        target.unlink()
    target.symlink_to(src)
    verb = "Replaced" if kind == "replace_file" else "Linked"
    print(f"{verb}: {target} → {src}")


def _apply_symlinks(ops):
    RULES_DIR.mkdir(exist_ok=True)
    for op in ops:
        _apply_symlink_op(op)


def _apply_changes(plan):
    _write_files(plan)
    _apply_symlinks(plan.actionable_ops)
    print("\nDone.")
    if (
        subprocess.run(
            ["git", "remote", "get-url", "origin"], capture_output=True
        ).returncode
        == 0
    ):
        print(
            "Note: old ~/.claude/hooks/*.sh scripts can be removed if no longer needed."
        )


def main():
    _check_tools()
    if not LOCAL_CONFIG_FILE.exists():
        _generate_local_config()
    plan = _plan_changes()
    _preview_changes(plan)
    if not plan.has_changes:
        print("\nAlready up to date.")
        sys.exit(0)
    if input("\nApply changes? [y/N]: ").strip().lower() != "y":
        print("No changes made.")
        sys.exit(0)
    _apply_changes(plan)
