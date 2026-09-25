#!/usr/bin/env python3
"""Hook: block git commands that would GPG-sign."""

import json
import logging
import re
import shutil
import subprocess
import sys

GIT = shutil.which("git") or "git"

logger = logging.getLogger(__name__)

_SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||[;|]|\n")

_SIGNING_SUBCOMMANDS = {
    "commit",
    "merge",
    "rebase",
    "cherry-pick",
    "revert",
    "am",
    "absorb",
    "pull",
}
_TAG_SIGN_FLAGS = {"-s", "-u", "--sign"}
_TAG_NON_CREATE_FLAGS = {"-l", "--list", "-d", "--delete"}

_BLOCK_REASON = (
    "GPG signing is unavailable in Claude sessions (~/.gnupg is "
    "sandbox-denied on purpose, see sandbox-config.json). Stage the changes "
    "and ask the user to run the command themselves with `! <command>`."
)


def _strip_git_prefix(tokens):
    if not tokens or tokens[0] != "git":
        return None
    i = 1
    while i < len(tokens):
        if tokens[i] in ("-C", "-c"):
            i += 2
        else:
            break
    return tokens[i:]


def _has_explicit_sign_flag(args):
    return any(arg == "-S" or arg.startswith("--gpg-sign") for arg in args)


def _tag_creates(args):
    return not any(arg in _TAG_NON_CREATE_FLAGS for arg in args)


def _check_git_invocation(rest, signing_config):
    if not rest:
        return True, ""

    subcommand = rest[0]
    args = rest[1:]

    if _has_explicit_sign_flag(args):
        return False, _BLOCK_REASON

    if subcommand == "tag":
        blocked = any(arg in _TAG_SIGN_FLAGS for arg in args) or (
            signing_config.get("tag") and _tag_creates(args)
        )
    else:
        blocked = signing_config.get("commit") and subcommand in _SIGNING_SUBCOMMANDS

    return (False, _BLOCK_REASON) if blocked else (True, "")


def check(data, signing_config):
    if data.get("tool_name") != "Bash":
        return True, ""

    command = data.get("tool_input", {}).get("command", "")
    for segment in _SEGMENT_SPLIT_RE.split(command):
        rest = _strip_git_prefix(segment.split())
        if rest is None:
            continue
        allowed, reason = _check_git_invocation(rest, signing_config)
        if not allowed:
            return allowed, reason

    return True, ""


def _bool_config(key, cwd):
    result = subprocess.run(  # noqa: S603
        [GIT, "-C", cwd, "config", "--bool", key],
        capture_output=True,
        check=False,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _read_signing_config(cwd):
    return {
        "commit": _bool_config("commit.gpgsign", cwd),
        "tag": _bool_config("tag.gpgSign", cwd),
    }


def main():
    logging.basicConfig(format="%(message)s")
    data = json.load(sys.stdin)
    cwd = data.get("cwd") or "."
    signing_config = _read_signing_config(cwd)
    allowed, reason = check(data, signing_config)
    if not allowed:
        logger.error("BLOCKED: %s", reason)
        sys.exit(2)


if __name__ == "__main__":
    main()
