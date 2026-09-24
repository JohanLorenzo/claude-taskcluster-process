import json
from unittest.mock import patch

from install import skills


def _make_skill(parent, name):
    skill_dir = parent / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("# test skill\n")
    return skill_dir


def _write_external_config(path, mapping):
    path.write_text(json.dumps(mapping))


def _write_local_config_repos(path, repos):
    lines = "".join(
        f"  - name: {name}\n    path: {repo_path}\n" for name, repo_path in repos
    )
    path.write_text(f"## Tracked repositories\nrepos:\n{lines}")


def test_skill_ops_new_symlink(tmp_path):
    skills_src = tmp_path / "skills"
    skills_src.mkdir()
    _make_skill(skills_src, "review-taskgraph")
    skills_target = tmp_path / "claude_skills"
    skills_target.mkdir()

    with (
        patch.object(skills, "REPO_ROOT", tmp_path),
        patch.object(skills, "SKILLS_DIR", skills_target),
    ):
        ops = skills.compute_skill_ops()

    assert len(ops) == 1
    op = ops[0]
    assert op[0] == "create"
    assert op[2] == skills_target / "review-taskgraph"


def test_skill_ops_already_correct(tmp_path):
    skills_src = tmp_path / "skills"
    skills_src.mkdir()
    src = _make_skill(skills_src, "review-taskgraph")
    skills_target = tmp_path / "claude_skills"
    skills_target.mkdir()
    link = skills_target / "review-taskgraph"
    link.symlink_to(src)

    with (
        patch.object(skills, "REPO_ROOT", tmp_path),
        patch.object(skills, "SKILLS_DIR", skills_target),
    ):
        ops = skills.compute_skill_ops()

    assert ops[0][0] == "noop"


def test_skill_ops_update_symlink(tmp_path):
    skills_src = tmp_path / "skills"
    skills_src.mkdir()
    src = _make_skill(skills_src, "review-taskgraph")
    other = tmp_path / "other-skill"
    other.mkdir()
    (other / "SKILL.md").write_text("# other\n")
    skills_target = tmp_path / "claude_skills"
    skills_target.mkdir()
    link = skills_target / "review-taskgraph"
    link.symlink_to(other)

    with (
        patch.object(skills, "REPO_ROOT", tmp_path),
        patch.object(skills, "SKILLS_DIR", skills_target),
    ):
        ops = skills.compute_skill_ops()

    assert ops[0][0] == "update"
    assert ops[0][1] == src


def test_skill_ops_replace_regular_dir(tmp_path):
    skills_src = tmp_path / "skills"
    skills_src.mkdir()
    _make_skill(skills_src, "review-taskgraph")
    skills_target = tmp_path / "claude_skills"
    skills_target.mkdir()
    (skills_target / "review-taskgraph").mkdir()

    with (
        patch.object(skills, "REPO_ROOT", tmp_path),
        patch.object(skills, "SKILLS_DIR", skills_target),
    ):
        ops = skills.compute_skill_ops()

    assert ops[0][0] == "replace_dir"


def test_skill_ops_skips_dirs_without_skill_md(tmp_path):
    skills_src = tmp_path / "skills"
    skills_src.mkdir()
    (skills_src / "no-skill-md").mkdir()
    skills_target = tmp_path / "claude_skills"
    skills_target.mkdir()

    with (
        patch.object(skills, "REPO_ROOT", tmp_path),
        patch.object(skills, "SKILLS_DIR", skills_target),
    ):
        ops = skills.compute_skill_ops()

    assert ops == []


def test_replace_dir_warnings_returns_warning_per_op(tmp_path):
    src = tmp_path / "src"
    target = tmp_path / "target"
    warnings = skills.replace_dir_warnings([("replace_dir", src, target)])
    assert len(warnings) == 1
    assert "regular directory" in warnings[0]


def test_replace_dir_warnings_empty_for_other_ops(tmp_path):
    src = tmp_path / "src"
    target = tmp_path / "target"
    assert skills.replace_dir_warnings([("create", src, target)]) == []
    assert skills.replace_dir_warnings([("noop", src, target)]) == []


def test_stale_skill_warnings_detects_broken_link(tmp_path):
    skills_dir = tmp_path / "claude_skills"
    skills_dir.mkdir()
    skills_src = tmp_path / "skills"
    skills_src.mkdir()
    stale = skills_dir / "gone"
    stale.symlink_to(skills_src / "gone")

    with (
        patch.object(skills, "SKILLS_DIR", skills_dir),
        patch.object(skills, "REPO_ROOT", tmp_path),
    ):
        warnings = skills.stale_skill_warnings()

    assert any("Stale" in w for w in warnings)


def test_stale_skill_warnings_ignores_external_broken_links(tmp_path):
    skills_dir = tmp_path / "claude_skills"
    skills_dir.mkdir()
    skills_src = tmp_path / "skills"
    skills_src.mkdir()
    # Points outside our skills dir
    stale = skills_dir / "external"
    stale.symlink_to(tmp_path / "elsewhere" / "skill")

    with (
        patch.object(skills, "SKILLS_DIR", skills_dir),
        patch.object(skills, "REPO_ROOT", tmp_path),
    ):
        warnings = skills.stale_skill_warnings()

    assert warnings == []


def test_stale_skill_warnings_empty_when_no_skills_dir(tmp_path):
    with patch.object(skills, "SKILLS_DIR", tmp_path / "missing"):
        assert skills.stale_skill_warnings() == []


