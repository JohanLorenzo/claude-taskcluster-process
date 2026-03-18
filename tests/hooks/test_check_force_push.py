from unittest.mock import patch

from hooks.check_force_push import check
from tests.helpers import make_run


def _mock_push(is_fork):
    def side_effect(cmd, **kwargs):
        if "repo" in cmd and "view" in cmd:
            return make_run(0, ("true" if is_fork else "false") + "\n")
        if "remote" in cmd and "get-url" in cmd:
            return make_run(0, "https://github.com/some/repo.git\n")
        return make_run(0)

    return side_effect


def test_force_push_to_upstream_blocked():
    with patch(
        "hooks.check_force_push.subprocess.run",
        side_effect=_mock_push(is_fork=False),
    ):
        allowed, reason = check(
            {"command": "git push origin feature --force-with-lease"}, cwd="/tmp"
        )
    assert not allowed
    assert "upstream" in reason


def test_force_push_to_fork_allowed():
    with patch(
        "hooks.check_force_push.subprocess.run",
        side_effect=_mock_push(is_fork=True),
    ):
        assert check(
            {"command": "git push origin worktree-taskgraph --force-with-lease"},
            cwd="/tmp",
        ) == (True, "")


def test_non_force_push_always_allowed():
    assert check({"command": "git push origin feature"}, cwd="/tmp") == (True, "")


def test_non_push_always_allowed():
    assert check({"command": "git status"}) == (True, "")
