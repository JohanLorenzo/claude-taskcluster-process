#!/usr/bin/env python3
"""Hook: block ci-admin apply against the firefoxci production environment."""

import json
import re
import sys


def check(tool_input, cwd=None):
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
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input", {})
    cwd = data.get("cwd")
    allowed, reason = check(tool_input, cwd=cwd)
    if not allowed:
        print(f"BLOCKED: {reason}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
