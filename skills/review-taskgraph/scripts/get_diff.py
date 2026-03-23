#!/usr/bin/env python3

import re
import subprocess
import sys


def get_diff(arg=None):
    if arg and arg.startswith("https://github.com/"):
        match = re.match(r"https://github\.com/([^/]+/[^/]+)/pull/(\d+)", arg)
        if not match:
            print(f"Cannot parse GitHub PR URL: {arg}", file=sys.stderr)
            sys.exit(1)
        repo, pr_number = match.group(1), match.group(2)
        result = subprocess.run(
            ["gh", "pr", "diff", pr_number, "--repo", repo],
            capture_output=True,
            text=True,
            check=False,
        )
    elif arg and re.match(r"^D\d+$", arg):
        result = subprocess.run(
            ["moz-phab", "patch", "--raw", arg],
            capture_output=True,
            text=True,
            check=False,
        )
    elif arg and re.match(r"^https://phabricator\.services\.mozilla\.com/(D\d+)", arg):
        revision_id = re.match(
            r"^https://phabricator\.services\.mozilla\.com/(D\d+)", arg
        ).group(1)
        result = subprocess.run(
            ["moz-phab", "patch", "--raw", revision_id],
            capture_output=True,
            text=True,
            check=False,
        )
    elif arg and ".." in arg:
        result = subprocess.run(
            ["git", "diff", arg],
            capture_output=True,
            text=True,
            check=False,
        )
    else:
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )

    if result.returncode != 0:
        print(result.stderr or "Command failed", file=sys.stderr)
        sys.exit(1)

    diff = result.stdout
    if not diff.strip():
        print("Diff is empty — nothing to review.", file=sys.stderr)
        sys.exit(1)

    return diff


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    print(get_diff(arg))
