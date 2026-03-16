#!/usr/bin/env python3
"""Hook: block all tool calls if CLAUDE.local.md is missing."""

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LOCAL_CONFIG = _REPO_ROOT / "CLAUDE.local.md"


def check(local_config_path=None):
    path = local_config_path or _LOCAL_CONFIG
    if not Path(path).exists():
        return (
            False,
            f"CLAUDE.local.md not found at {path}. "
            "Copy CLAUDE.local.md.template and fill it in, "
            "or run: python install.py",
        )
    return True, ""


def main():
    logging.basicConfig(format="%(message)s")
    sys.stdin.read()  # consume stdin (required by hook protocol)
    allowed, reason = check()
    if not allowed:
        logger.error("BLOCKED: %s", reason)
        sys.exit(2)


if __name__ == "__main__":
    main()
