"""Tests for install.py logic (no real ~/.claude/ touched)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import install as inst

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# _load_hooks_config: path resolution
# ---------------------------------------------------------------------------


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
        patch.object(inst, "REPO_ROOT", tmp_path),
        patch.object(inst, "HOOKS_CONFIG_FILE", hooks_cfg_file),
    ):
        result = inst._load_hooks_config()

    cmd = result["PreToolUse"][0]["hooks"][0]["command"]
    assert Path(cmd).is_absolute()
    assert cmd == str(tmp_path / "hooks" / "block_no_verify.py")


# ---------------------------------------------------------------------------
# _load_settings
# ---------------------------------------------------------------------------


def test_load_settings_missing_exits(tmp_path):
    missing = tmp_path / "settings.json"
    with patch.object(inst, "SETTINGS_FILE", missing), pytest.raises(SystemExit):
        inst._load_settings()


def test_load_settings_invalid_json_exits(tmp_path):
    bad = tmp_path / "settings.json"
    bad.write_text("not json")
    with patch.object(inst, "SETTINGS_FILE", bad), pytest.raises(SystemExit):
        inst._load_settings()


def test_load_settings_valid(tmp_path):
    settings_file = _make_settings(tmp_path)
    with patch.object(inst, "SETTINGS_FILE", settings_file):
        data = inst._load_settings()
    assert data["model"] == "opusplan"


# ---------------------------------------------------------------------------
# _compute_new_settings: hooks replacement + key preservation
# ---------------------------------------------------------------------------


def test_new_settings_replaces_hooks_only(tmp_path):
    settings_file = _make_settings(tmp_path)
    with patch.object(inst, "SETTINGS_FILE", settings_file):
        old = inst._load_settings()

    new_hooks = {"PreToolUse": [{"matcher": "Bash", "hooks": []}]}
    with patch.object(inst, "_read_local_config_repos", return_value=[]):
        new = inst._compute_new_settings(old, new_hooks)

    assert new["hooks"] == new_hooks
    assert new["model"] == "opusplan"
    assert new["alwaysThinkingEnabled"] is True
    assert new["permissions"]["allow"] == []
    assert new["permissions"]["defaultMode"] == "plan"


def test_new_settings_adds_additional_directories(tmp_path):
    settings_file = _make_settings(tmp_path)
    with patch.object(inst, "SETTINGS_FILE", settings_file):
        old = inst._load_settings()

    repo_paths = ["/some/repo", "/other/repo"]
    with patch.object(inst, "_read_local_config_repos", return_value=repo_paths):
        new = inst._compute_new_settings(old, {})

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
    with patch.object(inst, "SETTINGS_FILE", settings_file):
        old = inst._load_settings()

    with patch.object(inst, "_read_local_config_repos", return_value=["/p"]):
        new = inst._compute_new_settings(old, {})

    assert new["permissions"]["allow"] == ["Bash(git:*)"]
    assert new["permissions"]["deny"] == ["Bash(rm:*)"]
    assert new["permissions"]["defaultMode"] == "plan"
    assert new["permissions"]["additionalDirectories"] == ["/p"]


# ---------------------------------------------------------------------------
# _settings_diff
# ---------------------------------------------------------------------------


def test_settings_diff_shows_unified_diff(tmp_path):
    old = {"key": "old_value"}
    new = {"key": "new_value"}
    with patch.object(inst, "SETTINGS_FILE", tmp_path / "settings.json"):
        diff = inst._settings_diff(old, new)
    assert any("-" in line for line in diff)
    assert any("+" in line for line in diff)


def test_settings_diff_empty_when_identical(tmp_path):
    data = {"key": "value"}
    with patch.object(inst, "SETTINGS_FILE", tmp_path / "settings.json"):
        diff = inst._settings_diff(data, data)
    assert diff == []


# ---------------------------------------------------------------------------
# _compute_symlink_ops
# ---------------------------------------------------------------------------


def test_symlink_ops_new_symlink(tmp_path):
    rules_src = tmp_path / "rules"
    rules_src.mkdir()
    (rules_src / "coding-preferences.md").write_text("# test\n")
    rules_target = tmp_path / "claude_rules"
    rules_target.mkdir()

    with (
        patch.object(inst, "REPO_ROOT", tmp_path),
        patch.object(inst, "RULES_DIR", rules_target),
    ):
        ops = inst._compute_symlink_ops()

    assert len(ops) == 1
    op = ops[0]
    assert op[0] == "create"
    assert op[2] == rules_target / "coding-preferences.md"


def test_symlink_ops_already_correct(tmp_path):
    rules_src = tmp_path / "rules"
    rules_src.mkdir()
    md = rules_src / "coding-preferences.md"
    md.write_text("# test\n")
    rules_target = tmp_path / "claude_rules"
    rules_target.mkdir()
    link = rules_target / "coding-preferences.md"
    link.symlink_to(md)

    with (
        patch.object(inst, "REPO_ROOT", tmp_path),
        patch.object(inst, "RULES_DIR", rules_target),
    ):
        ops = inst._compute_symlink_ops()

    assert ops[0][0] == "noop"


def test_symlink_ops_update_symlink(tmp_path):
    rules_src = tmp_path / "rules"
    rules_src.mkdir()
    md = rules_src / "coding-preferences.md"
    md.write_text("# new\n")
    other = tmp_path / "other.md"
    other.write_text("# old\n")
    rules_target = tmp_path / "claude_rules"
    rules_target.mkdir()
    link = rules_target / "coding-preferences.md"
    link.symlink_to(other)

    with (
        patch.object(inst, "REPO_ROOT", tmp_path),
        patch.object(inst, "RULES_DIR", rules_target),
    ):
        ops = inst._compute_symlink_ops()

    assert ops[0][0] == "update"


def test_symlink_ops_replace_regular_file(tmp_path):
    rules_src = tmp_path / "rules"
    rules_src.mkdir()
    md = rules_src / "coding-preferences.md"
    md.write_text("# new content\n")
    rules_target = tmp_path / "claude_rules"
    rules_target.mkdir()
    (rules_target / "coding-preferences.md").write_text("# old content\n")

    with (
        patch.object(inst, "REPO_ROOT", tmp_path),
        patch.object(inst, "RULES_DIR", rules_target),
    ):
        ops = inst._compute_symlink_ops()

    assert ops[0][0] == "replace_file"


# ---------------------------------------------------------------------------
# _check_preflight_warnings
# ---------------------------------------------------------------------------


def test_preflight_rules_dir_is_file(tmp_path):
    rules_as_file = tmp_path / "rules_dir"
    rules_as_file.write_text("oops")
    with patch.object(inst, "RULES_DIR", rules_as_file):
        _, errors = inst._check_preflight_warnings([])
    assert any("not a directory" in e for e in errors)


def test_preflight_replace_file_warning(tmp_path):
    rules_target = tmp_path / "claude_rules"
    rules_target.mkdir()
    rules_src = tmp_path / "rules"
    rules_src.mkdir()
    md_src = rules_src / "foo.md"
    md_src.write_text("x")
    md_target = rules_target / "foo.md"
    md_target.write_text("y")
    ops = [("replace_file", md_src, md_target)]
    with patch.object(inst, "RULES_DIR", rules_target):
        warnings, _ = inst._check_preflight_warnings(ops)
    assert any("regular file" in w for w in warnings)


def test_preflight_old_sh_hooks_noted(tmp_path):
    # Set up: old shell hook in CLAUDE_DIR/hooks/ with a .py replacement in repo
    old_hooks_dir = tmp_path / "hooks"
    old_hooks_dir.mkdir()
    (old_hooks_dir / "block-no-verify.sh").write_text("#!/bin/bash\n")

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    repo_hooks = repo_root / "hooks"
    repo_hooks.mkdir()
    (repo_hooks / "block_no_verify.py").write_text("# py")

    with (
        patch.object(inst, "CLAUDE_DIR", tmp_path),
        patch.object(inst, "REPO_ROOT", repo_root),
        patch.object(inst, "RULES_DIR", tmp_path / "rules"),
    ):
        warnings, _ = inst._check_preflight_warnings([])

    assert any("block-no-verify.sh" in w or "block_no_verify" in w for w in warnings)


def test_preflight_stale_symlink(tmp_path):
    rules_target = tmp_path / "claude_rules"
    rules_target.mkdir()
    stale = rules_target / "gone.md"
    stale.symlink_to(tmp_path / "nonexistent.md")
    with patch.object(inst, "RULES_DIR", rules_target):
        warnings, _ = inst._check_preflight_warnings([])
    assert any("Stale" in w for w in warnings)


# ---------------------------------------------------------------------------
# CLI tool checks
# ---------------------------------------------------------------------------


def test_check_tools_all_present():
    with patch("shutil.which", return_value="/usr/bin/something"):
        inst._check_tools()


def test_check_tools_required_missing_exits():
    def fake_which(tool):
        return None if tool == "git" else "/usr/bin/" + tool

    with patch("shutil.which", side_effect=fake_which), pytest.raises(SystemExit):
        inst._check_tools()


def test_check_tools_optional_missing_continues(capsys):
    def fake_which(tool):
        return None if tool == "cargo" else "/usr/bin/" + tool

    with patch("shutil.which", side_effect=fake_which):
        inst._check_tools()

    out = capsys.readouterr().out
    assert "cargo" in out


# ---------------------------------------------------------------------------
# _pick_repo
# ---------------------------------------------------------------------------


def test_pick_repo_single_returns_it():
    assert inst._pick_repo([Path("/a")], "mything", required=True) == Path("/a")


def test_pick_repo_multiple_prompts(capsys):
    with patch("builtins.input", return_value="2"):
        result = inst._pick_repo([Path("/a"), Path("/b")], "mything", required=True)
    assert result == Path("/b")
    assert "mything" in capsys.readouterr().out


def test_pick_repo_required_missing_exits():
    with pytest.raises(SystemExit):
        inst._pick_repo([], "mything", required=True)


def test_pick_repo_optional_missing_returns_none():
    assert inst._pick_repo([], "mything", required=False) is None


# ---------------------------------------------------------------------------
# CLAUDE.local.md generation
# ---------------------------------------------------------------------------


def test_generate_local_config_finds_taskgraph(tmp_path):
    tg_dir = tmp_path / "git" / "taskcluster" / "taskgraph"
    tg_dir.mkdir(parents=True)
    pyproject = tg_dir / "pyproject.toml"
    pyproject.write_text('[project]\nname = "taskgraph"\n')

    inputs = [str(tmp_path / "git"), "y"]
    written_content = {}

    def fake_write_text(self, text):
        written_content["content"] = text

    with (
        patch("builtins.input", side_effect=inputs),
        patch.object(inst, "LOCAL_CONFIG_FILE", tmp_path / "CLAUDE.local.md"),
        patch.object(Path, "write_text", fake_write_text),
    ):
        inst._generate_local_config()

    assert str(tg_dir) in written_content.get("content", "")


def test_generate_local_config_finds_fxci_config(tmp_path):
    tg_dir = tmp_path / "git" / "taskcluster" / "taskgraph"
    tg_dir.mkdir(parents=True)
    (tg_dir / "pyproject.toml").write_text('[project]\nname = "taskgraph"\n')

    fxci_dir = tmp_path / "git" / "mozilla-releng" / "fxci-config"
    fxci_dir.mkdir(parents=True)
    (fxci_dir / "pyproject.toml").write_text('[project]\nname = "fxci-config"\n')

    inputs = [str(tmp_path / "git"), "y"]
    written_content = {}

    def fake_write_text(self, text):
        written_content["content"] = text

    with (
        patch("builtins.input", side_effect=inputs),
        patch.object(inst, "LOCAL_CONFIG_FILE", tmp_path / "CLAUDE.local.md"),
        patch.object(Path, "write_text", fake_write_text),
    ):
        inst._generate_local_config()

    assert str(fxci_dir) in written_content.get("content", "")


def test_generate_local_config_picks_fxci_config_when_multiple(tmp_path):
    tg_dir = tmp_path / "git" / "taskcluster" / "taskgraph"
    tg_dir.mkdir(parents=True)
    (tg_dir / "pyproject.toml").write_text('[project]\nname = "taskgraph"\n')

    fxci1 = tmp_path / "git" / "taskcluster" / "fxci-config"
    fxci1.mkdir(parents=True)
    (fxci1 / "pyproject.toml").write_text('[project]\nname = "fxci-config"\n')

    fxci2 = tmp_path / "git" / "mozilla-releng" / "fxci-config"
    fxci2.mkdir(parents=True)
    (fxci2 / "pyproject.toml").write_text('[project]\nname = "fxci-config"\n')

    written_content = {}

    def fake_write_text(self, text):
        written_content["content"] = text

    # inputs: root_path, pick "2" for fxci-config, "y" to write
    inputs = [str(tmp_path / "git"), "2", "y"]
    with (
        patch("builtins.input", side_effect=inputs),
        patch.object(inst, "LOCAL_CONFIG_FILE", tmp_path / "CLAUDE.local.md"),
        patch.object(Path, "write_text", fake_write_text),
    ):
        inst._generate_local_config()

    content = written_content.get("content", "")
    assert str(fxci1) in content or str(fxci2) in content


def test_generate_local_config_skipped_when_exists(tmp_path):
    config = tmp_path / "CLAUDE.local.md"
    config.write_text("taskgraph_repo: /existing\n")

    with patch.object(inst, "LOCAL_CONFIG_FILE", config):
        called = []
        with patch.object(
            inst, "_generate_local_config", side_effect=lambda: called.append(1)
        ):
            if config.exists():
                pass
            else:
                inst._generate_local_config()

    assert called == []


def test_generate_local_config_aborted_on_no(tmp_path):
    tg_dir = tmp_path / "git" / "taskcluster" / "taskgraph"
    tg_dir.mkdir(parents=True)
    (tg_dir / "pyproject.toml").write_text('[project]\nname = "taskgraph"\n')

    inputs = [str(tmp_path / "git"), "n"]
    with (
        patch("builtins.input", side_effect=inputs),
        patch.object(inst, "LOCAL_CONFIG_FILE", tmp_path / "CLAUDE.local.md"),
        pytest.raises(SystemExit),
    ):
        inst._generate_local_config()

    assert not (tmp_path / "CLAUDE.local.md").exists()


# ---------------------------------------------------------------------------
# Apply symlinks
# ---------------------------------------------------------------------------


def test_apply_creates_symlink(tmp_path):
    rules_src = tmp_path / "rules"
    rules_src.mkdir()
    md = rules_src / "foo.md"
    md.write_text("# foo\n")
    rules_target = tmp_path / "claude_rules"
    rules_target.mkdir()

    ops = [("create", md, rules_target / "foo.md")]
    link = rules_target / "foo.md"
    assert not link.exists()

    for op in ops:
        if op[0] in ("create", "update"):
            src, target = op[1], op[2]
            if target.is_symlink() or target.exists():
                target.unlink()
            target.symlink_to(src)

    assert link.is_symlink()
    assert link.resolve() == md.resolve()


def test_apply_replaces_regular_file_with_symlink(tmp_path):
    rules_src = tmp_path / "rules"
    rules_src.mkdir()
    md = rules_src / "foo.md"
    md.write_text("# new\n")
    rules_target = tmp_path / "claude_rules"
    rules_target.mkdir()
    existing = rules_target / "foo.md"
    existing.write_text("# old\n")

    ops = [("replace_file", md, existing)]
    for op in ops:
        if op[0] == "replace_file":
            src, target = op[1], op[2]
            target.unlink()
            target.symlink_to(src)

    assert existing.is_symlink()
    assert existing.resolve() == md.resolve()
