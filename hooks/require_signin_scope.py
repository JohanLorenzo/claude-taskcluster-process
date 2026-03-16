#!/usr/bin/env python3
"""Hook: require --scope when running taskcluster signin."""

import json
import logging
import sys

logger = logging.getLogger(__name__)


def check(tool_input):
    command = tool_input.get("command", "")
    if "taskcluster signin" not in command:
        return True, ""
    if "--scope" not in command:
        return False, "taskcluster signin must include --scope to limit credentials."
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
