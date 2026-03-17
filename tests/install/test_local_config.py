import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from install import local_config

_LOCAL_CONFIG_CONTENT = """\
# Local configuration — DO NOT COMMIT

## Required paths
taskgraph_repo: /tg/taskcluster/taskgraph
mozilla_taskgraph_repo: /tg/mozilla-releng/mozilla-taskgraph
fxci_config_repo: /tg/mozilla-releng/fxci-config

## Tracked repositories
repos:
  - name: taskcluster/taskgraph
    path: /tg/taskcluster/taskgraph
  - name: mozilla-releng/fxci-config
    path: /tg/mozilla-releng/fxci-config
"""


def test_parse_local_config_content_reads_required_paths():
    result = local_config.parse_local_config_content(_LOCAL_CONFIG_CONTENT)
    assert result["taskgraph_repo"] == Path("/tg/taskcluster/taskgraph")
    assert result["mozilla_taskgraph_repo"] == Path(
        "/tg/mozilla-releng/mozilla-taskgraph"
    )
    assert result["fxci_config_repo"] == Path("/tg/mozilla-releng/fxci-config")


def test_parse_local_config_content_reads_repo_paths():
    result = local_config.parse_local_config_content(_LOCAL_CONFIG_CONTENT)
    assert "/tg/taskcluster/taskgraph" in result["repo_paths"]
    assert "/tg/mozilla-releng/fxci-config" in result["repo_paths"]


def test_parse_local_config_content_empty_string_returns_empty():
    result = local_config.parse_local_config_content("")
    assert result["taskgraph_repo"] is None
    assert result["mozilla_taskgraph_repo"] is None
    assert result["fxci_config_repo"] is None
    assert result["repo_paths"] == []


def test_parse_local_config_content_no_fxci_config():
    result = local_config.parse_local_config_content(
        "taskgraph_repo: /tg/taskcluster/taskgraph\n"
    )
    assert result["taskgraph_repo"] == Path("/tg/taskcluster/taskgraph")
    assert result["fxci_config_repo"] is None


def test_parse_local_config_content_parses_text_directly():
    result = local_config.parse_local_config_content(
        "taskgraph_repo: /tg\n"
        "mozilla_taskgraph_repo: /mtg\n"
        "fxci_config_repo: /fxci\n"
        "repos:\n"
        "  - name: taskcluster/taskgraph\n    path: /tg\n"
    )
    assert result["taskgraph_repo"] == Path("/tg")
    assert result["mozilla_taskgraph_repo"] == Path("/mtg")
    assert result["fxci_config_repo"] == Path("/fxci")
    assert "/tg" in result["repo_paths"]


def test_build_repos_list_no_fxci(tmp_path):
    tg = tmp_path / "taskcluster" / "taskgraph"
    mtg = tmp_path / "mozilla-releng" / "mozilla-taskgraph"
    repos = local_config.build_repos_list(tg, mtg, None, tmp_path)
    names = [r["name"] for r in repos]
    assert "taskcluster/taskgraph" in names
    assert "mozilla-releng/mozilla-taskgraph" in names


def test_build_repos_list_with_fxci_adds_discovered(tmp_path):
    tg = tmp_path / "taskcluster" / "taskgraph"
    tg.mkdir(parents=True)
    mtg = tmp_path / "mozilla-releng" / "mozilla-taskgraph"
    mtg.mkdir(parents=True)
    fxci = tmp_path / "mozilla-releng" / "fxci-config"
    fxci.mkdir(parents=True)
    (fxci / "projects.yml").write_text(
        "ss:\n  repo: https://github.com/mozilla-releng/scriptworker-scripts\n"
    )
    ss = tmp_path / "mozilla-releng" / "scriptworker-scripts"
    ss.mkdir(parents=True)

    repos = local_config.build_repos_list(tg, mtg, fxci, tmp_path)
    names = [r["name"] for r in repos]
    assert "taskcluster/taskgraph" in names
    assert "mozilla-releng/mozilla-taskgraph" in names
    assert "mozilla-releng/scriptworker-scripts" in names


