#!/usr/bin/env python3
"""Hook: block gh api calls that use non-GET HTTP methods."""

import json
import logging
import re
import sys

logger = logging.getLogger(__name__)

_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def check(tool_input):
    command = tool_input.get("command", "")
    if "gh api" not in command:
        return True, ""
    match = re.search(r"--method\s+(\S+)", command)
    if not match:
        return True, ""
    method = match.group(1).upper()
    if method in _WRITE_METHODS:
        return False, f"gh api write operations (--method {method}) are not allowed."
    return True, ""


def main():
    logging.basicConfig(format="%(message)s")
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input", {})
    allowed, reason = check(tool_input)
    if not allowed:
        logger.error("BLOCKED: %s", reason)
        sys.exit(2)


if __name__ == "__main__":
    main()
