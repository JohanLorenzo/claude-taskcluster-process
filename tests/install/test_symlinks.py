from unittest.mock import patch

from install import symlinks

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
        patch.object(symlinks, "REPO_ROOT", tmp_path),
        patch.object(symlinks, "RULES_DIR", rules_target),
    ):
        ops = symlinks.compute_symlink_ops()

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
        patch.object(symlinks, "REPO_ROOT", tmp_path),
        patch.object(symlinks, "RULES_DIR", rules_target),
    ):
        ops = symlinks.compute_symlink_ops()

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
        patch.object(symlinks, "REPO_ROOT", tmp_path),
        patch.object(symlinks, "RULES_DIR", rules_target),
    ):
        ops = symlinks.compute_symlink_ops()

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
        patch.object(symlinks, "REPO_ROOT", tmp_path),
        patch.object(symlinks, "RULES_DIR", rules_target),
    ):
        ops = symlinks.compute_symlink_ops()

    assert ops[0][0] == "replace_file"


# ---------------------------------------------------------------------------
# _replace_file_warnings
# ---------------------------------------------------------------------------


def test_replace_file_warnings_returns_warning_per_op(tmp_path):
    src = tmp_path / "src.md"
    target = tmp_path / "target.md"
    src.write_text("x")
    target.write_text("y")
    warnings = symlinks.replace_file_warnings([("replace_file", src, target)])
    assert len(warnings) == 1
    assert "regular file" in warnings[0]


def test_replace_file_warnings_empty_for_other_ops(tmp_path):
    src = tmp_path / "src.md"
    target = tmp_path / "target.md"
    assert symlinks.replace_file_warnings([("create", src, target)]) == []
    assert symlinks.replace_file_warnings([("noop", src, target)]) == []


# ---------------------------------------------------------------------------
# _stale_symlink_warnings
# ---------------------------------------------------------------------------


def test_stale_symlink_warnings_detects_broken_link(tmp_path):
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    stale = rules_dir / "gone.md"
    stale.symlink_to(tmp_path / "nonexistent.md")
    with patch.object(symlinks, "RULES_DIR", rules_dir):
        warnings = symlinks.stale_symlink_warnings()
    assert any("Stale" in w for w in warnings)


def test_stale_symlink_warnings_empty_when_no_rules_dir(tmp_path):
    with patch.object(symlinks, "RULES_DIR", tmp_path / "missing"):
        assert symlinks.stale_symlink_warnings() == []


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
