import json
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

from .constants import (
    LOCAL_CONFIG_FILE,
    REPO_ROOT,
    RULES_DIR,
    SETTINGS_FILE,
    SKILLS_DIR,
)
from .local_config import compute_local_config_update
from .preflight import check_preflight_warnings
from .settings import (
    compute_new_settings,
    load_hooks_config,
    load_permissions_config,
    load_sandbox_config,
    load_settings,
    settings_diff,
)
from .skills import compute_skill_ops, print_skill_ops
from .symlinks import compute_symlink_ops, print_symlink_ops

GIT = shutil.which("git") or "git"

logger = logging.getLogger(__name__)


@dataclass
class Plan:
    local_config_diff: list
    new_local_content: str | None
    settings_diff: list
    new_settings: dict
    symlink_ops: list
    actionable_ops: list
    skill_ops: list
    actionable_skill_ops: list
    warnings: list = field(default_factory=list)

    @property
    def has_changes(self):
        return bool(
            self.local_config_diff
            or self.settings_diff
            or self.actionable_ops
            or self.actionable_skill_ops
        )


def plan_changes():
    current_settings = load_settings()
    hooks_config = load_hooks_config()
    symlink_ops = compute_symlink_ops()
    skill_ops = compute_skill_ops()
    warnings, errors = check_preflight_warnings(symlink_ops, skill_ops)
    for e in errors:
        logger.error(e)
    if errors:
        sys.exit(1)
    local_config_diff, new_local_content, new_repos = compute_local_config_update()
    new_repo_paths = [str(REPO_ROOT)] + [r["path"] for r in new_repos]
    taskgraph_repo = new_repos[0]["path"] if new_repos else None
    managed_allow = load_permissions_config(
        repo_paths=new_repo_paths, taskgraph_repo=taskgraph_repo
    )
    sandbox_config = load_sandbox_config(repo_paths=new_repo_paths)
    new_settings = compute_new_settings(
        current_settings,
        hooks_config,
        repo_paths=new_repo_paths,
        managed_allow=managed_allow,
        sandbox=sandbox_config,
    )
    return Plan(
        local_config_diff=local_config_diff,
        new_local_content=new_local_content,
        settings_diff=settings_diff(current_settings, new_settings),
        new_settings=new_settings,
        symlink_ops=symlink_ops,
        actionable_ops=[op for op in symlink_ops if op[0] != "noop"],
        skill_ops=skill_ops,
        actionable_skill_ops=[
            op for op in skill_ops if op[0] not in ("noop", "replace_dir")
        ],
        warnings=warnings,
    )


def preview_changes(plan):
    for w in plan.warnings:
        logger.info(w)
    for path, diff in [
        (LOCAL_CONFIG_FILE, plan.local_config_diff),
        (SETTINGS_FILE, plan.settings_diff),
    ]:
        if diff:
            logger.info("\n--- %s ---", path)
            logger.info("".join(diff))
        else:
            logger.info("\n= no change: %s", path)
    if plan.symlink_ops:
        logger.info("\n--- rules/ symlinks ---")
        print_symlink_ops(plan.symlink_ops)
    if plan.skill_ops:
        logger.info("\n--- skills/ symlinks ---")
        print_skill_ops(plan.skill_ops)


def write_files(plan):
    if plan.local_config_diff:
        LOCAL_CONFIG_FILE.write_text(plan.new_local_content)
        logger.info("Updated: %s", LOCAL_CONFIG_FILE)
    SETTINGS_FILE.write_text(json.dumps(plan.new_settings, indent=2) + "\n")
    logger.info("Updated: %s", SETTINGS_FILE)


def apply_symlink_op(op):
    kind, src, target = op[0], op[1], op[2]
    if target.is_symlink() or target.exists():
        target.unlink()
    target.symlink_to(src)
    verb = "Replaced" if kind == "replace_file" else "Linked"
    logger.info("%s: %s → %s", verb, target, src)


def apply_skill_op(op):
    kind, src, target = op[0], op[1], op[2]
    if target.is_symlink():
        target.unlink()
    target.symlink_to(src)
    verb = "Updated skill" if kind == "update" else "Linked skill"
    logger.info("%s: %s → %s", verb, target, src)


def _apply_symlinks(ops):
    RULES_DIR.mkdir(exist_ok=True)
    for op in ops:
        apply_symlink_op(op)


def _apply_skills(ops):
    SKILLS_DIR.mkdir(exist_ok=True)
    for op in ops:
        apply_skill_op(op)


def apply_changes(plan):
    write_files(plan)
    _apply_symlinks(plan.actionable_ops)
    _apply_skills(plan.actionable_skill_ops)
    logger.info("\nDone.")
    if (
        subprocess.run(  # noqa: S603
            [GIT, "remote", "get-url", "origin"], capture_output=True, check=False
        ).returncode
        == 0
    ):
        logger.info(
            "Note: old ~/.claude/hooks/*.sh scripts can be removed if no longer needed."
        )
