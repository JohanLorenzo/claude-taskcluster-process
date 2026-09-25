import json
from unittest.mock import patch

from hooks.review_pr_description import check, check_author_edit, find_heuristic_issues
from tests.helpers import make_run

CLEAN_BODY = "Short clean body that explains why this change is needed."
PYTEST_BODY = "Ran the suite locally.\n\n15 passed, 0 failed.\npytest -q"
INFLATED_ADJECTIVES = (
    "pivotal",
    "groundbreaking",
    "exceptional",
    "outstanding",
    "remarkable",
    "stellar",
    "incredible",
    "amazing",
    "fantastic",
    "tremendous",
)


def _mock_branch(name):
    def side_effect(cmd, **kwargs):
        return make_run(0, f"{name}\n")

    return side_effect


def _mock_pr_view(returncode, body=""):
    def side_effect(cmd, **kwargs):
        return make_run(returncode, body)

    return side_effect


def test_non_pr_command_passes(tmp_path):
    assert check(
        {"command": "git status"}, cwd="/repo", session_id="s1", cache_dir=tmp_path
    ) == ("allow", "")


def test_unparseable_command_passes(tmp_path):
    with patch(
        "hooks.review_pr_description.subprocess.run",
        side_effect=_mock_branch("feature"),
    ):
        decision, message = check(
            {"command": 'gh pr create --title "x"'},
            cwd="/repo",
            session_id="s1",
            cache_dir=tmp_path,
        )
    assert (decision, message) == ("allow", "")


def test_first_create_blocks(tmp_path):
    with patch(
        "hooks.review_pr_description.subprocess.run",
        side_effect=_mock_branch("feature"),
    ):
        decision, message = check(
            {"command": f'gh pr create --title "x" --body "{CLEAN_BODY}"'},
            cwd="/repo",
            session_id="s1",
            cache_dir=tmp_path,
        )
    assert decision == "block"
    assert "pr-description" in message


def test_second_clean_create_passes(tmp_path):
    command = {"command": f'gh pr create --title "x" --body "{CLEAN_BODY}"'}
    with patch(
        "hooks.review_pr_description.subprocess.run",
        side_effect=_mock_branch("feature"),
    ):
        check(command, cwd="/repo", session_id="s1", cache_dir=tmp_path)
        decision, message = check(
            command, cwd="/repo", session_id="s1", cache_dir=tmp_path
        )
    assert (decision, message) == ("allow", "")


def test_second_create_with_pytest_output_warns_without_blocking(tmp_path):
    first = {"command": f'gh pr create --title "x" --body "{CLEAN_BODY}"'}
    second = {"command": f'gh pr create --title "x" --body "{PYTEST_BODY}"'}
    with patch(
        "hooks.review_pr_description.subprocess.run",
        side_effect=_mock_branch("feature"),
    ):
        check(first, cwd="/repo", session_id="s1", cache_dir=tmp_path)
        decision, message = check(
            second, cwd="/repo", session_id="s1", cache_dir=tmp_path
        )
    assert decision == "warn"
    assert "CI" in message or "test output" in message


def test_body_file_is_read(tmp_path):
    body_file = tmp_path / "body.md"
    body_file.write_text(CLEAN_BODY)
    with patch(
        "hooks.review_pr_description.subprocess.run",
        side_effect=_mock_branch("feature"),
    ):
        decision, _ = check(
            {"command": f'gh pr create --title "x" --body-file {body_file}'},
            cwd=str(tmp_path),
            session_id="s1",
            cache_dir=tmp_path,
        )
    assert decision == "block"


def test_heredoc_body_is_parsed(tmp_path):
    command = f'gh pr create --title "x" --body "$(cat <<\'EOF\'\n{CLEAN_BODY}\nEOF\n)"'
    with patch(
        "hooks.review_pr_description.subprocess.run",
        side_effect=_mock_branch("feature"),
    ):
        decision, _ = check(
            {"command": command}, cwd="/repo", session_id="s1", cache_dir=tmp_path
        )
    assert decision == "block"


