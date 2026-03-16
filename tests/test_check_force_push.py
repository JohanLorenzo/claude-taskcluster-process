from unittest.mock import MagicMock, patch

from hooks.check_force_push import check


def _make_run(returncode, stdout=""):
    r = MagicMock()
    r.returncode = returncode
    r.stdout = stdout
    return r


def _mock_force_push(base_branch, is_ancestor):
    def side_effect(cmd, **kwargs):
        if "pr" in cmd and "view" in cmd:
            return _make_run(0, base_branch + "\n")
        if "merge-base" in cmd:
            return _make_run(0 if is_ancestor else 1)
        return _make_run(0)

    return side_effect


def test_force_push_only_pr_commits_allowed():
    with patch(
        "hooks.check_force_push.subprocess.run",
        side_effect=_mock_force_push("main", is_ancestor=True),
    ):
        assert check(
            {"command": "git push fork feature --force-with-lease"}, cwd="/tmp"
        ) == (True, "")


def test_force_push_rewrites_base_commits_blocked():
    with patch(
        "hooks.check_force_push.subprocess.run",
        side_effect=_mock_force_push("main", is_ancestor=False),
    ):
        allowed, reason = check(
            {"command": "git push fork feature --force"}, cwd="/tmp"
        )
    assert not allowed
    assert "rewrite" in reason


def test_non_force_push_always_allowed():
    assert check({"command": "git push fork feature"}, cwd="/tmp") == (True, "")


def test_non_push_always_allowed():
    assert check({"command": "git status"}) == (True, "")
