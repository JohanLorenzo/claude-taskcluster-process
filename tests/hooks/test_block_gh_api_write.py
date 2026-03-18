from hooks.block_gh_api_write import check


def test_gh_api_default_get_allowed():
    assert check({"command": "gh api repos/org/repo/check-runs"}) == (True, "")


def test_gh_api_explicit_get_allowed():
    assert check({"command": "gh api repos/org/repo --method GET"}) == (True, "")


def test_gh_api_post_blocked():
    allowed, reason = check({"command": "gh api repos/org/repo --method POST"})
    assert not allowed
    assert "write" in reason.lower()


def test_gh_api_delete_blocked():
    allowed, _ = check({"command": "gh api repos/org/repo --method DELETE"})
    assert not allowed


def test_gh_api_patch_blocked():
    allowed, _ = check({"command": "gh api repos/org/repo --method PATCH"})
    assert not allowed


def test_gh_api_put_blocked():
    allowed, _ = check({"command": "gh api repos/org/repo --method PUT"})
    assert not allowed


def test_non_gh_api_command_allowed():
    assert check({"command": "gh pr view 1"}) == (True, "")


def test_non_gh_command_allowed():
    assert check({"command": "git status"}) == (True, "")