def test_build_repos_list_deduplicates_taskgraph(tmp_path):
    tg = tmp_path / "taskcluster" / "taskgraph"
    tg.mkdir(parents=True)
    mtg = tmp_path / "mozilla-releng" / "mozilla-taskgraph"
    mtg.mkdir(parents=True)
    fxci = tmp_path / "mozilla-releng" / "fxci-config"
    fxci.mkdir(parents=True)
    (fxci / "projects.yml").write_text(
        "tg:\n  repo: https://github.com/taskcluster/taskgraph\n"
    )

    repos = local_config.build_repos_list(tg, mtg, fxci, tmp_path)
    assert sum(1 for r in repos if r["name"] == "taskcluster/taskgraph") == 1


def test_compute_local_config_update_detects_new_repo(tmp_path):
    fxci = tmp_path / "mozilla-releng" / "fxci-config"
    fxci.mkdir(parents=True)
    (fxci / "projects.yml").write_text(
        "tg:\n  repo: https://github.com/taskcluster/taskgraph\n"
        "ss:\n  repo: https://github.com/mozilla-releng/scriptworker-scripts\n"
    )
    tg = tmp_path / "taskcluster" / "taskgraph"
    tg.mkdir(parents=True)
    mtg = tmp_path / "mozilla-releng" / "mozilla-taskgraph"
    mtg.mkdir(parents=True)
    ss = tmp_path / "mozilla-releng" / "scriptworker-scripts"
    ss.mkdir(parents=True)

    config_file = tmp_path / "CLAUDE.local.md"
    config_file.write_text(
        f"taskgraph_repo: {tg}\n"
        f"mozilla_taskgraph_repo: {mtg}\n"
        f"fxci_config_repo: {fxci}\n"
        f"\n## Tracked repositories\nrepos:\n"
        f"  - name: taskcluster/taskgraph\n    path: {tg}\n"
    )

    with (
        patch.object(local_config, "LOCAL_CONFIG_FILE", config_file),
        patch("builtins.input", return_value=str(tmp_path)),
    ):
        diff, new_content, repos = local_config.compute_local_config_update()

    assert diff
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
    mtg = tmp_path / "mozilla-releng" / "mozilla-taskgraph"
    mtg.mkdir(parents=True)

    repos = [
        {"name": "taskcluster/taskgraph", "path": str(tg)},
        {"name": "mozilla-releng/mozilla-taskgraph", "path": str(mtg)},
    ]
    current_content = local_config.render_local_config(tg, mtg, fxci, repos)
    config_file = tmp_path / "CLAUDE.local.md"
    config_file.write_text(current_content)

    with (
        patch.object(local_config, "LOCAL_CONFIG_FILE", config_file),
        patch("builtins.input", return_value=str(tmp_path)),
    ):
        diff, _, _ = local_config.compute_local_config_update()

    assert not diff


def test_compute_local_config_update_no_taskgraph_repo_returns_empty(tmp_path):
    config_file = tmp_path / "CLAUDE.local.md"
    config_file.write_text("# no taskgraph_repo set\n")
    with patch.object(local_config, "LOCAL_CONFIG_FILE", config_file):
        diff, new_content, repos = local_config.compute_local_config_update()
    assert diff == []
    assert new_content is None
    assert repos == []


def test_compute_local_config_update_no_mozilla_taskgraph_repo_returns_empty(tmp_path):
    config_file = tmp_path / "CLAUDE.local.md"
    config_file.write_text("taskgraph_repo: /tg\n# no mozilla_taskgraph_repo\n")
    with patch.object(local_config, "LOCAL_CONFIG_FILE", config_file):
        diff, new_content, repos = local_config.compute_local_config_update()
    assert diff == []
    assert new_content is None
    assert repos == []


