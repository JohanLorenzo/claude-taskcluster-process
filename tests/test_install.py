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
# _unified_diff
# ---------------------------------------------------------------------------


def test_unified_diff_returns_diff_lines():
    diff = inst._unified_diff("old\n", "new\n", "a.txt", "b.txt")
    assert any("-old" in line for line in diff)
    assert any("+new" in line for line in diff)


def test_unified_diff_empty_when_identical():
    assert inst._unified_diff("same\n", "same\n", "a.txt", "b.txt") == []


# ---------------------------------------------------------------------------
# _parse_local_config / _parse_local_config_content
# ---------------------------------------------------------------------------

_LOCAL_CONFIG_CONTENT = """\
# Local configuration — DO NOT COMMIT

## Required paths
taskgraph_repo: /tg/taskcluster/taskgraph
fxci_config_repo: /tg/mozilla-releng/fxci-config

## Tracked repositories
repos:
  - name: taskcluster/taskgraph
    path: /tg/taskcluster/taskgraph
  - name: mozilla-releng/fxci-config
    path: /tg/mozilla-releng/fxci-config
"""


def test_parse_local_config_reads_required_paths(tmp_path):
    config_file = tmp_path / "CLAUDE.local.md"
    config_file.write_text(_LOCAL_CONFIG_CONTENT)
    result = inst._parse_local_config(config_file)
    assert result["taskgraph_repo"] == Path("/tg/taskcluster/taskgraph")
    assert result["fxci_config_repo"] == Path("/tg/mozilla-releng/fxci-config")


def test_parse_local_config_reads_repo_paths(tmp_path):
    config_file = tmp_path / "CLAUDE.local.md"
    config_file.write_text(_LOCAL_CONFIG_CONTENT)
    result = inst._parse_local_config(config_file)
    assert "/tg/taskcluster/taskgraph" in result["repo_paths"]
    assert "/tg/mozilla-releng/fxci-config" in result["repo_paths"]


def test_parse_local_config_missing_file_returns_empty(tmp_path):
    result = inst._parse_local_config(tmp_path / "missing.md")
    assert result["taskgraph_repo"] is None
    assert result["fxci_config_repo"] is None
    assert result["repo_paths"] == []


def test_parse_local_config_no_fxci_config(tmp_path):
    config_file = tmp_path / "CLAUDE.local.md"
    config_file.write_text("taskgraph_repo: /tg/taskcluster/taskgraph\n")
    result = inst._parse_local_config(config_file)
    assert result["taskgraph_repo"] == Path("/tg/taskcluster/taskgraph")
    assert result["fxci_config_repo"] is None


def test_parse_local_config_content_parses_text_directly():
    result = inst._parse_local_config_content(
        "taskgraph_repo: /tg\nfxci_config_repo: /fxci\nrepos:\n"
        "  - name: taskcluster/taskgraph\n    path: /tg\n"
    )
    assert result["taskgraph_repo"] == Path("/tg")
    assert result["fxci_config_repo"] == Path("/fxci")
    assert "/tg" in result["repo_paths"]


# ---------------------------------------------------------------------------
# _build_repos_list
# ---------------------------------------------------------------------------


def test_build_repos_list_no_fxci(tmp_path):
    tg = tmp_path / "taskcluster" / "taskgraph"
    repos = inst._build_repos_list(tg, None, tmp_path)
    assert repos == [{"name": "taskcluster/taskgraph", "path": str(tg)}]


def test_build_repos_list_with_fxci_adds_discovered(tmp_path):
    tg = tmp_path / "taskcluster" / "taskgraph"
    tg.mkdir(parents=True)
    fxci = tmp_path / "mozilla-releng" / "fxci-config"
    fxci.mkdir(parents=True)
    (fxci / "projects.yml").write_text(
        "ss:\n  repo: https://github.com/mozilla-releng/scriptworker-scripts\n"
    )
    ss = tmp_path / "mozilla-releng" / "scriptworker-scripts"
    ss.mkdir(parents=True)

    repos = inst._build_repos_list(tg, fxci, tmp_path)
    names = [r["name"] for r in repos]
    assert "taskcluster/taskgraph" in names
    assert "mozilla-releng/scriptworker-scripts" in names


