from hooks.block_no_verify import check


def test_plain_commit_allowed():
    assert check({"command": 'git commit -m "msg"'}) == (True, "")


def test_no_verify_blocked():
    allowed, reason = check({"command": 'git commit --no-verify -m "msg"'})
    assert not allowed
    assert reason


def test_no_verify_in_message_allowed():
    assert check({"command": 'git commit -m "no-verify in msg"'}) == (True, "")


def test_non_git_allowed():
    assert check({"command": "echo hello"}) == (True, "")
