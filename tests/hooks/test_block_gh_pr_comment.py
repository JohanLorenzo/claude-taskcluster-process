from hooks.block_gh_pr_comment import check


def test_gh_pr_comment_blocked():
    allowed, reason = check({"command": "gh pr comment 1 --body hi"})
    assert not allowed
    assert "comment" in reason.lower()


def test_gh_issue_comment_blocked():
    allowed, _ = check({"command": "gh issue comment 1 --body hi"})
    assert not allowed


def test_gh_pr_review_blocked():
    allowed, _ = check({"command": "gh pr review 1 --approve"})
    assert not allowed


def test_gh_pr_review_comment_blocked():
    allowed, _ = check({"command": "gh pr review 1 --comment --body lgtm"})
    assert not allowed


def test_gh_pr_close_with_comment_blocked():
    allowed, _ = check({"command": "gh pr close 1 -c 'not needed'"})
    assert not allowed


def test_gh_pr_close_without_comment_allowed():
    assert check({"command": "gh pr close 1"}) == (True, "")


def test_gh_api_reply_to_review_comment_blocked():
    allowed, reason = check(
        {"command": ("gh api repos/org/repo/pulls/1/comments/2/replies -f body=hi")}
    )
    assert not allowed
    assert "comments" in reason.lower() or "reviews" in reason.lower()


def test_gh_api_post_comment_with_method_blocked():
    allowed, _ = check(
        {"command": "gh api repos/org/repo/issues/1/comments --method POST -f body=hi"}
    )
    assert not allowed


def test_gh_api_dash_x_post_comment_blocked():
    allowed, _ = check(
        {"command": "gh api repos/org/repo/pulls/1/reviews -X POST -f body=hi"}
    )
    assert not allowed


def test_gh_api_graphql_mutation_comment_blocked():
    allowed, _ = check(
        {
            "command": (
                "gh api graphql -f query='mutation { addComment(input: {}) { "
                "clientMutationId } }'"
            )
        }
    )
    assert not allowed


def test_gh_api_get_comments_allowed():
    assert check({"command": "gh api repos/org/repo/pulls/1/comments"}) == (True, "")


def test_gh_api_get_comments_with_explicit_method_allowed():
    allowed, _ = check(
        {"command": "gh api repos/org/repo/pulls/1/comments -X GET -f per_page=100"}
    )
    assert allowed


def test_gh_api_graphql_query_comments_allowed():
    allowed, _ = check(
        {
            "command": (
                "gh api graphql -f query='query { repository { pullRequest { "
                "comments { nodes { body } } } } }'"
            )
        }
    )
    assert allowed


def test_gh_pr_create_draft_allowed():
    allowed, _ = check(
        {"command": "gh pr create --draft --title t --body b --base main"}
    )
    assert allowed


def test_gh_pr_edit_body_allowed():
    assert check({"command": "gh pr edit 1 --body 'new description'"}) == (True, "")


def test_gh_pr_view_comments_allowed():
    assert check({"command": "gh pr view 1 --comments"}) == (True, "")


def test_body_text_mentioning_comment_allowed():
    allowed, _ = check(
        {
            "command": (
                "gh pr create --draft --title t "
                "--body 'Use gh pr comment to reply, not this PR.'"
            )
        }
    )
    assert allowed


def test_chained_command_blocked():
    allowed, _ = check(
        {"command": "git push -u origin HEAD && gh pr comment 1 --body done"}
    )
    assert not allowed


def test_non_gh_command_allowed():
    assert check({"command": "git status"}) == (True, "")
