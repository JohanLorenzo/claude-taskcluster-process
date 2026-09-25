#!/usr/bin/env python3
"""Hook: force a review pass on PR descriptions and Phabricator test plans."""

import difflib
import json
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

GH = shutil.which("gh") or "gh"
GIT = shutil.which("git") or "git"

_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "claude-pr-review"

_HEREDOC_RE = re.compile(
    r"<<-?['\"]?(?P<delim>\w+)['\"]?\n(?P<body>.*?)\n(?P=delim)", re.DOTALL
)
_BODY_FLAG_RE = re.compile(r"(?:^|\s)(?:--body(?!-file)|-b)(?:=|\s+)")
_BODY_FILE_FLAG_RE = re.compile(r"(?:^|\s)(?:--body-file|-F)(?:=|\s+)")
_TEST_PLAN_FLAG_RE = re.compile(r"(?:^|\s)--test-plan(?:=|\s+)")

_MERGE_ORDER_RE = re.compile(
    r"^#{1,6}\s*merge order\b.*?(?=^#{1,6}\s|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_CI_MARKER_RE = re.compile(
    r"\b(pytest|tox|ruff|mypy|pre-commit)\b|\d+\s+passed|all tests pass", re.IGNORECASE
)
_BULLET_RE = re.compile(
    r"^\s*[-*]\s+(`[^`]+`|Added|Updated|Modified|Changed)\b",
    re.IGNORECASE | re.MULTILINE,
)
_HEADING_RE = re.compile(r"^#{2,6}\s+.*$", re.MULTILINE)
_CHANGES_HEADING_RE = re.compile(r"^##\s*Changes\s*$", re.IGNORECASE | re.MULTILINE)
_THIS_PR_RE = re.compile(r"\bThis PR\b")
_EM_DASH_RE = re.compile("—")
_HEDGE_RE = re.compile(r"\b(seems|likely|probably|appears to|I think)\b", re.IGNORECASE)
_INFLATED_RE = re.compile(
    r"\b(pivotal|groundbreaking|exceptional|outstanding|remarkable|stellar"
    r"|incredible|amazing|fantastic|tremendous)\b",
    re.IGNORECASE,
)
_PASSIVE_RE = re.compile(r"\b(was decided|were made|was done)\b", re.IGNORECASE)

_MAX_PROSE_WORDS = 150
_MAX_FENCE_LINES = 8
_MIN_RESTATEMENT_BULLETS = 4
_MAX_HEADINGS = 3

_TRUST_CHECKLIST = (
    "Load the `pr-description` skill if you haven't.\n"
    "Trust checklist:\n"
    "- Is the why the user's, not invented?\n"
    "- Are rejected alternatives stated?\n"
    "- Is the evidence something the diff and CI don't show?\n"
    "- Is every internal name explained?\n"
    "- Cut anything a reviewer doesn't need."
)


def _read_quoted_or_bare(rest):
    rest = rest.lstrip()
    if not rest:
        return None
    quote = rest[0]
    if quote in ("'", '"'):
        end = rest.find(quote, 1)
        return rest[1:end] if end != -1 else rest[1:]
    match = re.search(r"\s", rest)
    return rest[: match.start()] if match else rest


def _value_after_flag(command, flag_re):
    match = flag_re.search(command)
    if not match:
        return None
    rest = command[match.end() :]
    heredoc = _HEREDOC_RE.search(rest)
    if heredoc:
        return heredoc.group("body")
    return _read_quoted_or_bare(rest)


def _read_body_file(path, cwd):
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = Path(cwd) / path
    try:
        return file_path.read_text()
    except OSError:
        return None


def _extract_body_value(command, cwd):
    value = _value_after_flag(command, _BODY_FLAG_RE)
    if value is not None:
        return value
    file_value = _value_after_flag(command, _BODY_FILE_FLAG_RE)
    if file_value is None:
        return None
    return _read_body_file(file_value, cwd)


