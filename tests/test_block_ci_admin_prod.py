from hooks.block_ci_admin_prod import check


def test_apply_firefoxci_blocked():
    allowed, reason = check(
        {"command": "uv run ci-admin apply --environment firefoxci"}
    )
    assert not allowed
    assert reason


def test_apply_firefoxci_equals_blocked():
    allowed, reason = check({"command": "ci-admin apply --environment=firefoxci"})
    assert not allowed
    assert reason


def test_diff_firefoxci_allowed():
    assert check({"command": "uv run ci-admin diff --environment firefoxci"}) == (
        True,
        "",
    )


def test_apply_staging_allowed():
    assert check({"command": "ci-admin apply --environment staging"}) == (True, "")


def test_unrelated_command_allowed():
    assert check({"command": "echo hello"}) == (True, "")
