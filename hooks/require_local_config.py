#!/usr/bin/env python3
"""Hook: block all tool calls if CLAUDE.local.md is missing."""

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LOCAL_CONFIG = _REPO_ROOT / "CLAUDE.local.md"


def check(tool_input, cwd=None, local_config_path=None):
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
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input", {})
    cwd = data.get("cwd")
    allowed, reason = check(tool_input, cwd=cwd)
    if not allowed:
        print(f"BLOCKED: {reason}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
