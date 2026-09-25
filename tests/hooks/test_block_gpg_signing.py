from hooks.block_gpg_signing import check

_COMMIT_SIGNING = {"commit": True, "tag": False}
_NO_SIGNING = {"commit": False, "tag": False}


def _bash(command):
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def test_commit_blocked_with_commit_signing_on():
    allowed, reason = check(_bash("git commit -m x"), _COMMIT_SIGNING)
    assert not allowed
    assert reason


def test_commit_with_path_and_amend_blocked():
    allowed, _ = check(_bash("git -C /r commit --amend"), _COMMIT_SIGNING)
    assert not allowed


def test_absorb_blocked():
    allowed, _ = check(_bash("git absorb"), _COMMIT_SIGNING)
    assert not allowed


def test_rebase_blocked():
    allowed, _ = check(_bash("git rebase main"), _COMMIT_SIGNING)
    assert not allowed


def test_second_segment_blocked():
    allowed, _ = check(_bash("cd x && git commit -m y"), _COMMIT_SIGNING)
    assert not allowed


def test_no_gpg_sign_flag_does_not_bypass_block():
    allowed, _ = check(_bash("git commit --no-gpg-sign -m x"), _COMMIT_SIGNING)
    assert not allowed


def test_tag_sign_flag_always_blocked():
    allowed, _ = check(_bash("git tag -s v1"), _NO_SIGNING)
    assert not allowed


def test_explicit_sign_flag_always_blocked_even_with_signing_off():
    allowed, _ = check(_bash("git commit -S -m x"), _NO_SIGNING)
    assert not allowed


def test_status_allowed():
    assert check(_bash("git status"), _COMMIT_SIGNING) == (True, "")


def test_log_allowed():
    assert check(_bash("git log"), _COMMIT_SIGNING) == (True, "")


def test_tag_list_allowed():
    assert check(_bash("git tag -l"), _COMMIT_SIGNING) == (True, "")


def test_commit_allowed_with_signing_off():
    assert check(_bash("git commit -m x"), _NO_SIGNING) == (True, "")


def test_non_bash_tool_allowed():
    data = {"tool_name": "Edit", "tool_input": {}}
    assert check(data, _COMMIT_SIGNING) == (True, "")


def test_segment_not_starting_with_git_allowed():
    assert check(_bash("echo git commit"), _COMMIT_SIGNING) == (True, "")
