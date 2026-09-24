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


def test_load_permissions_config_returns_static_rules(tmp_path):
    cfg = tmp_path / "permissions-config.json"
    cfg.write_text('{"static": ["Bash(git rebase:*)", "mcp__moz__get_bugzilla_bug"]}')
    with patch.object(settings, "PERMISSIONS_CONFIG_FILE", cfg):
        result = settings.load_permissions_config()
    assert result == ["Bash(git rebase:*)", "mcp__moz__get_bugzilla_bug"]


def test_load_permissions_config_missing_returns_empty(tmp_path):
    with patch.object(settings, "PERMISSIONS_CONFIG_FILE", tmp_path / "missing.json"):
        assert settings.load_permissions_config() == []


def test_load_permissions_deny_returns_configured_rules(tmp_path):
    cfg = tmp_path / "permissions-config.json"
    cfg.write_text('{"deny": ["Read(~/.config/taskcluster.yml)"]}')
    with patch.object(settings, "PERMISSIONS_CONFIG_FILE", cfg):
        result = settings.load_permissions_deny()
    assert result == ["Read(~/.config/taskcluster.yml)"]


def test_load_permissions_deny_missing_returns_empty(tmp_path):
    with patch.object(settings, "PERMISSIONS_CONFIG_FILE", tmp_path / "missing.json"):
        assert settings.load_permissions_deny() == []


def test_load_permissions_deny_absent_key_returns_empty(tmp_path):
    cfg = tmp_path / "permissions-config.json"
    cfg.write_text("{}")
    with patch.object(settings, "PERMISSIONS_CONFIG_FILE", cfg):
        assert settings.load_permissions_deny() == []


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
    new = settings.compute_new_settings(
        old, {}, repo_paths=[], managed={"allow": managed}
    )

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
    new = settings.compute_new_settings(
        old, {}, repo_paths=[], managed={"allow": managed}
    )

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


def test_new_settings_adds_managed_deny_rules(tmp_path):
    settings_file = _make_settings(
        tmp_path,
        extra={
            "permissions": {
                "allow": [],
                "deny": ["Bash(timeout:*)"],
                "defaultMode": "plan",
            }
        },
    )
    with patch.object(settings, "SETTINGS_FILE", settings_file):
        old = settings.load_settings()

    managed_deny = [
        "Read(~/.config/taskcluster.yml)",
        "Edit(~/.config/taskcluster.yml)",
    ]
    new = settings.compute_new_settings(
        old, {}, repo_paths=[], managed={"deny": managed_deny}
    )

    assert new["permissions"]["deny"] == sorted({"Bash(timeout:*)", *managed_deny})


def test_new_settings_managed_deny_deduplicates(tmp_path):
    settings_file = _make_settings(
        tmp_path,
        extra={
            "permissions": {
                "allow": [],
                "deny": ["Read(~/.config/taskcluster.yml)"],
                "defaultMode": "plan",
            }
        },
    )
    with patch.object(settings, "SETTINGS_FILE", settings_file):
        old = settings.load_settings()

    new = settings.compute_new_settings(
        old, {}, repo_paths=[], managed={"deny": ["Read(~/.config/taskcluster.yml)"]}
    )

    assert new["permissions"]["deny"] == ["Read(~/.config/taskcluster.yml)"]


def test_new_settings_managed_deny_empty_by_default(tmp_path):
    settings_file = _make_settings(
        tmp_path,
        extra={
            "permissions": {
                "allow": [],
                "deny": ["Bash(timeout:*)"],
                "defaultMode": "plan",
            }
        },
    )
    with patch.object(settings, "SETTINGS_FILE", settings_file):
        old = settings.load_settings()

    new = settings.compute_new_settings(old, {}, repo_paths=[])

    assert new["permissions"]["deny"] == ["Bash(timeout:*)"]


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


def _write_sandbox_config(path, extra=None):
    data = {
        "sandbox": {
            "enabled": True,
            "excludedCommands": ["docker"],
            "filesystem": {
                "allowWrite": ["~/.cache"],
                "denyWrite": ["~/.ssh"],
            },
            "network": {"allowLocalBinding": True},
        }
    }
    if extra:
        data.update(extra)
    path.write_text(json.dumps(data, indent=2))
    return path


