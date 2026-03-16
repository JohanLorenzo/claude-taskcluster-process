#!/usr/bin/env python3
"""Hook: block git push to non-fork repositories."""

import json
import re
import subprocess
import sys


def _parse_remote(command):
    parts = command.split()
    idx = parts.index("push") + 1 if "push" in parts else -1
    if idx < 0 or idx >= len(parts):
        return "origin"
    args = [p for p in parts[idx:] if not p.startswith("-")]
    if not args:
        return "origin"
    return args[0]


def _get_remote_url(remote, cwd):
    result = subprocess.run(
        ["git", "-C", cwd, "remote", "get-url", remote],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _parse_org_repo(url):
    match = re.search(r"github\.com[:/](.+?/[^/]+?)(?:\.git)?$", url)
    return match.group(1) if match else None


def _is_fork(org_repo):
    result = subprocess.run(
        ["gh", "repo", "view", org_repo, "--json", "isFork", "--jq", ".isFork"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() == "true"


def check(tool_input, cwd=None):
    command = tool_input.get("command", "")
    if "git push" not in command:
        return True, ""
    remote = _parse_remote(command)
    url = _get_remote_url(remote, cwd or ".")
    if not url:
        return False, f"Could not determine URL for remote '{remote}'."
    org_repo = _parse_org_repo(url)
    if not org_repo:
        return True, ""
    is_fork = _is_fork(org_repo)
    if is_fork is None:
        return False, f"Could not determine if '{org_repo}' is a fork."
    if not is_fork:
        return (
            False,
            f"Refusing to push to '{org_repo}': not a fork. Use a fork remote.",
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