def _extract_submission(command, cwd):
    if re.search(r"\bgh\s+pr\s+create\b", command):
        body = _extract_body_value(command, cwd)
        return None if body is None else ("create", body)
    if re.search(r"\bgh\s+pr\s+edit\b", command):
        body = _extract_body_value(command, cwd)
        return None if body is None else ("edit", body)
    if re.search(r"\bmoz-phab\s+submit\b", command) and "--test-plan" in command:
        value = _value_after_flag(command, _TEST_PLAN_FLAG_RE)
        return None if value is None else ("phab", value)
    return None


def _current_branch(cwd):
    result = subprocess.run(  # noqa: S603
        [GIT, "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _resolve_target(kind, command, cwd):
    if kind == "create":
        return _current_branch(cwd)
    if kind == "edit":
        match = re.search(r"\bgh\s+pr\s+edit\s+(\S+)", command)
        return match.group(1) if match else None
    if kind == "phab":
        match = re.search(r"--single\s+(\S+)", command)
        return match.group(1) if match else "HEAD"
    return None


def _strip_merge_order(body):
    return _MERGE_ORDER_RE.sub("", body)


def _strip_fences(text):
    return _FENCE_RE.sub("", text)


def _prose_word_count(body):
    return len(_strip_fences(body).split())


def _longest_fence_lines(body):
    longest = 0
    for fence in _FENCE_RE.findall(body):
        lines = fence.strip("`").strip("\n").splitlines()
        longest = max(longest, len(lines))
    return longest


def _heuristic_checks(body, stripped):
    return [
        (
            _prose_word_count(stripped) > _MAX_PROSE_WORDS,
            "more than 150 prose words",
        ),
        (
            _longest_fence_lines(body) > _MAX_FENCE_LINES,
            "a code fence longer than 8 lines",
        ),
        (
            bool(_CI_MARKER_RE.search(body)),
            "pastes CI/test output the PR's own CI already reports",
        ),
        (
            len(_BULLET_RE.findall(body)) >= _MIN_RESTATEMENT_BULLETS,
            "4 or more bullets that just restate file changes",
        ),
        (bool(_THIS_PR_RE.search(body)), 'uses "This PR" instead of first person'),
        (bool(_CHANGES_HEADING_RE.search(stripped)), 'has a "## Changes" heading'),
        (
            len(_HEADING_RE.findall(stripped)) > _MAX_HEADINGS,
            "more than 3 headings",
        ),
        (bool(_EM_DASH_RE.search(body)), "contains an em-dash"),
        (
            bool(_HEDGE_RE.search(body)),
            "hedges instead of naming the uncertainty precisely",
        ),
        (bool(_INFLATED_RE.search(body)), "uses inflated adjectives"),
        (
            bool(_PASSIVE_RE.search(body)),
            "uses passive-agency phrasing instead of naming who acted",
        ),
    ]


def find_heuristic_issues(body):
    stripped = _strip_merge_order(body)
    return [
        message for triggered, message in _heuristic_checks(body, stripped) if triggered
    ]


def _fetch_pr_body(pr_number, cwd):
    result = subprocess.run(  # noqa: S603
        [GH, "pr", "view", str(pr_number), "--json", "body", "--jq", ".body"],
        capture_output=True,
        check=False,
        text=True,
        cwd=cwd,
    )
    if result.returncode != 0:
        return None
    return result.stdout.rstrip("\n")


def _author_added_lines(remote_body, stored_body):
    stored_lines = stored_body.splitlines()
    remote_lines = remote_body.splitlines()
    matcher = difflib.SequenceMatcher(a=stored_lines, b=remote_lines)
    added = []
    for tag, _, _, j1, j2 in matcher.get_opcodes():
        if tag in ("insert", "replace"):
            added.extend(remote_lines[j1:j2])
    return added


def _missing_author_lines(new_body, author_lines):
    new_lines = set(new_body.splitlines())
    return [line for line in author_lines if line.strip() and line not in new_lines]


def _strip_author_lines(body, author_lines):
    author_set = set(author_lines)
    return "\n".join(line for line in body.splitlines() if line not in author_set)


def _author_protection_message(remote_body, missing_lines):
    lines = [
        (
            "The new body drops lines the author added by hand. "
            "Apply your change on top of them, don't drop them."
        ),
        "",
        "Author's lines missing from the new body:",
    ]
    lines.extend(f"> {line}" for line in missing_lines)
    lines.append("")
    lines.append("Current remote body:")
    lines.append(remote_body)
    return "\n".join(lines)


def check_author_edit(pr_number, new_body, stored_body, cwd):
    if stored_body is None:
        return True, "", []
    remote_body = _fetch_pr_body(pr_number, cwd)
    if remote_body is None:
        return True, "", []
    if remote_body == stored_body:
        return True, "", []
    author_lines = _author_added_lines(remote_body, stored_body)
    missing = _missing_author_lines(new_body, author_lines)
    if missing:
        return False, _author_protection_message(remote_body, missing), author_lines
    return True, "", author_lines


def _state_path(session_id, cache_dir):
    base = Path(cache_dir) if cache_dir else _DEFAULT_CACHE_DIR
    return base / f"{session_id}.json"


def _load_state(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {"reviewed": [], "pr_bodies": {}}


def _save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))


def _forced_review_message(findings):
    lines = [_TRUST_CHECKLIST]
    if findings:
        lines.append("Findings:")
        lines.extend(f"- {f}" for f in findings)
    return "\n".join(lines)


def _warning_message(findings):
    lines = ["PR description review findings (not blocking):"]
    lines.extend(f"- {f}" for f in findings)
    return "\n".join(lines)


def _check(command, cwd, session_id, cache_dir):
    submission = _extract_submission(command, cwd)
    if submission is None:
        return "allow", ""
    kind, body = submission
    target = _resolve_target(kind, command, cwd)
    if target is None:
        return "allow", ""

    state_path = _state_path(session_id, cache_dir)
    state = _load_state(state_path)
    review_key = f"{cwd}|{target}"

    author_lines = []
    if kind == "edit":
        pr_key = f"{cwd}|{target}"
        stored_body = state.get("pr_bodies", {}).get(pr_key)
        allowed, reason, author_lines = check_author_edit(
            target, body, stored_body, cwd
        )
        if not allowed:
            return "block", reason
        state.setdefault("pr_bodies", {})[pr_key] = body

    body_for_heuristics = (
        _strip_author_lines(body, author_lines) if author_lines else body
    )
    findings = find_heuristic_issues(body_for_heuristics)

    reviewed = set(state.get("reviewed", []))
    first_submit = review_key not in reviewed

    if first_submit:
        reviewed.add(review_key)
        state["reviewed"] = sorted(reviewed)
        _save_state(state_path, state)
        return "block", _forced_review_message(findings)

    _save_state(state_path, state)
    if findings:
        return "warn", _warning_message(findings)
    return "allow", ""


def check(tool_input, cwd=None, session_id=None, cache_dir=None):
    command = tool_input.get("command", "")
    if not session_id:
        return "allow", ""
    try:
        return _check(command, cwd or ".", session_id, cache_dir)
    except Exception:
        logger.exception("review_pr_description failed, failing open")
        return "allow", ""


def main():
    logging.basicConfig(format="%(message)s")
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input", {})
    cwd = data.get("cwd")
    session_id = data.get("session_id")
    decision, message = check(tool_input, cwd=cwd, session_id=session_id)
    if decision == "block":
        logger.error("BLOCKED: %s", message)
        sys.exit(2)
    if decision == "warn":
        payload = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": message,
            }
        }
        sys.stdout.write(json.dumps(payload) + "\n")


if __name__ == "__main__":
    main()