def test_load_sandbox_config_prepends_repo_paths(tmp_path):
    cfg = _write_sandbox_config(tmp_path / "sandbox-config.json")
    with patch.object(settings, "SANDBOX_CONFIG_FILE", cfg):
        result = settings.load_sandbox_config(repo_paths=["/a/repo", "/b/repo"])
    assert result["filesystem"]["allowWrite"] == ["/a/repo", "/b/repo", "~/.cache"]


def test_load_sandbox_config_preserves_other_keys(tmp_path):
    cfg = _write_sandbox_config(tmp_path / "sandbox-config.json")
    with patch.object(settings, "SANDBOX_CONFIG_FILE", cfg):
        result = settings.load_sandbox_config(repo_paths=[])
    assert result["enabled"] is True
    assert result["excludedCommands"] == ["docker"]
    assert result["filesystem"]["denyWrite"] == ["~/.ssh"]
    assert result["network"]["allowLocalBinding"] is True


def test_load_sandbox_config_missing_returns_none(tmp_path):
    with patch.object(settings, "SANDBOX_CONFIG_FILE", tmp_path / "missing.json"):
        assert settings.load_sandbox_config() is None


def test_new_settings_adds_sandbox(tmp_path):
    settings_file = _make_settings(tmp_path)
    with patch.object(settings, "SETTINGS_FILE", settings_file):
        old = settings.load_settings()
    sandbox = {"enabled": True, "excludedCommands": ["docker"]}
    new = settings.compute_new_settings(
        old, {}, repo_paths=[], overrides={"sandbox": sandbox}
    )
    assert new["sandbox"] == sandbox


def test_new_settings_no_sandbox_by_default(tmp_path):
    settings_file = _make_settings(tmp_path)
    with patch.object(settings, "SETTINGS_FILE", settings_file):
        old = settings.load_settings()
    new = settings.compute_new_settings(old, {}, repo_paths=[])
    assert "sandbox" not in new


def test_load_static_settings_returns_configured_keys(tmp_path):
    cfg = tmp_path / "settings-config.json"
    _write_json(cfg, {"attribution": {"commit": "", "pr": "", "sessionUrl": False}})
    with patch.object(settings, "SETTINGS_CONFIG_FILE", cfg):
        result = settings.load_static_settings()
    assert result == {"attribution": {"commit": "", "pr": "", "sessionUrl": False}}


def test_load_static_settings_missing_returns_empty(tmp_path):
    with patch.object(settings, "SETTINGS_CONFIG_FILE", tmp_path / "missing.json"):
        assert settings.load_static_settings() == {}


def test_new_settings_applies_static_keys(tmp_path):
    settings_file = _make_settings(tmp_path)
    with patch.object(settings, "SETTINGS_FILE", settings_file):
        old = settings.load_settings()

    static = {"attribution": {"commit": "", "pr": "", "sessionUrl": False}}
    new = settings.compute_new_settings(old, {}, repo_paths=[], overrides=static)

    assert new["attribution"] == static["attribution"]
    assert new["model"] == "opusplan"


def test_new_settings_no_static_keys_by_default(tmp_path):
    settings_file = _make_settings(tmp_path)
    with patch.object(settings, "SETTINGS_FILE", settings_file):
        old = settings.load_settings()
    new = settings.compute_new_settings(old, {}, repo_paths=[])
    assert "attribution" not in new


def test_new_settings_static_overrides_existing_key(tmp_path):
    settings_file = _make_settings(tmp_path, extra={"attribution": {"commit": "old"}})
    with patch.object(settings, "SETTINGS_FILE", settings_file):
        old = settings.load_settings()

    static = {"attribution": {"commit": "", "pr": "", "sessionUrl": False}}
    new = settings.compute_new_settings(old, {}, repo_paths=[], overrides=static)

    assert new["attribution"] == static["attribution"]
