from hooks.block_gh_pr_close import check


def test_gh_pr_close_plain_blocked():
    allowed, reason = check({"command": "gh pr close 1"})
    assert not allowed
    assert "closing" in reason.lower()


def test_gh_pr_close_with_flag_blocked():
    allowed, _ = check({"command": "gh pr close 1 -c 'not needed' --delete-branch"})
    assert not allowed


def test_gh_pr_close_by_url_blocked():
    allowed, _ = check({"command": "gh pr close https://github.com/org/repo/pull/1"})
    assert not allowed


def test_gh_pr_close_with_env_var_blocked():
    allowed, _ = check({"command": "GH_TOKEN=x gh pr close 1"})
    assert not allowed


def test_chained_gh_pr_close_blocked():
    allowed, _ = check({"command": "git push -u origin HEAD && gh pr close 1"})
    assert not allowed


def test_gh_api_graphql_close_mutation_blocked():
    allowed, _ = check(
        {
            "command": (
                "gh api graphql -f query='mutation { closePullRequest(input: {}) { "
                "clientMutationId } }'"
            )
        }
    )
    assert not allowed


def test_gh_api_patch_state_closed_blocked():
    allowed, _ = check(
        {"command": "gh api -X PATCH repos/org/repo/pulls/1 -f state=closed"}
    )
    assert not allowed


def test_gh_pr_create_allowed():
    allowed, _ = check(
        {"command": "gh pr create --draft --title t --body b --base main"}
    )
    assert allowed


def test_gh_pr_edit_body_allowed():
    assert check({"command": "gh pr edit 1 --body 'new description'"}) == (True, "")


def test_gh_pr_view_allowed():
    assert check({"command": "gh pr view 1"}) == (True, "")


def test_gh_issue_close_allowed():
    assert check({"command": "gh issue close 1"}) == (True, "")


def test_gh_pr_reopen_allowed():
    assert check({"command": "gh pr reopen 1"}) == (True, "")


def test_gh_api_get_pull_allowed():
    assert check({"command": "gh api repos/org/repo/pulls/1"}) == (True, "")


def test_non_gh_command_allowed():
    assert check({"command": "git status"}) == (True, "")
