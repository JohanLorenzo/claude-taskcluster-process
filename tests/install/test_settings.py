import json
from unittest.mock import patch

import pytest

from install import settings


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


def test_hooks_config_resolves_relative_paths(tmp_path):
    config = {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [{"type": "command", "command": "hooks/block_no_verify.py"}],
            }
        ]
    }
    hooks_cfg_file = tmp_path / "hooks-config.json"
    _write_json(hooks_cfg_file, config)

    with (
        patch.object(settings, "REPO_ROOT", tmp_path),
        patch.object(settings, "HOOKS_CONFIG_FILE", hooks_cfg_file),
    ):
        result = settings.load_hooks_config()

    cmd = result["PreToolUse"][0]["hooks"][0]["command"]
    assert cmd == str(tmp_path / "hooks" / "block_no_verify.py")


def test_load_settings_missing_exits(tmp_path):
    missing = tmp_path / "settings.json"
    with patch.object(settings, "SETTINGS_FILE", missing), pytest.raises(SystemExit):
        settings.load_settings()


def test_load_settings_invalid_json_exits(tmp_path):
    bad = tmp_path / "settings.json"
    bad.write_text("not json")
    with patch.object(settings, "SETTINGS_FILE", bad), pytest.raises(SystemExit):
        settings.load_settings()


def test_load_settings_valid(tmp_path):
    settings_file = _make_settings(tmp_path)
    with patch.object(settings, "SETTINGS_FILE", settings_file):
        data = settings.load_settings()
    assert data["model"] == "opusplan"


def test_new_settings_replaces_hooks_only(tmp_path):
    settings_file = _make_settings(tmp_path)
    with patch.object(settings, "SETTINGS_FILE", settings_file):
        old = settings.load_settings()

    new_hooks = {"PreToolUse": [{"matcher": "Bash", "hooks": []}]}
    new = settings.compute_new_settings(old, new_hooks, repo_paths=[])

    assert new["hooks"] == new_hooks
    assert new["model"] == "opusplan"
    assert new["alwaysThinkingEnabled"] is True
    assert new["permissions"]["allow"] == []
    assert new["permissions"]["defaultMode"] == "plan"


def test_new_settings_adds_additional_directories(tmp_path):
    settings_file = _make_settings(tmp_path)
    with patch.object(settings, "SETTINGS_FILE", settings_file):
        old = settings.load_settings()

    repo_paths = ["/some/repo", "/other/repo"]
    new = settings.compute_new_settings(old, {}, repo_paths=repo_paths)

    assert new["permissions"]["additionalDirectories"] == repo_paths


def test_new_settings_preserves_other_permissions_keys(tmp_path):
    settings_file = _make_settings(
        tmp_path,
        extra={
            "permissions": {
                "allow": ["Bash(git:*)"],
                "deny": ["Bash(rm:*)"],
                "defaultMode": "plan",
            }
        },
    )
    with patch.object(settings, "SETTINGS_FILE", settings_file):
        old = settings.load_settings()

    new = settings.compute_new_settings(old, {}, repo_paths=["/p"])

    assert new["permissions"]["allow"] == ["Bash(git:*)"]
    assert new["permissions"]["deny"] == ["Bash(rm:*)"]
    assert new["permissions"]["defaultMode"] == "plan"
    assert new["permissions"]["additionalDirectories"] == ["/p"]


def test_load_permissions_config_generates_patterns(tmp_path):
    cfg = tmp_path / "permissions-config.json"
    cfg.write_text(
        '{"static": ["Bash(git rebase:*)"], "taskcluster_instances": ["https://tc.example.com"]}'
    )
    with patch.object(settings, "PERMISSIONS_CONFIG_FILE", cfg):
        result = settings.load_permissions_config()
    assert "Bash(git rebase:*)" in result
    for cmd in (
        "taskcluster task status",
        "taskcluster task log",
        "taskcluster task def",
        "taskcluster group status",
        "taskcluster group list",
    ):
        assert f"Bash(TASKCLUSTER_ROOT_URL=https://tc.example.com {cmd}:*)" in result
    for cmd in ("taskcluster task status", "taskcluster group status"):
        assert (
            f"Bash(until TASKCLUSTER_ROOT_URL=https://tc.example.com {cmd}:*)" in result
        )


def test_load_permissions_config_generates_uv_taskgraph_rules(tmp_path):
    cfg = tmp_path / "permissions-config.json"
    cfg.write_text('{"uv_taskgraph_extras": ["", "load-image"]}')
    with patch.object(settings, "PERMISSIONS_CONFIG_FILE", cfg):
        result = settings.load_permissions_config(taskgraph_repo="/path/to/taskgraph")
    assert "Bash(uv run --with-editable '/path/to/taskgraph' taskgraph:*)" in result
    assert (
        "Bash(uv run --with-editable '/path/to/taskgraph[load-image]' taskgraph:*)"
        in result
    )