def test_get_search_root_valid_dir(tmp_path):
    with patch("builtins.input", return_value=str(tmp_path)):
        assert local_config.get_search_root() == tmp_path


def test_get_search_root_tilde_expansion():
    home = Path.home()
    with patch("builtins.input", return_value="~"):
        result = local_config.get_search_root()
    assert result == home


def test_get_search_root_not_a_dir_exits(tmp_path):
    not_a_dir = tmp_path / "file.txt"
    not_a_dir.write_text("x")
    with (
        patch("builtins.input", return_value=str(not_a_dir)),
        pytest.raises(SystemExit),
    ):
        local_config.get_search_root()


def test_matches_pyproject_name_double_quotes():
    assert local_config.matches_pyproject_name(
        '[project]\nname = "taskgraph"\n', "taskgraph"
    )


def test_matches_pyproject_name_single_quotes():
    assert local_config.matches_pyproject_name(
        "[project]\nname = 'taskgraph'\n", "taskgraph"
    )


def test_matches_pyproject_name_no_match():
    assert not local_config.matches_pyproject_name(
        '[project]\nname = "other"\n', "taskgraph"
    )


def test_scan_pyprojects_finds_taskgraph(tmp_path):
    tg = tmp_path / "taskgraph"
    tg.mkdir()
    (tg / "pyproject.toml").write_text('[project]\nname = "taskgraph"\n')
    taskgraph, fxci, mozilla_taskgraph = local_config.scan_pyprojects(tmp_path)
    assert tg in taskgraph
    assert fxci == []
    assert mozilla_taskgraph == []


def test_scan_pyprojects_finds_mozilla_taskgraph(tmp_path):
    mtg = tmp_path / "mozilla-taskgraph"
    mtg.mkdir()
    (mtg / "pyproject.toml").write_text('[project]\nname = "mozilla-taskgraph"\n')
    taskgraph, fxci, mozilla_taskgraph = local_config.scan_pyprojects(tmp_path)
    assert taskgraph == []
    assert fxci == []
    assert mtg in mozilla_taskgraph


def test_scan_pyprojects_handles_src_layout(tmp_path):
    tg = tmp_path / "taskgraph"
    src = tg / "src"
    src.mkdir(parents=True)
    (tg / ".git").mkdir()
    (src / "pyproject.toml").write_text('[project]\nname = "taskgraph"\n')
    taskgraph, _, _ = local_config.scan_pyprojects(tmp_path)
    assert tg in taskgraph
    assert src not in taskgraph


def test_scan_pyprojects_finds_fxci_config(tmp_path):
    fxci = tmp_path / "fxci-config"
    fxci.mkdir()
    (fxci / "pyproject.toml").write_text('[project]\nname = "fxci-config"\n')
    _, fxci_candidates, _ = local_config.scan_pyprojects(tmp_path)
    assert fxci in fxci_candidates


def test_scan_pyprojects_skips_unreadable(tmp_path):
    bad = tmp_path / "bad"
    bad.mkdir()
    pyproject = bad / "pyproject.toml"
    pyproject.write_text("")
    pyproject.chmod(0o000)
    try:
        taskgraph, fxci, mozilla_taskgraph = local_config.scan_pyprojects(tmp_path)
        assert taskgraph == []
        assert fxci == []
        assert mozilla_taskgraph == []
    finally:
        pyproject.chmod(0o644)


def test_scan_pyprojects_no_duplicates(tmp_path):
    tg = tmp_path / "taskgraph"
    src = tg / "src"
    src.mkdir(parents=True)
    (tg / ".git").mkdir()
    (src / "pyproject.toml").write_text('[project]\nname = "taskgraph"\n')
    taskgraph, _, _ = local_config.scan_pyprojects(tmp_path)
    assert taskgraph.count(tg) == 1


def test_find_repo_candidates_finds_taskgraph_via_init(tmp_path):
    tg = tmp_path / "taskgraph"
    pkg = tg / "taskgraph"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    taskgraph, _, _ = local_config.find_repo_candidates(tmp_path)
    assert tg in taskgraph