def test_skill_ops_external_source_creates_symlink(tmp_path):
    skills_src = tmp_path / "skills"
    skills_src.mkdir()
    external_repo = tmp_path / "external-repo"
    external_skill = _make_skill(external_repo / ".claude" / "skills", "external-skill")
    skills_target = tmp_path / "claude_skills"
    skills_target.mkdir()
    external_config = tmp_path / "external-skills.json"
    _write_external_config(external_config, {"org/external-repo": ".claude/skills"})
    local_config_file = tmp_path / "CLAUDE.local.md"
    _write_local_config_repos(local_config_file, [("org/external-repo", external_repo)])

    with (
        patch.object(skills, "REPO_ROOT", tmp_path),
        patch.object(skills, "SKILLS_DIR", skills_target),
        patch.object(skills, "EXTERNAL_SKILLS_CONFIG_FILE", external_config),
        patch.object(skills, "LOCAL_CONFIG_FILE", local_config_file),
    ):
        ops = skills.compute_skill_ops()

    assert len(ops) == 1
    assert ops[0][0] == "create"
    assert ops[0][1] == external_skill
    assert ops[0][2] == skills_target / "external-skill"


def test_external_skill_warnings_untracked_slug(tmp_path):
    skills_src = tmp_path / "skills"
    skills_src.mkdir()
    skills_target = tmp_path / "claude_skills"
    skills_target.mkdir()
    external_config = tmp_path / "external-skills.json"
    _write_external_config(external_config, {"org/external-repo": ".claude/skills"})
    local_config_file = tmp_path / "CLAUDE.local.md"
    local_config_file.write_text("## Tracked repositories\nrepos:\n")

    with (
        patch.object(skills, "REPO_ROOT", tmp_path),
        patch.object(skills, "SKILLS_DIR", skills_target),
        patch.object(skills, "EXTERNAL_SKILLS_CONFIG_FILE", external_config),
        patch.object(skills, "LOCAL_CONFIG_FILE", local_config_file),
    ):
        ops = skills.compute_skill_ops()
        warnings = skills.external_skill_warnings()

    assert ops == []
    assert any("not a tracked repo" in w for w in warnings)


def test_external_skill_warnings_missing_dir(tmp_path):
    skills_src = tmp_path / "skills"
    skills_src.mkdir()
    skills_target = tmp_path / "claude_skills"
    skills_target.mkdir()
    external_repo = tmp_path / "external-repo"
    external_repo.mkdir()
    external_config = tmp_path / "external-skills.json"
    _write_external_config(external_config, {"org/external-repo": ".claude/skills"})
    local_config_file = tmp_path / "CLAUDE.local.md"
    _write_local_config_repos(local_config_file, [("org/external-repo", external_repo)])

    with (
        patch.object(skills, "REPO_ROOT", tmp_path),
        patch.object(skills, "SKILLS_DIR", skills_target),
        patch.object(skills, "EXTERNAL_SKILLS_CONFIG_FILE", external_config),
        patch.object(skills, "LOCAL_CONFIG_FILE", local_config_file),
    ):
        ops = skills.compute_skill_ops()
        warnings = skills.external_skill_warnings()

    assert ops == []
    assert any("does not exist" in w for w in warnings)


def test_skill_ops_duplicate_name_keeps_first_source(tmp_path):
    skills_src = tmp_path / "skills"
    skills_src.mkdir()
    own_skill = _make_skill(skills_src, "shared-skill")
    external_repo = tmp_path / "external-repo"
    _make_skill(external_repo / ".claude" / "skills", "shared-skill")
    skills_target = tmp_path / "claude_skills"
    skills_target.mkdir()
    external_config = tmp_path / "external-skills.json"
    _write_external_config(external_config, {"org/external-repo": ".claude/skills"})
    local_config_file = tmp_path / "CLAUDE.local.md"
    _write_local_config_repos(local_config_file, [("org/external-repo", external_repo)])

    with (
        patch.object(skills, "REPO_ROOT", tmp_path),
        patch.object(skills, "SKILLS_DIR", skills_target),
        patch.object(skills, "EXTERNAL_SKILLS_CONFIG_FILE", external_config),
        patch.object(skills, "LOCAL_CONFIG_FILE", local_config_file),
    ):
        ops = skills.compute_skill_ops()
        warnings = skills.external_skill_warnings()

    assert len(ops) == 1
    assert ops[0][1] == own_skill
    assert any("duplicate skill name" in w for w in warnings)


def test_stale_skill_warnings_detects_external_broken_link(tmp_path):
    skills_dir = tmp_path / "claude_skills"
    skills_dir.mkdir()
    skills_src = tmp_path / "skills"
    skills_src.mkdir()
    external_repo = tmp_path / "external-repo"
    external_skills_dir = external_repo / ".claude" / "skills"
    external_skills_dir.mkdir(parents=True)
    external_config = tmp_path / "external-skills.json"
    _write_external_config(external_config, {"org/external-repo": ".claude/skills"})
    local_config_file = tmp_path / "CLAUDE.local.md"
    _write_local_config_repos(local_config_file, [("org/external-repo", external_repo)])
    stale = skills_dir / "gone"
    stale.symlink_to(external_skills_dir / "gone")

    with (
        patch.object(skills, "REPO_ROOT", tmp_path),
        patch.object(skills, "SKILLS_DIR", skills_dir),
        patch.object(skills, "EXTERNAL_SKILLS_CONFIG_FILE", external_config),
        patch.object(skills, "LOCAL_CONFIG_FILE", local_config_file),
    ):
        warnings = skills.stale_skill_warnings()

    assert any("Stale" in w for w in warnings)
