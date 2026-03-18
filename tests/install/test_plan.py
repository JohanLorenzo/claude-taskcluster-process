import json
import logging
from unittest.mock import patch

import pytest

import install
from install import local_config, preflight, settings, symlinks
from install import plan as install_plan
from install.plan import Plan
from install.tools import check_tools


def _write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def _make_settings(tmp_path, extra=None):
    data = {
        "alwaysThinkingEnabled": True,
        "model": "opusplan",
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "~/.claude/hooks/old.sh"}],
                }
            ]
        },
        "permissions": {"allow": [], "defaultMode": "plan"},
    }
    if extra:
        data.update(extra)
    settings_file = tmp_path / "settings.json"
    _write_json(settings_file, data)
    return settings_file


def test_plan_has_changes_true_when_diff():
    plan = Plan(
        local_config_diff=["-old\n", "+new\n"],
        new_local_content="new",
        settings_diff=[],
        new_settings={},
        symlink_ops=[],
        actionable_ops=[],
    )
    assert plan.has_changes


def test_plan_has_changes_false_when_empty():
    plan = Plan(
        local_config_diff=[],
        new_local_content=None,
        settings_diff=[],
        new_settings={},
        symlink_ops=[],
        actionable_ops=[],
    )
    assert not plan.has_changes


def test_plan_has_changes_true_when_actionable_ops(tmp_path):
    src = tmp_path / "foo.md"
    src.write_text("x")
    target = tmp_path / "link.md"
    plan = Plan(
        local_config_diff=[],
        new_local_content=None,
        settings_diff=[],
        new_settings={},
        symlink_ops=[("create", src, target)],
        actionable_ops=[("create", src, target)],
    )
    assert plan.has_changes


def test_preview_changes_prints_no_change_when_up_to_date(caplog, tmp_path):

    plan = Plan(
        local_config_diff=[],
        new_local_content=None,
        settings_diff=[],
        new_settings={},
        symlink_ops=[],
        actionable_ops=[],
    )
    with (
        caplog.at_level(logging.INFO),
        patch.object(install_plan, "LOCAL_CONFIG_FILE", tmp_path / "CLAUDE.local.md"),
        patch.object(install_plan, "SETTINGS_FILE", tmp_path / "settings.json"),
    ):
        install_plan.preview_changes(plan)
    assert "no change" in caplog.text


def test_preview_changes_prints_warnings(caplog, tmp_path):

    plan = Plan(
        local_config_diff=[],
        new_local_content=None,
        settings_diff=[],
        new_settings={},
        symlink_ops=[],
        actionable_ops=[],
        warnings=["WARNING: something"],
    )
    with (
        caplog.at_level(logging.INFO),
        patch.object(install_plan, "LOCAL_CONFIG_FILE", tmp_path / "CLAUDE.local.md"),
        patch.object(install_plan, "SETTINGS_FILE", tmp_path / "settings.json"),
    ):
        install_plan.preview_changes(plan)
    assert "WARNING: something" in caplog.text


def test_write_files_writes_settings(tmp_path):
    settings_file = _make_settings(tmp_path)
    new_settings = {"model": "updated"}
    plan = Plan(
        local_config_diff=[],
        new_local_content=None,
        settings_diff=[],
        new_settings=new_settings,
        symlink_ops=[],
        actionable_ops=[],
    )
    with patch.object(install_plan, "SETTINGS_FILE", settings_file):
        install_plan.write_files(plan)
    assert json.loads(settings_file.read_text()) == new_settings


def test_write_files_writes_local_config_when_diff(tmp_path):
    settings_file = _make_settings(tmp_path)
    local_config_file = tmp_path / "CLAUDE.local.md"
    plan = Plan(
        local_config_diff=["-old\n", "+new\n"],
        new_local_content="new content",
        settings_diff=[],
        new_settings={"model": "x"},
        symlink_ops=[],
        actionable_ops=[],
    )
    with (
        patch.object(install_plan, "LOCAL_CONFIG_FILE", local_config_file),
        patch.object(install_plan, "SETTINGS_FILE", settings_file),
    ):
        install_plan.write_files(plan)
    assert local_config_file.read_text() == "new content"


def test_write_files_skips_local_config_when_no_diff(tmp_path):
    settings_file = _make_settings(tmp_path)
    local_config_file = tmp_path / "CLAUDE.local.md"
    plan = Plan(
        local_config_diff=[],
        new_local_content=None,
        settings_diff=[],
        new_settings={"model": "x"},
        symlink_ops=[],
        actionable_ops=[],
    )
    with (
        patch.object(install_plan, "LOCAL_CONFIG_FILE", local_config_file),
        patch.object(install_plan, "SETTINGS_FILE", settings_file),
    ):
        install_plan.write_files(plan)
    assert not local_config_file.exists()


def test_apply_symlink_op_create(tmp_path):
    src = tmp_path / "src.md"
    src.write_text("x")
    target = tmp_path / "link.md"
    install_plan.apply_symlink_op(("create", src, target))
    assert target.is_symlink()
    assert target.resolve() == src.resolve()


def test_apply_symlink_op_update_replaces_existing_symlink(tmp_path):
    src = tmp_path / "new.md"
    src.write_text("new")
    old = tmp_path / "old.md"
    old.write_text("old")
    target = tmp_path / "link.md"
    target.symlink_to(old)
    install_plan.apply_symlink_op(("update", src, target))
    assert target.resolve() == src.resolve()