def test_moz_phab_test_plan_is_covered(tmp_path):
    command = f'moz-phab submit --no-wip --single HEAD --test-plan "{CLEAN_BODY}"'
    decision, _ = check(
        {"command": command}, cwd="/repo", session_id="s1", cache_dir=tmp_path
    )
    assert decision == "block"


def test_state_is_kept_in_injected_cache_dir(tmp_path):
    with patch(
        "hooks.review_pr_description.subprocess.run",
        side_effect=_mock_branch("feature"),
    ):
        check(
            {"command": f'gh pr create --title "x" --body "{CLEAN_BODY}"'},
            cwd="/repo",
            session_id="s1",
            cache_dir=tmp_path,
        )
    state_file = tmp_path / "s1.json"
    assert state_file.exists()
    state = json.loads(state_file.read_text())
    assert "/repo|feature" in state["reviewed"]


def test_no_session_id_fails_open(tmp_path):
    assert check(
        {"command": f'gh pr create --title "x" --body "{CLEAN_BODY}"'},
        cwd="/repo",
        cache_dir=tmp_path,
    ) == ("allow", "")


def test_author_edit_drops_line_blocks():
    stored = "Line A\nLine B"
    remote = "Line A\nLine B\nAuthor added this note."
    new_body = "Line A\nLine B changed"
    with patch(
        "hooks.review_pr_description.subprocess.run",
        side_effect=_mock_pr_view(0, remote),
    ):
        allowed, reason, author_lines = check_author_edit(42, new_body, stored, "/repo")
    assert not allowed
    assert "Author added this note." in reason
    assert author_lines == ["Author added this note."]


def test_author_edit_keeps_line_passes():
    stored = "Line A\nLine B"
    remote = "Line A\nLine B\nAuthor added this note."
    new_body = "Line A\nLine B\nAuthor added this note.\nMore evidence."
    with patch(
        "hooks.review_pr_description.subprocess.run",
        side_effect=_mock_pr_view(0, remote),
    ):
        allowed, reason, author_lines = check_author_edit(42, new_body, stored, "/repo")
    assert allowed
    assert reason == ""
    assert author_lines == ["Author added this note."]


def test_author_edit_no_stored_body_passes():
    allowed, reason, author_lines = check_author_edit(42, "New body", None, "/repo")
    assert allowed
    assert reason == ""
    assert author_lines == []


def test_author_edit_gh_failure_passes():
    with patch(
        "hooks.review_pr_description.subprocess.run", side_effect=_mock_pr_view(1, "")
    ):
        allowed, reason, author_lines = check_author_edit(
            42, "New body", "stored", "/repo"
        )
    assert allowed
    assert reason == ""
    assert author_lines == []


def test_full_edit_flow_blocks_on_dropped_author_line(tmp_path):
    session_id = "s-edit"
    state_path = tmp_path / f"{session_id}.json"
    state_path.write_text(
        json.dumps(
            {"reviewed": ["/repo|42"], "pr_bodies": {"/repo|42": "Line A\nLine B"}}
        )
    )
    remote = "Line A\nLine B\nAuthor note."
    command = 'gh pr edit 42 --body "Line A\nLine B changed"'
    with patch(
        "hooks.review_pr_description.subprocess.run",
        side_effect=_mock_pr_view(0, remote),
    ):
        decision, message = check(
            {"command": command}, cwd="/repo", session_id=session_id, cache_dir=tmp_path
        )
    assert decision == "block"
    assert "Author note." in message


def test_all_inflated_adjectives_are_flagged():
    for word in INFLATED_ADJECTIVES:
        issues = find_heuristic_issues(f"This change is {word}.")
        assert issues == ["uses inflated adjectives"], word


def test_inflated_adjectives_are_case_insensitive():
    assert find_heuristic_issues("STELLAR work on this migration.") == [
        "uses inflated adjectives"
    ]


def test_inflated_adjective_word_boundary_excludes_substring():
    assert find_heuristic_issues("The outstandingly good result stands.") == []
