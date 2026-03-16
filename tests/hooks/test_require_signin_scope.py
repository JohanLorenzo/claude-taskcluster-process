from hooks.require_signin_scope import check


def test_signin_with_scope_allowed():
    assert check({"command": "taskcluster signin --scope 'queue:*' --expires 1h"}) == (
        True,
        "",
    )


def test_signin_without_scope_blocked():
    allowed, reason = check({"command": "taskcluster signin"})
    assert not allowed
    assert reason


def test_signin_with_flags_but_no_scope_blocked():
    allowed, reason = check({"command": "taskcluster signin --expires 1h"})
    assert not allowed
    assert reason


def test_other_taskcluster_command_allowed():
    assert check({"command": "taskcluster task log abc123"}) == (True, "")
