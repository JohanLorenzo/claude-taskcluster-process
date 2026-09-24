import os
from unittest.mock import patch

from hooks.route_skills_to_subagents import check_prompt_expansion, check_skill


def _write_skill(skills_dir, name, frontmatter_extra=""):
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\n{frontmatter_extra}---\n")


def test_subagent_skill_call_allowed(tmp_path):
    data = {"agent_id": "abc", "tool_input": {"skill": "mozdata:probe-discovery"}}
    assert check_skill(data, skills_dir=tmp_path) == (True, "")


def test_forked_skill_allowed(tmp_path):
    _write_skill(tmp_path, "review-taskgraph", "context: fork\n")
    data = {"tool_input": {"skill": "review-taskgraph", "args": "HEAD~1..HEAD"}}
    assert check_skill(data, skills_dir=tmp_path) == (True, "")


def test_inline_allowlisted_skill_allowed(tmp_path):
    data = {"tool_input": {"skill": "workflow-authoring", "args": ""}}
    assert check_skill(data, skills_dir=tmp_path) == (True, "")


def test_plugin_skill_denied_with_name_and_args(tmp_path):
    data = {
        "tool_input": {"skill": "mozdata:probe-discovery", "args": "search caribou"}
    }
    allowed, reason = check_skill(data, skills_dir=tmp_path)
    assert not allowed
    assert "mozdata:probe-discovery" in reason
    assert "search caribou" in reason


def test_non_forked_repo_skill_denied(tmp_path):
    _write_skill(tmp_path, "git-origin")
    data = {"tool_input": {"skill": "git-origin", "args": ""}}
    allowed, _ = check_skill(data, skills_dir=tmp_path)
    assert not allowed


def test_env_escape_hatch_allows_skill(tmp_path):
    with patch.dict(os.environ, {"CLAUDE_MAIN_SESSION_WORK": "1"}):
        data = {"tool_input": {"skill": "mozdata:probe-discovery"}}
        assert check_skill(data, skills_dir=tmp_path) == (True, "")


def test_prompt_expansion_for_plugin_skill_emits_context(tmp_path):
    data = {
        "command_name": "simplify",
        "command_args": "",
        "command_source": "plugin",
        "prompt": "/simplify",
    }
    context = check_prompt_expansion(data, skills_dir=tmp_path)
    assert context is not None
    assert "simplify" in context
    assert "subagent" in context.lower()


def test_prompt_expansion_for_forked_skill_returns_none(tmp_path):
    _write_skill(tmp_path, "review-taskgraph", "context: fork\n")
    data = {"command_name": "review-taskgraph", "command_args": "HEAD~1..HEAD"}
    assert check_prompt_expansion(data, skills_dir=tmp_path) is None


def test_prompt_expansion_for_inline_skill_returns_none(tmp_path):
    data = {"command_name": "loop", "command_args": "5m /foo"}
    assert check_prompt_expansion(data, skills_dir=tmp_path) is None


def test_prompt_expansion_for_non_command_prompt_returns_none(tmp_path):
    data = {"command_name": "", "prompt": "please run git status"}
    assert check_prompt_expansion(data, skills_dir=tmp_path) is None


def test_prompt_expansion_env_escape_hatch(tmp_path):
    with patch.dict(os.environ, {"CLAUDE_MAIN_SESSION_WORK": "1"}):
        data = {"command_name": "simplify", "command_args": ""}
        assert check_prompt_expansion(data, skills_dir=tmp_path) is None