def test_load_permissions_config_no_uv_rules_without_taskgraph_repo(tmp_path):
    cfg = tmp_path / "permissions-config.json"
    cfg.write_text('{"uv_taskgraph_extras": ["", "load-image"]}')
    with patch.object(settings, "PERMISSIONS_CONFIG_FILE", cfg):
        result = settings.load_permissions_config()
    assert not any("uv run --with-editable" in r for r in result)


def test_load_permissions_config_generates_skill_script_rules(tmp_path):
    cfg = tmp_path / "permissions-config.json"
    cfg.write_text("{}")
    fake_skills_dir = tmp_path / "skills"
    with (
        patch.object(settings, "PERMISSIONS_CONFIG_FILE", cfg),
        patch.object(settings, "SKILLS_DIR", fake_skills_dir),
    ):
        result = settings.load_permissions_config()
    for skill, script in [
        ("taskcluster-monitor-group", "taskcluster_monitor_group.py"),
        ("taskcluster-submit-task", "taskcluster_submit_task.py"),
    ]:
        expected = f"Bash(uv run {fake_skills_dir}/{skill}/scripts/{script}:*)"
        assert expected in result


def test_load_permissions_config_generates_git_c_rules(tmp_path):
    cfg = tmp_path / "permissions-config.json"
    cfg.write_text('{"git_c_operations": ["add", "commit"]}')
    with patch.object(settings, "PERMISSIONS_CONFIG_FILE", cfg):
        result = settings.load_permissions_config(repo_paths=["/a/repo", "/b/repo"])
    assert "Bash(git -C /a/repo add:*)" in result
    assert "Bash(git -C /a/repo commit:*)" in result
    assert "Bash(git -C /b/repo add:*)" in result
    assert "Bash(git -C /b/repo commit:*)" in result


def test_load_permissions_config_no_git_c_without_repos(tmp_path):
    cfg = tmp_path / "permissions-config.json"
    cfg.write_text('{"git_c_operations": ["add", "commit"]}')
    with patch.object(settings, "PERMISSIONS_CONFIG_FILE", cfg):
        result = settings.load_permissions_config()
    assert not any("git -C" in r for r in result)


def test_load_permissions_config_missing_returns_empty(tmp_path):
    with patch.object(settings, "PERMISSIONS_CONFIG_FILE", tmp_path / "missing.json"):
        assert settings.load_permissions_config() == []


def test_new_settings_adds_managed_allow_rules(tmp_path):
    settings_file = _make_settings(
        tmp_path,
        extra={
            "permissions": {
                "allow": ["Bash(git log:*)", "Bash(ls:*)"],
                "defaultMode": "plan",
            }
        },
    )
    with patch.object(settings, "SETTINGS_FILE", settings_file):
        old = settings.load_settings()

    managed = ["Bash(taskcluster task status:*)", "Bash(git diff:*)"]
    new = settings.compute_new_settings(old, {}, repo_paths=[], managed_allow=managed)

    assert new["permissions"]["allow"] == [
        "Bash(git diff:*)",
        "Bash(git log:*)",
        "Bash(ls:*)",
        "Bash(taskcluster task status:*)",
    ]


def test_new_settings_managed_allow_deduplicates(tmp_path):
    settings_file = _make_settings(
        tmp_path,
        extra={
            "permissions": {
                "allow": ["Bash(git log:*)", "Bash(taskcluster task status:*)"],
                "defaultMode": "plan",
            }
        },
    )
    with patch.object(settings, "SETTINGS_FILE", settings_file):
        old = settings.load_settings()

    managed = ["Bash(taskcluster task status:*)"]
    new = settings.compute_new_settings(old, {}, repo_paths=[], managed_allow=managed)

    assert new["permissions"]["allow"] == [
        "Bash(git log:*)",
        "Bash(taskcluster task status:*)",
    ]


def test_new_settings_managed_allow_empty_by_default(tmp_path):
    settings_file = _make_settings(
        tmp_path,
        extra={"permissions": {"allow": ["Bash(git log:*)"], "defaultMode": "plan"}},
    )
    with patch.object(settings, "SETTINGS_FILE", settings_file):
        old = settings.load_settings()

    new = settings.compute_new_settings(old, {}, repo_paths=[])

    assert new["permissions"]["allow"] == ["Bash(git log:*)"]


def test_settings_diff_shows_unified_diff(tmp_path):
    old = {"key": "old_value"}
    new = {"key": "new_value"}
    with patch.object(settings, "SETTINGS_FILE", tmp_path / "settings.json"):
        diff = settings.settings_diff(old, new)
    assert any("-" in line for line in diff)
    assert any("+" in line for line in diff)


def test_settings_diff_empty_when_identical(tmp_path):
    data = {"key": "value"}
    with patch.object(settings, "SETTINGS_FILE", tmp_path / "settings.json"):
        diff = settings.settings_diff(data, data)
    assert diff == []
