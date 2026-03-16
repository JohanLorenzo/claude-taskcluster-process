#!/usr/bin/env python3
"""Hook: block git commit --no-verify."""

import json
import logging
import sys

logger = logging.getLogger(__name__)


def check(tool_input, cwd=None):
    command = tool_input.get("command", "")
    if "git commit" in command and "--no-verify" in command:
        return False, "Do not use --no-verify. Fix the underlying hook issue instead."
    return True, ""


def main():
    logging.basicConfig(format="%(message)s")
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input", {})
    cwd = data.get("cwd")
    allowed, reason = check(tool_input, cwd=cwd)
    if not allowed:
        logger.error("BLOCKED: %s", reason)
        sys.exit(2)


if __name__ == "__main__":
    main()
