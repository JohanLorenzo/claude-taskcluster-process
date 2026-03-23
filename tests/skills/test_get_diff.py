import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.helpers import make_run

_SCRIPT = Path(__file__).parents[2] / "skills/review-taskgraph/scripts/get_diff.py"
spec = importlib.util.spec_from_file_location("get_diff", _SCRIPT)
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)
get_diff = _mod.get_diff
_detect_pr_range = _mod._detect_pr_range  # noqa: SLF001
_detect_base_range = _mod._detect_base_range  # noqa: SLF001


def test_github_pr_url(tmp_path):
    with patch(
        "subprocess.run", return_value=make_run(0, stdout="diff output\n")
    ) as mock_run:
        result = get_diff("https://github.com/owner/repo/pull/42")
    mock_run.assert_called_once_with(
        ["gh", "pr", "diff", "42", "--repo", "owner/repo"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result == "diff output\n"


def test_phabricator_d_prefix():
    with patch(
        "subprocess.run", return_value=make_run(0, stdout="phab diff\n")
    ) as mock_run:
        result = get_diff("D12345")
    mock_run.assert_called_once_with(
        ["moz-phab", "patch", "--raw", "D12345"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result == "phab diff\n"


def test_phabricator_full_url():
    with patch(
        "subprocess.run", return_value=make_run(0, stdout="phab diff\n")
    ) as mock_run:
        result = get_diff("https://phabricator.services.mozilla.com/D12345")
    mock_run.assert_called_once_with(
        ["moz-phab", "patch", "--raw", "D12345"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result == "phab diff\n"


def test_commit_range():
    with patch(
        "subprocess.run", return_value=make_run(0, stdout="range diff\n")
    ) as mock_run:
        result = get_diff("main..HEAD")
    mock_run.assert_called_once_with(
        ["git", "diff", "main..HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result == "range diff\n"


def test_no_args_uncommitted():
    with patch(
        "subprocess.run", return_value=make_run(0, stdout="local diff\n")
    ) as mock_run:
        result = get_diff(None)
    mock_run.assert_called_once_with(
        ["git", "diff", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result == "local diff\n"


def test_detect_pr_range_returns_diff_and_description():
    pr_json = (
        '{"baseRefName": "master", "url": "https://github.com/org/repo/pull/1",'
        ' "headRefName": "my-branch"}'
    )
    diff_content = "diff --git a/foo.py\n+change\n"
    calls = [
        make_run(0, stdout=pr_json),  # gh pr view
        make_run(0, stdout="abc123\n"),  # git merge-base origin/master HEAD
        make_run(0, stdout=diff_content),  # git diff abc123..HEAD
    ]
    with patch("subprocess.run", side_effect=calls):
        diff, description = _detect_pr_range()
    assert diff == diff_content
    assert "https://github.com/org/repo/pull/1" in description
    assert "my-branch" in description
    assert "master" in description


def test_detect_pr_range_returns_none_when_no_pr():
    with patch("subprocess.run", return_value=make_run(1)):
        commit_range, description = _detect_pr_range()
    assert commit_range is None
    assert description is None


def test_detect_base_range_returns_diff_and_description():
    diff_content = "diff --git a/foo.py\n+change\n"
    calls = [
        make_run(0),  # git rev-parse origin/master — exists
        make_run(0, stdout=diff_content),  # git diff origin/master..HEAD
    ]
    with patch("subprocess.run", side_effect=calls):
        diff, description = _detect_base_range()
    assert diff == diff_content
    assert "origin/master" in description


def test_detect_base_range_skips_empty_diff():
    diff_content = "diff --git a/foo.py\n+change\n"
    calls = [
        make_run(0),  # git rev-parse origin/master — exists
        make_run(0, stdout=""),  # git diff origin/master..HEAD — empty
        make_run(0),  # git rev-parse origin/main — exists
        make_run(0, stdout=diff_content),  # git diff origin/main..HEAD — has content
    ]
    with patch("subprocess.run", side_effect=calls):
        diff, description = _detect_base_range()
    assert diff == diff_content
    assert "origin/main" in description


def test_detect_base_range_returns_none_when_no_base_found():
    with patch("subprocess.run", return_value=make_run(1)):
        commit_range, description = _detect_base_range()
    assert commit_range is None
    assert description is None


def test_no_args_detects_pr_when_no_uncommitted_changes(capsys):
    pr_json = (
        '{"baseRefName": "master", "url": "https://github.com/org/repo/pull/1",'
        ' "headRefName": "my-branch"}'
    )
    diff_content = "diff --git a/foo.py\n+change\n"
    calls = [
        make_run(0, stdout=""),  # git diff HEAD — empty
        make_run(0, stdout=pr_json),  # gh pr view
        make_run(0, stdout="abc123\n"),  # git merge-base origin/master HEAD
        make_run(0, stdout=diff_content),  # git diff abc123..HEAD
    ]
    with patch("subprocess.run", side_effect=calls):
        result = get_diff(None)
    assert result == diff_content
    captured = capsys.readouterr()
    assert "https://github.com/org/repo/pull/1" in captured.err


def test_no_args_falls_back_to_origin_master_when_no_pr(capsys):
    diff_content = "diff --git a/bar.py\n+change\n"
    calls = [
        make_run(0, stdout=""),  # git diff HEAD — empty
        make_run(1),  # gh pr view — no PR
        make_run(0),  # git rev-parse origin/master — exists
        make_run(0, stdout=diff_content),  # git diff origin/master..HEAD
    ]
    with patch("subprocess.run", side_effect=calls):
        result = get_diff(None)
    assert result == diff_content
    assert "origin/master" in capsys.readouterr().err


def test_no_args_exits_when_truly_nothing():
    calls = [
        make_run(0, stdout=""),  # git diff HEAD — empty
        make_run(1),  # gh pr view — no PR
        make_run(1),  # git rev-parse origin/master — not found
        make_run(1),  # git rev-parse origin/main — not found
        make_run(1),  # git rev-parse upstream/master — not found
        make_run(1),  # git rev-parse upstream/main — not found
    ]
    with (
        patch("subprocess.run", side_effect=calls),
        pytest.raises(SystemExit) as exc,
    ):
        get_diff(None)
    assert exc.value.code == 1


def test_empty_diff_exits_1():
    with (
        patch("subprocess.run", return_value=make_run(0, stdout="")),
        pytest.raises(SystemExit) as exc,
    ):
        get_diff(None)
    assert exc.value.code == 1


def test_command_failure_exits_1():
    with (
        patch("subprocess.run", return_value=make_run(1, stderr="error")),
        pytest.raises(SystemExit) as exc,
    ):
        get_diff(None)
    assert exc.value.code == 1
