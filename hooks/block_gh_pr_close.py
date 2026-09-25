#!/usr/bin/env python3
"""Hook: block gh commands that close a PR.

A stateless hook can't tell that a `gh pr create` is a replacement for an
earlier PR. What it can do is block the close, which a replacement always
needs. When a PR really should close, the user closes it.
"""

import json
import logging
import re
import sys

logger = logging.getLogger(__name__)

_SEGMENT_SPLIT = re.compile(r";|\|\||&&|\||\n")
_LEADING_NOISE = re.compile(r"^[\s(]*(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*")
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_FIELD_FLAG_RE = re.compile(r"(?:^|\s)(-f|-F|--field|--raw-field|--input)(?:=|\s|$)")
_METHOD_RE = re.compile(r"--method[= ](\S+)|-X\s*(\S+)")
_PULLS_PATH_RE = re.compile(r"/pulls/\d+\b")
_STATE_CLOSED_RE = re.compile(
    r"(?:-f|-F|--field|--raw-field)(?:=|\s+)state=closed", re.IGNORECASE
)
_MUTATION_CLOSE_RE = re.compile(
    r"mutation.*closepullrequest", re.IGNORECASE | re.DOTALL
)

_BLOCK_MESSAGE = (
    "Closing PRs is blocked. Amend the existing PR (force-push, `gh pr edit`), "
    "or reuse its number for one half of a split. Ask the user if it really "
    "must be closed."
)


def _gh_segments(command):
    for segment in _SEGMENT_SPLIT.split(command):
        stripped = _LEADING_NOISE.sub("", segment.strip())
        if stripped.startswith("gh "):
            yield stripped


def _is_write_request(segment):
    method_match = _METHOD_RE.search(segment)
    if method_match:
        method = (method_match.group(1) or method_match.group(2)).upper()
        return method in _WRITE_METHODS
    return bool(_FIELD_FLAG_RE.search(segment))


def _pr_close_blocked(segment):
    return bool(re.match(r"gh\s+pr\s+close\b", segment))


def _graphql_close_blocked(segment):
    return bool(
        re.match(r"gh\s+api\s+graphql\b", segment)
        and "mutation" in segment.lower()
        and _MUTATION_CLOSE_RE.search(segment)
    )


def _api_close_blocked(segment):
    return bool(
        re.match(r"gh\s+api\b", segment)
        and not re.match(r"gh\s+api\s+graphql\b", segment)
        and _PULLS_PATH_RE.search(segment)
        and _is_write_request(segment)
        and _STATE_CLOSED_RE.search(segment)
    )


def _check_segment(segment):
    if _pr_close_blocked(segment):
        return False, _BLOCK_MESSAGE
    if _graphql_close_blocked(segment):
        return False, _BLOCK_MESSAGE
    if _api_close_blocked(segment):
        return False, _BLOCK_MESSAGE
    return True, ""


def check(tool_input):
    command = tool_input.get("command", "")
    if "gh " not in command:
        return True, ""
    for segment in _gh_segments(command):
        allowed, reason = _check_segment(segment)
        if not allowed:
            return allowed, reason
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