def test_find_repo_candidates_no_duplicates_across_pyproject_and_init(tmp_path):
    tg = tmp_path / "taskgraph"
    src = tg / "src"
    src.mkdir(parents=True)
    (tg / ".git").mkdir()
    (src / "pyproject.toml").write_text('[project]\nname = "taskgraph"\n')
    pkg = src / "taskgraph"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    taskgraph, _, _ = local_config.find_repo_candidates(tmp_path)
    assert taskgraph.count(tg) == 1


def test_render_local_config_without_fxci():
    repos = [{"name": "taskcluster/taskgraph", "path": "/tg"}]
    content = local_config.render_local_config(Path("/tg"), Path("/mtg"), None, repos)
    assert "taskgraph_repo: /tg" in content
    assert "mozilla_taskgraph_repo: /mtg" in content
    assert "fxci_config_repo" not in content
    assert "taskcluster/taskgraph" in content


def test_render_local_config_with_fxci():
    repos = [
        {"name": "taskcluster/taskgraph", "path": "/tg"},
        {"name": "mozilla-releng/fxci-config", "path": "/fxci"},
    ]
    content = local_config.render_local_config(
        Path("/tg"), Path("/mtg"), Path("/fxci"), repos
    )
    assert "fxci_config_repo: /fxci" in content
    assert "mozilla-releng/fxci-config" in content


def test_render_local_config_structure():
    repos = [{"name": "org/repo", "path": "/p"}]
    content = local_config.render_local_config(Path("/tg"), Path("/mtg"), None, repos)
    assert content.startswith("# Local configuration — DO NOT COMMIT")
    assert "## Required paths" in content
    assert "## Tracked repositories" in content
    assert "repos:" in content


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
    slugs = local_config.parse_github_slugs(tmp_path)
    assert slugs == {
        "taskcluster/taskgraph",
        "mozilla-releng/fxci-config",
        "org/project",
    }


def test_parse_github_slugs_excludes_hg_repos(tmp_path):
    (tmp_path / "projects.yml").write_text(_PROJECTS_YML)
    slugs = local_config.parse_github_slugs(tmp_path)
    assert not any("hg.mozilla.org" in s for s in slugs)


def test_parse_github_slugs_strips_dot_git_suffix(tmp_path):
    (tmp_path / "projects.yml").write_text(_PROJECTS_YML)
    assert "org/project" in local_config.parse_github_slugs(tmp_path)


def test_parse_github_slugs_missing_file_returns_empty(tmp_path):
    assert local_config.parse_github_slugs(tmp_path) == set()


def test_discover_tracked_repos_finds_matching_local_clone(tmp_path):
    fxci = tmp_path / "fxci-config"
    fxci.mkdir()
    (fxci / "projects.yml").write_text(
        "taskgraph:\n  repo: https://github.com/taskcluster/taskgraph\n"
    )
    tg = tmp_path / "taskcluster" / "taskgraph"
    tg.mkdir(parents=True)

    repos = local_config.discover_tracked_repos(fxci, tmp_path)
    assert repos == [{"name": "taskcluster/taskgraph", "path": str(tg)}]


def test_discover_tracked_repos_skips_missing_clones(tmp_path):
    fxci = tmp_path / "fxci-config"
    fxci.mkdir()
    (fxci / "projects.yml").write_text(
        "taskgraph:\n  repo: https://github.com/taskcluster/taskgraph\n"
    )
    repos = local_config.discover_tracked_repos(fxci, tmp_path)
    assert repos == []


def test_discover_tracked_repos_matches_by_org_and_name(tmp_path):
    fxci = tmp_path / "fxci-config"
    fxci.mkdir()
    (fxci / "projects.yml").write_text(
        "a:\n  repo: https://github.com/org-a/project\n"
        "b:\n  repo: https://github.com/org-b/project\n"
    )
    (tmp_path / "org-b" / "project").mkdir(parents=True)

    repos = local_config.discover_tracked_repos(fxci, tmp_path)
    assert repos == [
        {"name": "org-b/project", "path": str(tmp_path / "org-b" / "project")}
    ]


