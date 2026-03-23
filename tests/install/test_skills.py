from unittest.mock import patch

from install import skills


def _make_skill(parent, name):
    skill_dir = parent / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("# test skill\n")
    return skill_dir


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
