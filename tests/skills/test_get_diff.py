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
