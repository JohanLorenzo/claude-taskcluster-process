#!/usr/bin/env python3
"""Hook: block the main session from doing implementation work directly.

Bash, Edit, Write and NotebookEdit must be delegated to a subagent. Calls made
from inside a subagent (data has agent_id) are always allowed. Set
CLAUDE_MAIN_SESSION_WORK=1 to bypass this hook for one session.
"""

import fnmatch
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_ALLOWED_EDIT_PATTERNS = [
    str(Path("~/.claude/plans/*").expanduser()),
    str(Path("~/.claude/projects/*/memory/*").expanduser()),
]

_DELEGATE_REASON = (
    "Main session is orchestrator-only. Hand this off to a general-purpose "
    "subagent. If you're running a skill, spawn a general-purpose subagent "
    "with the prompt: Invoke the Skill tool with skill=<name> args=<args>, "
    "then report the result."
)


def _is_exempt(data):
    return os.environ.get("CLAUDE_MAIN_SESSION_WORK") == "1" or bool(
        data.get("agent_id")
    )


def _is_allowed_edit_path(file_path):
    if not file_path:
        return False
    resolved = str(Path(file_path).expanduser())
    return any(fnmatch.fnmatch(resolved, pattern) for pattern in _ALLOWED_EDIT_PATTERNS)


def _check_edit(tool_input):
    if _is_allowed_edit_path(tool_input.get("file_path")):
        return True, ""
    return False, _DELEGATE_REASON


def _check_agent(tool_input):
    if tool_input.get("subagent_type") == "fork":
        return False, "fork runs on the main model. Use a general-purpose subagent."
    model = tool_input.get("model")
    if model in ("opus", "fable"):
        reason = f"Subagents must not run on {model}. Use sonnet or omit model."
        return False, reason
    return True, ""


def check(data):
    if _is_exempt(data):
        return True, ""

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool_name in ("Bash", "NotebookEdit"):
        return False, _DELEGATE_REASON
    if tool_name in ("Edit", "Write"):
        return _check_edit(tool_input)
    if tool_name == "Agent":
        return _check_agent(tool_input)
    return True, ""


def main():
    logging.basicConfig(format="%(message)s")
    data = json.load(sys.stdin)
    allowed, reason = check(data)
    if not allowed:
        logger.error("BLOCKED: %s", reason)
        sys.exit(2)


if __name__ == "__main__":
    main()
