#!/usr/bin/env python3
"""Hook: block gh commands that post comments/reviews on GitHub PRs or issues.

Drafting a PR and writing/editing its description is allowed. Posting a
comment, a review, or a reply to a review comment is not.
"""

import json
import logging
import re
import sys

logger = logging.getLogger(__name__)

_SEGMENT_SPLIT = re.compile(r";|\|\||&&|\||\n")
_LEADING_NOISE = re.compile(r"^[\s(]*(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*")
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_COMMENT_PATH_RE = re.compile(r"/(comments|replies|reviews)\b")
_FIELD_FLAG_RE = re.compile(r"(?:^|\s)(-f|-F|--field|--raw-field|--input)(?:=|\s|$)")
_METHOD_RE = re.compile(r"--method[= ](\S+)|-X\s*(\S+)")
_MUTATION_COMMENT_RE = re.compile(
    r"mutation.*(?:addcomment|addpullrequestreview|deletepullrequestreview|"
    r"resolvereviewthread|addpullrequestreviewthreadreply|updateissuecomment|"
    r"addlabelstolabelable)",
    re.IGNORECASE | re.DOTALL,
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


_COMMENT_COMMAND_RULES = [
    (re.compile(r"gh\s+pr\s+comment\b"), "gh pr comment posts a comment on a PR."),
    (
        re.compile(r"gh\s+issue\s+comment\b"),
        "gh issue comment posts a comment (works on PR numbers too).",
    ),
    (re.compile(r"gh\s+pr\s+review\b"), "gh pr review posts a review on a PR."),
]


def _closes_with_comment(segment):
    return re.match(r"gh\s+(?:pr|issue)\s+close\b", segment) and re.search(
        r"(?:^|\s)(-c|--comment)(?:=|\s|$)", segment
    )


def _graphql_mutation_blocked(segment):
    return re.match(r"gh\s+api\s+graphql\b", segment) and (
        "mutation" in segment.lower() and _MUTATION_COMMENT_RE.search(segment)
    )


def _api_write_blocked(segment):
    return (
        re.match(r"gh\s+api\b", segment)
        and not re.match(r"gh\s+api\s+graphql\b", segment)
        and _COMMENT_PATH_RE.search(segment)
        and _is_write_request(segment)
    )


def _check_segment(segment):
    for pattern, reason in _COMMENT_COMMAND_RULES:
        if pattern.match(segment):
            return False, reason
    if _closes_with_comment(segment):
        return False, "gh pr/issue close -c posts a closing comment."
    if _graphql_mutation_blocked(segment):
        return False, "gh api graphql mutation posts a comment/review."
    if _api_write_blocked(segment):
        return (
            False,
            "gh api write request against a comments/reviews/replies endpoint.",
        )
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
