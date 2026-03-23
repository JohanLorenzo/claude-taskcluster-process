import logging

from .constants import REPO_ROOT, SKILLS_DIR

logger = logging.getLogger(__name__)


def compute_skill_ops():
    ops = []
    skills_src_dir = REPO_ROOT / "skills"
    if not skills_src_dir.is_dir():
        return ops
    for src in sorted(skills_src_dir.iterdir()):
        if not src.is_dir() or not (src / "SKILL.md").exists():
            continue
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
    return ops


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
    skills_src_dir = str((REPO_ROOT / "skills").resolve())
    return [
        f"WARNING: Stale skill symlink: {link} → {link.readlink()}"
        for link in SKILLS_DIR.iterdir()
        if link.is_symlink()
        and not link.resolve().exists()
        and str(link.readlink()).startswith(skills_src_dir)
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
        elif op[0] == "noop":
            logger.info("  = no change: %s", op[2])
