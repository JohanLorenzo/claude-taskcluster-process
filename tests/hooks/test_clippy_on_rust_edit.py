import logging
from unittest.mock import MagicMock, patch

from hooks.clippy_on_rust_edit import check


def test_rust_file_runs_clippy():
    mock_result = MagicMock()
    mock_result.returncode = 0
    with patch(
        "hooks.clippy_on_rust_edit.subprocess.run", return_value=mock_result
    ) as mock_run:
        check({"file_path": "/some/path/main.rs"})
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == "cargo"
    assert "clippy" in args


def test_python_file_skips_clippy():
    with patch("hooks.clippy_on_rust_edit.subprocess.run") as mock_run:
        check({"file_path": "/some/path/main.py"})
    mock_run.assert_not_called()


def test_no_file_path_skips_clippy():
    with patch("hooks.clippy_on_rust_edit.subprocess.run") as mock_run:
        check({})
    mock_run.assert_not_called()


def test_clippy_failure_logs_warning(caplog):

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = "error: some clippy warning\n"
    mock_result.stderr = ""
    with (
        caplog.at_level(logging.WARNING),
        patch("hooks.clippy_on_rust_edit.subprocess.run", return_value=mock_result),
    ):
        check({"file_path": "/some/lib.rs"})
    assert "error" in caplog.text
