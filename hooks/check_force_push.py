#!/usr/bin/env python3
"""Hook: block force push that rewrites base branch commits."""

import json
import subprocess
import sys


def _get_base_branch(cwd):
    result = subprocess.run(
        ["gh", "pr", "view", "--json", "baseRefName", "--jq", ".baseRefName"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


def _parse_remote_and_branch(command):
    parts = command.split()
    args = [p for p in parts if not p.startswith("-")]
    push_idx = args.index("push") if "push" in args else -1
    if push_idx < 0:
        return "origin", None
    positional = args[push_idx + 1 :]
    if len(positional) == 0:
        return "origin", None
    if len(positional) == 1:
        return "origin", positional[0]
    return positional[0], positional[1]


def _is_ancestor(remote, base_branch, cwd):
    ref = f"{remote}/{base_branch}"
    result = subprocess.run(
        ["git", "-C", cwd, "merge-base", "--is-ancestor", ref, "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def check(tool_input, cwd=None):
    command = tool_input.get("command", "")
    if "git push" not in command:
        return True, ""
    if "--force" not in command and "--force-with-lease" not in command:
        return True, ""
    effective_cwd = cwd or "."
    remote, _ = _parse_remote_and_branch(command)
    base_branch = _get_base_branch(effective_cwd)
    if not base_branch:
        return True, ""
    if not _is_ancestor(remote, base_branch, effective_cwd):
        return (
            False,
            f"Force push would rewrite commits from {remote}/{base_branch}. "
            "Only rewrite your own commits.",
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