def test_build_repos_list_deduplicates_taskgraph(tmp_path):
    tg = tmp_path / "taskcluster" / "taskgraph"
    tg.mkdir(parents=True)
    fxci = tmp_path / "mozilla-releng" / "fxci-config"
    fxci.mkdir(parents=True)
    # projects.yml also lists taskgraph — should not be duplicated
    (fxci / "projects.yml").write_text(
        "tg:\n  repo: https://github.com/taskcluster/taskgraph\n"
    )

    repos = inst._build_repos_list(tg, fxci, tmp_path)
    assert sum(1 for r in repos if r["name"] == "taskcluster/taskgraph") == 1


# ---------------------------------------------------------------------------
# _compute_local_config_update
# ---------------------------------------------------------------------------


def test_compute_local_config_update_detects_new_repo(tmp_path):
    fxci = tmp_path / "mozilla-releng" / "fxci-config"
    fxci.mkdir(parents=True)
    (fxci / "projects.yml").write_text(
        "tg:\n  repo: https://github.com/taskcluster/taskgraph\n"
        "ss:\n  repo: https://github.com/mozilla-releng/scriptworker-scripts\n"
    )
    tg = tmp_path / "taskcluster" / "taskgraph"
    tg.mkdir(parents=True)
    ss = tmp_path / "mozilla-releng" / "scriptworker-scripts"
    ss.mkdir(parents=True)

    config_file = tmp_path / "CLAUDE.local.md"
    # Old content: only taskgraph listed, scriptworker-scripts not yet discovered
    config_file.write_text(
        f"taskgraph_repo: {tg}\nfxci_config_repo: {fxci}\n"
        f"\n## Tracked repositories\nrepos:\n"
        f"  - name: taskcluster/taskgraph\n    path: {tg}\n"
    )

    with patch.object(inst, "LOCAL_CONFIG_FILE", config_file):
        diff, new_content, repos = inst._compute_local_config_update()

    assert diff  # there is a diff
    assert "scriptworker-scripts" in new_content
    assert any(r["name"] == "mozilla-releng/scriptworker-scripts" for r in repos)


def test_compute_local_config_update_no_diff_when_current(tmp_path):
    fxci = tmp_path / "mozilla-releng" / "fxci-config"
    fxci.mkdir(parents=True)
    (fxci / "projects.yml").write_text(
        "tg:\n  repo: https://github.com/taskcluster/taskgraph\n"
    )
    tg = tmp_path / "taskcluster" / "taskgraph"
    tg.mkdir(parents=True)

    repos = [{"name": "taskcluster/taskgraph", "path": str(tg)}]
    current_content = inst._render_local_config(tg, fxci, repos)
    config_file = tmp_path / "CLAUDE.local.md"
    config_file.write_text(current_content)

    with patch.object(inst, "LOCAL_CONFIG_FILE", config_file):
        diff, _, _ = inst._compute_local_config_update()

    assert not diff


def test_compute_local_config_update_no_taskgraph_repo_returns_empty(tmp_path):
    config_file = tmp_path / "CLAUDE.local.md"
    config_file.write_text("# no taskgraph_repo set\n")
    with patch.object(inst, "LOCAL_CONFIG_FILE", config_file):
        diff, new_content, repos = inst._compute_local_config_update()
    assert diff == []
    assert new_content is None
    assert repos == []


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
    new = inst._compute_new_settings(old, new_hooks, repo_paths=[])

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
    new = inst._compute_new_settings(old, {}, repo_paths=repo_paths)

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

    new = inst._compute_new_settings(old, {}, repo_paths=["/p"])

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
# already up to date
# ---------------------------------------------------------------------------