def test_discover_tracked_repos_skips_match_inside_git_repo(tmp_path):
    fxci = tmp_path / "fxci-config"
    fxci.mkdir()
    (fxci / "projects.yml").write_text(
        "glean:\n  repo: https://github.com/mozilla/glean\n"
    )
    # Simulate Firefox build output: obj-*/dist/include/mozilla/glean inside a git repo
    firefox = tmp_path / "firefox"
    firefox.mkdir()
    (firefox / ".git").mkdir()
    nested = firefox / "obj-x86_64" / "dist" / "include" / "mozilla" / "glean"
    nested.mkdir(parents=True)

    repos = local_config.discover_tracked_repos(fxci, tmp_path)
    assert repos == []


def test_discover_tracked_repos_finds_repo_in_subdirectory(tmp_path):
    fxci = tmp_path / "fxci-config"
    fxci.mkdir()
    (fxci / "projects.yml").write_text(
        "taskgraph:\n  repo: https://github.com/taskcluster/taskgraph\n"
    )
    # Repo nested one level deeper (e.g. user entered ~/git instead of ~/git/hub)
    tg = tmp_path / "hub" / "taskcluster" / "taskgraph"
    tg.mkdir(parents=True)

    repos = local_config.discover_tracked_repos(fxci, tmp_path)
    assert repos == [{"name": "taskcluster/taskgraph", "path": str(tg)}]


def test_pick_repo_single_returns_it():
    assert local_config.pick_repo([Path("/a")], "mything", required=True) == Path("/a")


def test_pick_repo_multiple_prompts(caplog):

    with caplog.at_level(logging.INFO), patch("builtins.input", return_value="2"):
        result = local_config.pick_repo(
            [Path("/a"), Path("/b")], "mything", required=True
        )
    assert result == Path("/b")
    assert "mything" in caplog.text


def test_pick_repo_required_missing_exits():
    with pytest.raises(SystemExit):
        local_config.pick_repo([], "mything", required=True)


def test_pick_repo_optional_missing_returns_none():
    assert local_config.pick_repo([], "mything", required=False) is None


def _make_tg_and_mtg(tmp_path):
    tg_dir = tmp_path / "git" / "taskcluster" / "taskgraph"
    tg_dir.mkdir(parents=True)
    (tg_dir / "pyproject.toml").write_text('[project]\nname = "taskgraph"\n')
    mtg_dir = tmp_path / "git" / "mozilla-releng" / "mozilla-taskgraph"
    mtg_dir.mkdir(parents=True)
    (mtg_dir / "pyproject.toml").write_text('[project]\nname = "mozilla-taskgraph"\n')
    return tg_dir, mtg_dir


def test_generate_local_config_finds_taskgraph(tmp_path):
    tg_dir, _mtg_dir = _make_tg_and_mtg(tmp_path)

    inputs = [str(tmp_path / "git"), "y"]
    written_content = {}

    def fake_write_text(self, text):
        written_content["content"] = text

    with (
        patch("builtins.input", side_effect=inputs),
        patch.object(local_config, "LOCAL_CONFIG_FILE", tmp_path / "CLAUDE.local.md"),
        patch.object(Path, "write_text", fake_write_text),
    ):
        local_config.generate_local_config()

    assert str(tg_dir) in written_content.get("content", "")


def test_generate_local_config_finds_mozilla_taskgraph(tmp_path):
    _tg_dir, mtg_dir = _make_tg_and_mtg(tmp_path)

    inputs = [str(tmp_path / "git"), "y"]
    written_content = {}

    def fake_write_text(self, text):
        written_content["content"] = text

    with (
        patch("builtins.input", side_effect=inputs),
        patch.object(local_config, "LOCAL_CONFIG_FILE", tmp_path / "CLAUDE.local.md"),
        patch.object(Path, "write_text", fake_write_text),
    ):
        local_config.generate_local_config()

    assert str(mtg_dir) in written_content.get("content", "")


