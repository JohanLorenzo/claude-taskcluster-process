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