def test_apply_symlink_op_replace_file(tmp_path):
    src = tmp_path / "src.md"
    src.write_text("new")
    target = tmp_path / "target.md"
    target.write_text("old")
    install_plan.apply_symlink_op(("replace_file", src, target))
    assert target.is_symlink()
    assert target.resolve() == src.resolve()


def test_apply_changes_orchestrates_all_steps(tmp_path):
    settings_file = _make_settings(tmp_path)
    md = tmp_path / "rules" / "foo.md"
    md.parent.mkdir()
    md.write_text("x")
    rules_target = tmp_path / "claude_rules"
    rules_target.mkdir()
    link = rules_target / "foo.md"
    plan = Plan(
        local_config_diff=[],
        new_local_content=None,
        settings_diff=[],
        new_settings={"model": "updated"},
        symlink_ops=[("create", md, link)],
        actionable_ops=[("create", md, link)],
    )
    with (
        patch.object(install_plan, "SETTINGS_FILE", settings_file),
        patch.object(install_plan, "RULES_DIR", rules_target),
    ):
        install_plan.apply_changes(plan)
    assert json.loads(settings_file.read_text()) == {"model": "updated"}
    assert link.is_symlink()


def test_check_tools_all_present():
    with patch("shutil.which", return_value="/usr/bin/something"):
        check_tools()


def test_check_tools_required_missing_exits():
    def fake_which(tool):
        return None if tool == "git" else "/usr/bin/" + tool

    with patch("shutil.which", side_effect=fake_which), pytest.raises(SystemExit):
        check_tools()


def test_check_tools_optional_missing_continues(caplog):
    def fake_which(tool):
        return None if tool == "cargo" else "/usr/bin/" + tool

    with (
        caplog.at_level(logging.WARNING),
        patch("shutil.which", side_effect=fake_which),
    ):
        check_tools()

    assert "cargo" in caplog.text


def test_main_exits_without_prompt_when_no_changes(tmp_path, caplog):

    hooks_cfg = tmp_path / "hooks-config.json"
    _write_json(hooks_cfg, {"PreToolUse": [], "PostToolUse": []})
    tg = tmp_path / "taskcluster" / "taskgraph"
    tg.mkdir(parents=True)
    mtg = tmp_path / "mozilla-releng" / "mozilla-taskgraph"
    mtg.mkdir(parents=True)
    fxci = tmp_path / "mozilla-releng" / "fxci-config"
    fxci.mkdir(parents=True)
    (fxci / "projects.yml").write_text("")
    tc = tmp_path / "taskcluster" / "taskcluster"
    tc.mkdir(parents=True)
    local_config_file = tmp_path / "CLAUDE.local.md"
    repos = [
        {"name": "taskcluster/taskgraph", "path": str(tg)},
        {"name": "mozilla-releng/mozilla-taskgraph", "path": str(mtg)},
        {"name": "mozilla-releng/fxci-config", "path": str(fxci)},
        {"name": "taskcluster/taskcluster", "path": str(tc)},
    ]
    local_config_file.write_text(
        local_config.render_local_config(tg, mtg, fxci, tc, repos)
    )
    repo_paths = [str(tmp_path), str(tg), str(mtg), str(fxci), str(tc)]
    worktree_rules = sorted(
        f"Bash(git -C {p}/.claude/worktrees/:*)" for p in repo_paths
    )
    settings_file = _make_settings(
        tmp_path,
        extra={
            "hooks": {"PreToolUse": [], "PostToolUse": []},
            "permissions": {
                "allow": worktree_rules,
                "defaultMode": "plan",
                "additionalDirectories": repo_paths,
            },
        },
    )
    rules_src = tmp_path / "rules"
    rules_src.mkdir()
    rules_target = tmp_path / "claude_rules"
    rules_target.mkdir()

    empty_perms = tmp_path / "permissions-config.json"
    empty_perms.write_text("{}")
    with (
        caplog.at_level(logging.INFO),
        patch.object(settings, "SETTINGS_FILE", settings_file),
        patch.object(settings, "HOOKS_CONFIG_FILE", hooks_cfg),
        patch.object(settings, "PERMISSIONS_CONFIG_FILE", empty_perms),
        patch.object(settings, "REPO_ROOT", tmp_path),
        patch.object(local_config, "LOCAL_CONFIG_FILE", local_config_file),
        patch.object(symlinks, "REPO_ROOT", tmp_path),
        patch.object(symlinks, "RULES_DIR", rules_target),
        patch.object(preflight, "RULES_DIR", rules_target),
        patch.object(preflight, "SETTINGS_FILE", settings_file),
        patch.object(preflight, "CLAUDE_DIR", tmp_path),
        patch.object(install_plan, "REPO_ROOT", tmp_path),
        patch.object(install, "LOCAL_CONFIG_FILE", local_config_file),
        # First input: search root prompt. Second input: should never be reached.
        patch(
            "builtins.input",
            side_effect=[str(tmp_path), AssertionError("should not prompt for apply")],
        ),
        pytest.raises(SystemExit) as exc,
    ):
        install.main()

    assert exc.value.code == 0
    assert "up to date" in caplog.text
