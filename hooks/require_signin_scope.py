#!/usr/bin/env python3
"""Hook: require --scope when running taskcluster signin."""

import json
import sys


def check(tool_input, cwd=None):
    command = tool_input.get("command", "")
    if "taskcluster signin" not in command:
        return True, ""
    if "--scope" not in command:
        return False, "taskcluster signin must include --scope to limit credentials."
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
