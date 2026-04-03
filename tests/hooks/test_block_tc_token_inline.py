from hooks.block_tc_token_inline import check


def test_inline_token_blocked():
    allowed, reason = check({"command": "TASKCLUSTER_ACCESS_TOKEN=foo ci-admin diff"})
    assert not allowed
    assert reason


def test_inline_token_with_other_vars_blocked():
    allowed, reason = check(
        {
            "command": (
                "TASKCLUSTER_CLIENT_ID='myid' "
                "TASKCLUSTER_ACCESS_TOKEN='TAA5abc' "
                "TASKCLUSTER_ROOT_URL='https://example.com' "
                "uv run ci-admin diff --environment firefoxci"
            )
        }
    )
    assert not allowed
    assert reason


def test_sourcing_creds_file_allowed():
    assert check({"command": "source $TMPDIR/tc-creds.sh && ci-admin diff"}) == (
        True,
        "",
    )


def test_token_in_quoted_string_allowed():
    assert check({"command": 'echo "TASKCLUSTER_ACCESS_TOKEN=foo"'}) == (True, "")


def test_unrelated_command_allowed():
    assert check({"command": "echo hello"}) == (True, "")


def test_no_token_allowed():
    assert check(
        {"command": "TASKCLUSTER_ROOT_URL=https://example.com ci-admin diff"}
    ) == (
        True,
        "",
    )
