import json
import logging

from .constants import (
    EXTERNAL_SKILLS_CONFIG_FILE,
    LOCAL_CONFIG_FILE,
    REPO_ROOT,
    SKILLS_DIR,
)
from .local_config import parse_tracked_repos

logger = logging.getLogger(__name__)


def skill_source_dirs():
    dirs = [REPO_ROOT / "skills"]
    warnings = []
    if not EXTERNAL_SKILLS_CONFIG_FILE.is_file():
        return dirs, warnings
    try:
        config = json.loads(EXTERNAL_SKILLS_CONFIG_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return dirs, warnings
    tracked_repos = (
        parse_tracked_repos(LOCAL_CONFIG_FILE.read_text())
        if LOCAL_CONFIG_FILE.is_file()
        else {}
    )
    for slug, skills_subdir in config.items():
        repo_path = tracked_repos.get(slug)
        if repo_path is None:
            warnings.append(
                f"WARNING: external skill source {slug!r} is not a tracked repo"
                " in CLAUDE.local.md — skipping."
            )
            continue
        skill_dir = repo_path / skills_subdir
        if not skill_dir.is_dir():
            warnings.append(
                f"WARNING: external skill source {skill_dir} does not exist — skipping."
            )
            continue
        dirs.append(skill_dir)
    return dirs, warnings


def _compute_skill_ops_and_warnings():
    dirs, warnings = skill_source_dirs()
    ops = []
    seen = {}
    for skills_src_dir in dirs:
        if not skills_src_dir.is_dir():
            continue
        for src in sorted(skills_src_dir.iterdir()):
            if not src.is_dir() or not (src / "SKILL.md").exists():
                continue
            if src.name in seen:
                warnings.append(
                    f"WARNING: duplicate skill name {src.name!r}: {src} shadowed by"
                    f" {seen[src.name]}."
                )
                continue
            seen[src.name] = src
            src_resolved = src.resolve()
            target = SKILLS_DIR / src.name
            if not target.exists() and not target.is_symlink():
                ops.append(("create", src, target))
            elif target.is_symlink():
                current = target.readlink()
                if current.resolve() == src_resolved:
                    ops.append(("noop", src, target))
                else:
                    ops.append(("update", src, target, current))
            else:
                ops.append(("replace_dir", src, target))
    return ops, warnings


def compute_skill_ops():
    ops, _ = _compute_skill_ops_and_warnings()
    return ops


def external_skill_warnings():
    _, warnings = _compute_skill_ops_and_warnings()
    return warnings


def replace_dir_warnings(ops):
    return [
        f"WARNING: {op[2]} is a regular directory (not a symlink)"
        " — remove it manually to install the skill."
        for op in ops
        if op[0] == "replace_dir"
    ]


def stale_skill_warnings():
    if not SKILLS_DIR.is_dir():
        return []
    source_dirs, _ = skill_source_dirs()
    resolved_prefixes = [str(d.resolve()) for d in source_dirs]
    return [
        f"WARNING: Stale skill symlink: {link} → {link.readlink()}"
        for link in SKILLS_DIR.iterdir()
        if link.is_symlink()
        and not link.resolve().exists()
        and any(str(link.readlink()).startswith(p) for p in resolved_prefixes)
    ]


def print_skill_ops(ops):
    for op in ops:
        if op[0] == "create":
            logger.info("  + new skill symlink: %s → %s", op[2], op[1])
        elif op[0] == "update":
            logger.info(
                "  ~ update skill symlink: %s → %s (was → %s)", op[2], op[1], op[3]
            )
        elif op[0] == "replace_dir":
            logger.info("  ! skip (regular dir): %s", op[2])