def test_main_exits_without_prompt_when_no_changes(tmp_path, capsys):
    hooks_cfg = tmp_path / "hooks-config.json"
    _write_json(hooks_cfg, {"PreToolUse": [], "PostToolUse": []})
    # Settings already match what install.py would compute — no diff expected
    settings_file = _make_settings(
        tmp_path, extra={"hooks": {"PreToolUse": [], "PostToolUse": []}}
    )
    # Local config already reflects the current discovery state
    tg = tmp_path / "taskcluster" / "taskgraph"
    tg.mkdir(parents=True)
    local_config = tmp_path / "CLAUDE.local.md"
    repos = [{"name": "taskcluster/taskgraph", "path": str(tg)}]
    local_config.write_text(inst._render_local_config(tg, None, repos))
    # Settings must also already include additionalDirectories from local config
    settings_file = _make_settings(
        tmp_path,
        extra={
            "hooks": {"PreToolUse": [], "PostToolUse": []},
            "permissions": {
                "allow": [],
                "defaultMode": "plan",
                "additionalDirectories": [str(tg)],
            },
        },
    )
    rules_src = tmp_path / "rules"
    rules_src.mkdir()
    rules_target = tmp_path / "claude_rules"
    rules_target.mkdir()

    with (
        patch.object(inst, "SETTINGS_FILE", settings_file),
        patch.object(inst, "HOOKS_CONFIG_FILE", hooks_cfg),
        patch.object(inst, "LOCAL_CONFIG_FILE", local_config),
        patch.object(inst, "REPO_ROOT", tmp_path),
        patch.object(inst, "RULES_DIR", rules_target),
        patch.object(inst, "CLAUDE_DIR", tmp_path),
        patch("builtins.input", side_effect=AssertionError("should not prompt")),
        pytest.raises(SystemExit) as exc,
    ):
        inst.main()

    assert exc.value.code == 0
    assert "up to date" in capsys.readouterr().out


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
# _get_search_root
# ---------------------------------------------------------------------------


def test_get_search_root_valid_dir(tmp_path):
    with patch("builtins.input", return_value=str(tmp_path)):
        assert inst._get_search_root() == tmp_path


def test_get_search_root_tilde_expansion(tmp_path):
    home = Path.home()
    with patch("builtins.input", return_value="~"):
        result = inst._get_search_root()
    assert result == home


def test_get_search_root_not_a_dir_exits(tmp_path):
    not_a_dir = tmp_path / "file.txt"
    not_a_dir.write_text("x")
    with (
        patch("builtins.input", return_value=str(not_a_dir)),
        pytest.raises(SystemExit),
    ):
        inst._get_search_root()


# ---------------------------------------------------------------------------
# _find_repo_candidates
# ---------------------------------------------------------------------------


def test_find_repo_candidates_finds_taskgraph_via_pyproject(tmp_path):
    tg = tmp_path / "taskgraph"
    tg.mkdir()
    (tg / "pyproject.toml").write_text('[project]\nname = "taskgraph"\n')
    taskgraph, fxci = inst._find_repo_candidates(tmp_path)
    assert tg in taskgraph
    assert fxci == []


def test_find_repo_candidates_finds_taskgraph_via_init(tmp_path):
    tg = tmp_path / "taskgraph"
    pkg = tg / "taskgraph"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    taskgraph, _ = inst._find_repo_candidates(tmp_path)
    assert tg in taskgraph


def test_find_repo_candidates_handles_src_layout(tmp_path):
    tg = tmp_path / "taskgraph"
    src = tg / "src"
    src.mkdir(parents=True)
    (tg / ".git").mkdir()
    (src / "pyproject.toml").write_text('[project]\nname = "taskgraph"\n')
    taskgraph, _ = inst._find_repo_candidates(tmp_path)
    assert tg in taskgraph
    assert src not in taskgraph


def test_find_repo_candidates_finds_fxci_config(tmp_path):
    fxci = tmp_path / "fxci-config"
    fxci.mkdir()
    (fxci / "pyproject.toml").write_text('[project]\nname = "fxci-config"\n')
    _, fxci_candidates = inst._find_repo_candidates(tmp_path)
    assert fxci in fxci_candidates


def test_find_repo_candidates_skips_unreadable_pyproject(tmp_path):
    bad = tmp_path / "bad"
    bad.mkdir()
    pyproject = bad / "pyproject.toml"
    pyproject.write_text("")
    pyproject.chmod(0o000)
    try:
        taskgraph, fxci = inst._find_repo_candidates(tmp_path)
        assert taskgraph == []
        assert fxci == []
    finally:
        pyproject.chmod(0o644)


def test_find_repo_candidates_no_duplicates(tmp_path):
    tg = tmp_path / "taskgraph"
    src = tg / "src"
    src.mkdir(parents=True)
    (tg / ".git").mkdir()
    (src / "pyproject.toml").write_text('[project]\nname = "taskgraph"\n')
    pkg = src / "taskgraph"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    taskgraph, _ = inst._find_repo_candidates(tmp_path)
    assert taskgraph.count(tg) == 1


# ---------------------------------------------------------------------------
# _render_local_config
# ---------------------------------------------------------------------------


