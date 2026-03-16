import logging

from .constants import REPO_ROOT, RULES_DIR
from .utils import unified_diff

logger = logging.getLogger(__name__)


def compute_symlink_ops():
    ops = []
    rules_src_dir = REPO_ROOT / "rules"
    for src in sorted(rules_src_dir.glob("*.md")):
        src_resolved = src.resolve()
        target = RULES_DIR / src.name
        if not target.exists() and not target.is_symlink():
            ops.append(("create", src, target))
        elif target.is_symlink():
            current = target.readlink()
            if current.resolve() == src_resolved:
                ops.append(("noop", src, target))
            else:
                ops.append(("update", src, target, current))
        else:
            ops.append(("replace_file", src, target))
    return ops


def replace_file_warnings(ops):
    return [
        f"WARNING: {op[2]} is a regular file (not a symlink) — will be replaced."
        for op in ops
        if op[0] == "replace_file"
    ]


def stale_symlink_warnings():
    if not RULES_DIR.is_dir():
        return []
    return [
        f"WARNING: Stale symlink: {link} → {link.readlink()}"
        for link in RULES_DIR.glob("*.md")
        if link.is_symlink() and not link.resolve().exists()
    ]


def print_symlink_ops(ops):
    for op in ops:
        if op[0] == "create":
            logger.info("  + new symlink: %s → %s", op[2], op[1])
        elif op[0] == "update":
            logger.info("  ~ update symlink: %s → %s (was → %s)", op[2], op[1], op[3])
        elif op[0] == "replace_file":
            src_text = op[1].read_text()
            target_text = op[2].read_text()
            diff = unified_diff(target_text, src_text, str(op[2]), str(op[1]))
            if diff:
                logger.info("  ~ replace file with symlink: %s", op[2])
                logger.info("".join(diff[:40]))
            else:
                logger.info("  ~ replace file with symlink (same content): %s", op[2])
        elif op[0] == "noop":
            logger.info("  = no change: %s", op[2])
