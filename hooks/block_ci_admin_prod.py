#!/usr/bin/env python3
"""Hook: block ci-admin apply against the firefoxci production environment."""

import json
import logging
import re
import sys

logger = logging.getLogger(__name__)


def check(tool_input):
    command = tool_input.get("command", "")
    if "ci-admin" not in command or "apply" not in command:
        return True, ""
    if re.search(r"--environment[= ]firefoxci\b", command):
        return (
            False,
            "Blocked: ci-admin apply --environment firefoxci targets production. "
            "Use 'ci-admin diff' to preview, or use the staging environment.",
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
