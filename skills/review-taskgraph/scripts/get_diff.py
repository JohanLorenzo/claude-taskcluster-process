#!/usr/bin/env python3

import json
import re
import subprocess
import sys


def _detect_pr_range():
    """Try to detect and return the diff for an open PR on the current branch."""
    pr = subprocess.run(
        ["gh", "pr", "view", "--json", "baseRefName,url,headRefName"],
        capture_output=True,
        text=True,
        check=False,
    )
    if pr.returncode != 0:
        return None, None
    try:
        data = json.loads(pr.stdout)
        base_ref = data["baseRefName"]
        pr_url = data["url"]
        head_ref = data["headRefName"]
    except (json.JSONDecodeError, KeyError):
        return None, None

    for remote_base in (f"origin/{base_ref}", f"upstream/{base_ref}"):
        mb = subprocess.run(
            ["git", "merge-base", remote_base, "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if mb.returncode != 0:
            continue
        merge_base = mb.stdout.strip()
        diff = subprocess.run(
            ["git", "diff", f"{merge_base}..HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if diff.returncode == 0 and diff.stdout.strip():
            description = f"PR {pr_url} ({head_ref} → {base_ref})"
            return diff.stdout, description

    return None, None


def _detect_base_range():
    """Fall back to diff of commits ahead of a known base branch."""
    for base in ("origin/master", "origin/main", "upstream/master", "upstream/main"):
        check = subprocess.run(
            ["git", "rev-parse", "--verify", base],
            capture_output=True,
            text=True,
            check=False,
        )
        if check.returncode != 0:
            continue
        diff = subprocess.run(
            ["git", "diff", f"{base}..HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if diff.returncode == 0 and diff.stdout.strip():
            return diff.stdout, f"commits ahead of {base}"

    return None, None


def _detect_commit_range():
    diff, description = _detect_pr_range()
    if diff:
        return diff, description
    return _detect_base_range()


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
        if result.returncode == 0 and not result.stdout.strip():
            diff, description = _detect_commit_range()
            if diff:
                print(
                    f"No uncommitted changes. Reviewing {description}.",
                    file=sys.stderr,
                )
                return diff
            print("Diff is empty — nothing to review.", file=sys.stderr)
            sys.exit(1)

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
