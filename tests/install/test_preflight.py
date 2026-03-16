from unittest.mock import patch

from install import preflight

# ---------------------------------------------------------------------------
# _old_shell_hook_warnings
# ---------------------------------------------------------------------------


def test_old_shell_hook_warnings_notes_replaceable_hooks(tmp_path):
    old_hooks_dir = tmp_path / "hooks"
    old_hooks_dir.mkdir()
    (old_hooks_dir / "block-no-verify.sh").write_text("#!/bin/bash\n")
    repo_root = tmp_path / "repo"
    (repo_root / "hooks").mkdir(parents=True)
    (repo_root / "hooks" / "block_no_verify.py").write_text("# py")

    with (
        patch.object(preflight, "CLAUDE_DIR", tmp_path),
        patch.object(preflight, "REPO_ROOT", repo_root),
    ):
        warnings = preflight._old_shell_hook_warnings()

    assert any("block-no-verify.sh" in w for w in warnings)


def test_old_shell_hook_warnings_empty_when_no_hooks_dir(tmp_path):
    with patch.object(preflight, "CLAUDE_DIR", tmp_path):
        assert preflight._old_shell_hook_warnings() == []


# ---------------------------------------------------------------------------
# _check_preflight_warnings (integration)
# ---------------------------------------------------------------------------


def test_preflight_rules_dir_is_file(tmp_path):
    rules_as_file = tmp_path / "rules_dir"
    rules_as_file.write_text("oops")
    with patch.object(preflight, "RULES_DIR", rules_as_file):
        _, errors = preflight._check_preflight_warnings([])
    assert any("not a directory" in e for e in errors)
