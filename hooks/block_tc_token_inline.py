#!/usr/bin/env python3
"""Hook: block inline TASKCLUSTER_ACCESS_TOKEN assignments in Bash commands."""

import json
import logging
import re
import sys

logger = logging.getLogger(__name__)

# Matches TASKCLUSTER_ACCESS_TOKEN= when not immediately preceded by a quote,
# which would indicate it is inside a quoted string argument.
_PATTERN = re.compile(r"(?<!['\"])TASKCLUSTER_ACCESS_TOKEN=\S")


def check(tool_input):
    command = tool_input.get("command", "")
    if _PATTERN.search(command):
        return (
            False,
            "Do not inline TASKCLUSTER_ACCESS_TOKEN in commands. "
            "Redirect `taskcluster signin` to a temp file and `source` it instead.",
        )
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
