#!/usr/bin/env python3
"""Hook: block force push to the upstream (non-fork) repository."""

import json
import logging
import shutil
import subprocess
import sys

GH = shutil.which("gh") or "gh"
GIT = shutil.which("git") or "git"

logger = logging.getLogger(__name__)


def _parse_remote(command):
    parts = command.split()
    args = [p for p in parts if not p.startswith("-")]
    push_idx = args.index("push") if "push" in args else -1
    if push_idx < 0 or push_idx + 1 >= len(args):
        return "origin"
    return args[push_idx + 1]


def _get_remote_url(remote, cwd):
    result = subprocess.run(  # noqa: S603
        [GIT, "-C", cwd, "remote", "get-url", remote],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _is_fork(remote_url):
    result = subprocess.run(  # noqa: S603
        [GH, "repo", "view", remote_url, "--json", "isFork", "--jq", ".isFork"],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        return False
    return result.stdout.strip() == "true"


def check(tool_input, cwd=None):
    command = tool_input.get("command", "")
    if "git push" not in command:
        return True, ""
    if "--force" not in command and "--force-with-lease" not in command:
        return True, ""
    effective_cwd = cwd or "."
    remote = _parse_remote(command)
    remote_url = _get_remote_url(remote, effective_cwd)
    if remote_url and _is_fork(remote_url):
        return True, ""
    return (
        False,
        f"Force push to upstream repository '{remote}' is not allowed. "
        "Use a fork instead.",
    )


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