def test_generate_local_config_fails_when_mozilla_taskgraph_not_found(tmp_path):
    tg_dir = tmp_path / "git" / "taskcluster" / "taskgraph"
    tg_dir.mkdir(parents=True)
    (tg_dir / "pyproject.toml").write_text('[project]\nname = "taskgraph"\n')
    # No mozilla-taskgraph directory

    with (
        patch("builtins.input", return_value=str(tmp_path / "git")),
        patch.object(local_config, "LOCAL_CONFIG_FILE", tmp_path / "CLAUDE.local.md"),
        pytest.raises(SystemExit),
    ):
        local_config.generate_local_config()


def test_generate_local_config_finds_fxci_config(tmp_path):
    _tg_dir, _mtg_dir = _make_tg_and_mtg(tmp_path)

    fxci_dir = tmp_path / "git" / "mozilla-releng" / "fxci-config"
    fxci_dir.mkdir(parents=True)
    (fxci_dir / "pyproject.toml").write_text('[project]\nname = "fxci-config"\n')

    inputs = [str(tmp_path / "git"), "y"]
    written_content = {}

    def fake_write_text(self, text):
        written_content["content"] = text

    with (
        patch("builtins.input", side_effect=inputs),
        patch.object(local_config, "LOCAL_CONFIG_FILE", tmp_path / "CLAUDE.local.md"),
        patch.object(Path, "write_text", fake_write_text),
    ):
        local_config.generate_local_config()

    assert str(fxci_dir) in written_content.get("content", "")


def test_generate_local_config_picks_fxci_config_when_multiple(tmp_path):
    _tg_dir, _mtg_dir = _make_tg_and_mtg(tmp_path)

    fxci1 = tmp_path / "git" / "taskcluster" / "fxci-config"
    fxci1.mkdir(parents=True)
    (fxci1 / "pyproject.toml").write_text('[project]\nname = "fxci-config"\n')

    fxci2 = tmp_path / "git" / "mozilla-releng" / "fxci-config"
    fxci2.mkdir(parents=True)
    (fxci2 / "pyproject.toml").write_text('[project]\nname = "fxci-config"\n')

    written_content = {}

    def fake_write_text(self, text):
        written_content["content"] = text

    inputs = [str(tmp_path / "git"), "2", "y"]
    with (
        patch("builtins.input", side_effect=inputs),
        patch.object(local_config, "LOCAL_CONFIG_FILE", tmp_path / "CLAUDE.local.md"),
        patch.object(Path, "write_text", fake_write_text),
    ):
        local_config.generate_local_config()

    content = written_content.get("content", "")
    assert str(fxci1) in content or str(fxci2) in content


def test_generate_local_config_skipped_when_exists(tmp_path):
    config = tmp_path / "CLAUDE.local.md"
    config.write_text("taskgraph_repo: /existing\n")

    with patch.object(local_config, "LOCAL_CONFIG_FILE", config):
        called = []
        with patch.object(
            local_config,
            "generate_local_config",
            side_effect=lambda: called.append(1),
        ):
            if config.exists():
                pass
            else:
                local_config.generate_local_config()

    assert called == []


def test_generate_local_config_aborted_on_no(tmp_path):
    _tg_dir, _mtg_dir = _make_tg_and_mtg(tmp_path)

    inputs = [str(tmp_path / "git"), "n"]
    with (
        patch("builtins.input", side_effect=inputs),
        patch.object(local_config, "LOCAL_CONFIG_FILE", tmp_path / "CLAUDE.local.md"),
        pytest.raises(SystemExit),
    ):
        local_config.generate_local_config()

    assert not (tmp_path / "CLAUDE.local.md").exists()
