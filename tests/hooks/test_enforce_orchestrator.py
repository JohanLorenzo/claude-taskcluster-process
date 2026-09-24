import os
from pathlib import Path
from unittest.mock import patch

from hooks.enforce_orchestrator import check


def test_subagent_bash_allowed():
    assert check({"agent_id": "abc", "tool_name": "Bash", "tool_input": {}}) == (
        True,
        "",
    )


def test_main_session_bash_blocked():
    allowed, reason = check({"tool_name": "Bash", "tool_input": {"command": "ls"}})
    assert not allowed
    assert "subagent" in reason.lower()


def test_main_session_notebook_edit_blocked():
    allowed, _ = check({"tool_name": "NotebookEdit", "tool_input": {}})
    assert not allowed


def test_plan_file_write_allowed():
    file_path = str(Path("~/.claude/plans/my-plan.md").expanduser())
    allowed, _ = check({"tool_name": "Write", "tool_input": {"file_path": file_path}})
    assert allowed


def test_memory_file_write_allowed():
    file_path = str(
        Path("~/.claude/projects/-some-project/memory/fact.md").expanduser()
    )
    allowed, _ = check({"tool_name": "Write", "tool_input": {"file_path": file_path}})
    assert allowed


def test_repo_file_edit_blocked():
    allowed, reason = check(
        {"tool_name": "Edit", "tool_input": {"file_path": "/repo/foo.py"}}
    )
    assert not allowed
    assert reason


def test_fork_blocked():
    allowed, reason = check(
        {"tool_name": "Agent", "tool_input": {"subagent_type": "fork"}}
    )
    assert not allowed
    assert "fork" in reason.lower()


def test_agent_opus_model_blocked():
    allowed, _ = check(
        {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "general-purpose", "model": "opus"},
        }
    )
    assert not allowed


def test_agent_fable_model_blocked():
    allowed, _ = check(
        {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "general-purpose", "model": "fable"},
        }
    )
    assert not allowed


def test_agent_general_purpose_no_model_allowed():
    assert check(
        {"tool_name": "Agent", "tool_input": {"subagent_type": "general-purpose"}}
    ) == (True, "")


def test_agent_sonnet_model_allowed():
    assert check(
        {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "general-purpose", "model": "sonnet"},
        }
    ) == (True, "")


def test_read_allowed():
    data = {"tool_name": "Read", "tool_input": {"file_path": "/repo/foo.py"}}
    assert check(data) == (True, "")


def test_env_escape_hatch_allows_bash():
    with patch.dict(os.environ, {"CLAUDE_MAIN_SESSION_WORK": "1"}):
        assert check({"tool_name": "Bash", "tool_input": {"command": "ls"}}) == (
            True,
            "",
        )
