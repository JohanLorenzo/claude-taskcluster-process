#!/usr/bin/env python3

import json
import re
import subprocess
import sys


def _git_cwd():
    """Return the git toplevel directory, or None if not in a git repo."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _detect_pr_range(cwd=None):
    """Try to detect and return the diff for an open PR on the current branch."""
    pr = subprocess.run(
        ["gh", "pr", "view", "--json", "number,url,headRefName"],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if pr.returncode != 0:
        return None, None
    try:
        data = json.loads(pr.stdout)
        pr_number = str(data["number"])
        pr_url = data["url"]
        head_ref = data["headRefName"]
    except (json.JSONDecodeError, KeyError):
        return None, None

    diff = subprocess.run(
        ["gh", "pr", "diff", pr_number],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if diff.returncode == 0 and diff.stdout.strip():
        return diff.stdout, f"PR {pr_url} ({head_ref})"

    return None, None


def _detect_base_range(cwd=None):
    """Fall back to diff of commits ahead of a known base branch."""
    for base in ("origin/master", "origin/main", "upstream/master", "upstream/main"):
        check = subprocess.run(
            ["git", "rev-parse", "--verify", base],
            capture_output=True,
            text=True,
            check=False,
            cwd=cwd,
        )
        if check.returncode != 0:
            continue
        diff = subprocess.run(
            ["git", "diff", f"{base}..HEAD"],
            capture_output=True,
            text=True,
            check=False,
            cwd=cwd,
        )
        if diff.returncode == 0 and diff.stdout.strip():
            return diff.stdout, f"commits ahead of {base}"

    return None, None


def _detect_commit_range(cwd=None):
    diff, description = _detect_pr_range(cwd=cwd)
    if diff:
        return diff, description
    return _detect_base_range(cwd=cwd)


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
    else:
        cwd = _git_cwd()
        if arg and ".." in arg:
            result = subprocess.run(
                ["git", "diff", arg],
                capture_output=True,
                text=True,
                check=False,
                cwd=cwd,
            )
        else:
            result = subprocess.run(
                ["git", "diff", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
                cwd=cwd,
            )
            if result.returncode == 0 and not result.stdout.strip():
                diff, description = _detect_commit_range(cwd=cwd)
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
