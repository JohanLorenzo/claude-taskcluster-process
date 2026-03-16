from unittest.mock import patch

from hooks.check_push_target import check
from tests.helpers import make_run


def _mock_run_factory(remote_url, is_fork_str):
    def side_effect(cmd, **kwargs):
        if "get-url" in cmd:
            return make_run(0, remote_url + "\n")
        return make_run(0, is_fork_str + "\n")

    return side_effect


def test_fork_remote_allowed():
    with patch(
        "hooks.check_push_target.subprocess.run",
        side_effect=_mock_run_factory(
            "git@github.com:JohanLorenzo/taskgraph.git", "true"
        ),
    ):
        assert check({"command": "git push fork feature-branch"}, cwd="/tmp") == (
            True,
            "",
        )


def test_non_fork_origin_blocked():
    with patch(
        "hooks.check_push_target.subprocess.run",
        side_effect=_mock_run_factory(
            "git@github.com:taskcluster/taskgraph.git", "false"
        ),
    ):
        allowed, reason = check(
            {"command": "git push origin feature-branch"}, cwd="/tmp"
        )
    assert not allowed
    assert "not a fork" in reason


def test_origin_that_is_fork_allowed():
    with patch(
        "hooks.check_push_target.subprocess.run",
        side_effect=_mock_run_factory(
            "https://github.com/JohanLorenzo/taskgraph.git", "true"
        ),
    ):
        assert check({"command": "git push origin feature-branch"}, cwd="/tmp") == (
            True,
            "",
        )


def test_non_push_command_allowed():
    assert check({"command": "git status"}) == (True, "")


def test_push_defaults_to_origin_fork():
    with patch(
        "hooks.check_push_target.subprocess.run",
        side_effect=_mock_run_factory(
            "git@github.com:JohanLorenzo/taskgraph.git", "true"
        ),
    ):
        assert check({"command": "git push"}, cwd="/tmp") == (True, "")


def test_push_defaults_to_origin_non_fork():
    with patch(
        "hooks.check_push_target.subprocess.run",
        side_effect=_mock_run_factory(
            "git@github.com:taskcluster/taskgraph.git", "false"
        ),
    ):
        allowed, _ = check({"command": "git push"}, cwd="/tmp")
    assert not allowed