def test_render_local_config_without_fxci(tmp_path):
    repos = [{"name": "taskcluster/taskgraph", "path": "/tg"}]
    content = inst._render_local_config(Path("/tg"), None, repos)
    assert "taskgraph_repo: /tg" in content
    assert "fxci_config_repo" not in content
    assert "taskcluster/taskgraph" in content


def test_render_local_config_with_fxci(tmp_path):
    repos = [
        {"name": "taskcluster/taskgraph", "path": "/tg"},
        {"name": "mozilla-releng/fxci-config", "path": "/fxci"},
    ]
    content = inst._render_local_config(Path("/tg"), Path("/fxci"), repos)
    assert "fxci_config_repo: /fxci" in content
    assert "mozilla-releng/fxci-config" in content


def test_render_local_config_structure(tmp_path):
    repos = [{"name": "org/repo", "path": "/p"}]
    content = inst._render_local_config(Path("/tg"), None, repos)
    assert content.startswith("# Local configuration — DO NOT COMMIT")
    assert "## Required paths" in content
    assert "## Tracked repositories" in content
    assert "repos:" in content


# ---------------------------------------------------------------------------
# _parse_github_slugs
# ---------------------------------------------------------------------------

_PROJECTS_YML = """\
---
ash:
  repo: https://hg.mozilla.org/projects/ash
  repo_type: hg
taskgraph:
  repo: https://github.com/taskcluster/taskgraph
  repo_type: git
fxci-config:
  repo: https://github.com/mozilla-releng/fxci-config
  repo_type: git
with-dot-git:
  repo: https://github.com/org/project.git
  repo_type: git
"""


def test_parse_github_slugs_returns_github_repos(tmp_path):
    (tmp_path / "projects.yml").write_text(_PROJECTS_YML)
    slugs = inst._parse_github_slugs(tmp_path)
    assert slugs == {
        "taskcluster/taskgraph",
        "mozilla-releng/fxci-config",
        "org/project",
    }


def test_parse_github_slugs_excludes_hg_repos(tmp_path):
    (tmp_path / "projects.yml").write_text(_PROJECTS_YML)
    slugs = inst._parse_github_slugs(tmp_path)
    assert not any("hg.mozilla.org" in s for s in slugs)


def test_parse_github_slugs_strips_dot_git_suffix(tmp_path):
    (tmp_path / "projects.yml").write_text(_PROJECTS_YML)
    assert "org/project" in inst._parse_github_slugs(tmp_path)


def test_parse_github_slugs_missing_file_returns_empty(tmp_path):
    assert inst._parse_github_slugs(tmp_path) == set()


# ---------------------------------------------------------------------------
# _discover_tracked_repos
# ---------------------------------------------------------------------------


def test_discover_tracked_repos_finds_matching_local_clone(tmp_path):
    fxci = tmp_path / "fxci-config"
    fxci.mkdir()
    (fxci / "projects.yml").write_text(
        "taskgraph:\n  repo: https://github.com/taskcluster/taskgraph\n"
    )
    tg = tmp_path / "taskcluster" / "taskgraph"
    tg.mkdir(parents=True)

    repos = inst._discover_tracked_repos(fxci, tmp_path)
    assert repos == [{"name": "taskcluster/taskgraph", "path": str(tg)}]


def test_discover_tracked_repos_skips_missing_clones(tmp_path):
    fxci = tmp_path / "fxci-config"
    fxci.mkdir()
    (fxci / "projects.yml").write_text(
        "taskgraph:\n  repo: https://github.com/taskcluster/taskgraph\n"
    )
    # No local clone created
    repos = inst._discover_tracked_repos(fxci, tmp_path)
    assert repos == []


def test_discover_tracked_repos_matches_by_org_and_name(tmp_path):
    fxci = tmp_path / "fxci-config"
    fxci.mkdir()
    (fxci / "projects.yml").write_text(
        "a:\n  repo: https://github.com/org-a/project\n"
        "b:\n  repo: https://github.com/org-b/project\n"
    )
    # Only org-b/project exists locally
    (tmp_path / "org-b" / "project").mkdir(parents=True)

    repos = inst._discover_tracked_repos(fxci, tmp_path)
    assert repos == [
        {"name": "org-b/project", "path": str(tmp_path / "org-b" / "project")}
    ]


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
