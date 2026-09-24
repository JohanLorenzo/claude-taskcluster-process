#!/usr/bin/env python3
"""Hook: route skills to subagents instead of running them in the main session.

Handles two events:
- PreToolUse (Skill): denies the call before the skill loads, unless the
  skill forks itself into a subagent or is on the reference-only allowlist.
- UserPromptExpansion: when a user types a /command that isn't safe to run
  inline, injects additionalContext telling Claude to delegate it. Never
  blocks the prompt.
"""

import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Reference-only skills that just load instructions into the orchestrator,
# rather than doing file/shell work themselves.
INLINE_SKILLS = {
    "workflow-authoring",
    "claude-api",
    "update-config",
    "keybindings-help",
    "loop",
    "fewer-permission-prompts",
}

_SKILLS_DIR = Path("~/.claude/skills").expanduser()

_DELEGATE_REASON = (
    "Skills run in subagents. Spawn a general-purpose subagent with the "
    "prompt: Invoke the Skill tool with skill={name} args={args}, then "
    "report the result."
)


def _is_exempt(data):
    return os.environ.get("CLAUDE_MAIN_SESSION_WORK") == "1" or bool(
        data.get("agent_id")
    )


def _is_forked_skill(name, skills_dir=_SKILLS_DIR):
    skill_md = skills_dir / name / "SKILL.md"
    if not skill_md.exists():
        return False
    return "context: fork" in skill_md.read_text()


def _is_inline_safe(name, skills_dir=_SKILLS_DIR):
    return name in INLINE_SKILLS or _is_forked_skill(name, skills_dir)


def check_skill(data, skills_dir=_SKILLS_DIR):
    if _is_exempt(data):
        return True, ""
    tool_input = data.get("tool_input", {})
    name = tool_input.get("skill", "")
    if _is_inline_safe(name, skills_dir):
        return True, ""
    args = tool_input.get("args", "")
    return False, _DELEGATE_REASON.format(name=name, args=args)


def check_prompt_expansion(data, skills_dir=_SKILLS_DIR):
    if _is_exempt(data):
        return None
    name = data.get("command_name", "")
    if not name or _is_inline_safe(name, skills_dir):
        return None
    args = data.get("command_args", "")
    return (
        f"The user invoked /{name}. Don't execute it in the main session. "
        f"Immediately spawn a general-purpose subagent to invoke it via the "
        f"Skill tool with skill={name} args={args}."
    )


def _handle_pre_tool_use(data):
    allowed, reason = check_skill(data)
    if not allowed:
        logger.error("BLOCKED: %s", reason)
        sys.exit(2)


def _handle_user_prompt_expansion(data):
    context = check_prompt_expansion(data)
    if context is None:
        return
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptExpansion",
            "additionalContext": context,
        }
    }
    sys.stdout.write(json.dumps(output) + "\n")


def main():
    logging.basicConfig(format="%(message)s")
    data = json.load(sys.stdin)
    event = data.get("hook_event_name", "")
    if event == "PreToolUse":
        _handle_pre_tool_use(data)
    elif event == "UserPromptExpansion":
        _handle_user_prompt_expansion(data)


if __name__ == "__main__":
    main()
