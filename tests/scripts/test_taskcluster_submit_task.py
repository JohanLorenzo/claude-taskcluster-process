import asyncio
import importlib.util
import io
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_SCRIPT = Path(__file__).parents[2] / "scripts/taskcluster_submit_task.py"
spec = importlib.util.spec_from_file_location("taskcluster_submit_task", _SCRIPT)
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)

cmd_prepare = _mod.cmd_prepare
cmd_submit = _mod.cmd_submit
_extract_scopes = _mod._extract_scopes  # noqa: SLF001
_signin = _mod._signin  # noqa: SLF001
_update_timestamps = _mod._update_timestamps  # noqa: SLF001

_TASK = {
    "provisionerId": "code-analysis-1",
    "workerType": "linux-gw-gcp",
    "schedulerId": "code-analysis-level-1",
    "priority": "low",
    "routes": ["checks"],
    "scopes": ["assume:repo:github.com/foo:pull-request"],
    "payload": {},
    "metadata": {"name": "test", "description": "", "owner": "x@x.com", "source": ""},
    "dependencies": [],
    "requires": "all-completed",
}

_FAKE_CREDS = {
    "clientId": "mozilla-auth0/ad|Mozilla-LDAP|testuser/claude-submit-abc1234",
    "accessToken": "fake-token",
}


def _make_queue(task=None):
    queue = AsyncMock()
    queue.task.return_value = task or dict(_TASK)
    queue.createTask.return_value = {"status": {"state": "pending", "taskId": "NEWID"}}
    return queue


def _run_prepare(tc_url, task_id=None, stdin_task=None):
    @asynccontextmanager
    async def mock_session():
        yield MagicMock()

    with (
        patch.object(_mod.tc_aio, "createSession", mock_session),
        patch.object(
            _mod.tc_aio, "Queue", return_value=_make_queue(stdin_task or dict(_TASK))
        ),
    ):
        if stdin_task:
            with patch.object(_mod.sys, "stdin", io.StringIO(json.dumps(stdin_task))):
                return asyncio.run(cmd_prepare(tc_url, task_id))
        return asyncio.run(cmd_prepare(tc_url, task_id))


def _run_submit(task_file, signin_creds=None):
    @asynccontextmanager
    async def mock_session():
        yield MagicMock()

    queue = _make_queue()
    with (
        patch.object(_mod.tc_aio, "createSession", mock_session),
        patch.object(_mod.tc_aio, "Queue", return_value=queue),
        patch.object(_mod.taskcluster.utils, "slugId", return_value="NEWID"),
        patch.object(_mod, "_signin", return_value=signin_creds or _FAKE_CREDS),
    ):
        task_id = asyncio.run(cmd_submit("https://tc.example.com", task_file))
    return task_id, queue


def test_prepare_from_task_id_writes_temp_file():
    path = _run_prepare("https://tc.example.com", task_id="TASKID")
    assert path.startswith("/")
    assert Path(path).exists()
    task = json.loads(Path(path).read_text())
    assert "created" in task
    assert "deadline" in task


def test_prepare_from_stdin_writes_temp_file():
    path = _run_prepare("https://tc.example.com", stdin_task=dict(_TASK))
    assert Path(path).exists()


def test_prepare_updates_timestamps():
    path = _run_prepare("https://tc.example.com", task_id="TASKID")
    task = json.loads(Path(path).read_text())
    assert task["created"] != ""
    assert task["deadline"] > task["created"]
    assert task["expires"] > task["deadline"]


def test_extract_scopes_includes_create_task():
    scopes = _extract_scopes(_TASK)
    assert "queue:create-task:low:code-analysis-1/linux-gw-gcp" in scopes


def test_extract_scopes_includes_scheduler():
    scopes = _extract_scopes(_TASK)
    assert "queue:scheduler-id:code-analysis-level-1" in scopes


def test_extract_scopes_includes_task_scopes():
    scopes = _extract_scopes(_TASK)
    assert "assume:repo:github.com/foo:pull-request" in scopes


def test_extract_scopes_includes_routes():
    scopes = _extract_scopes(_TASK)
    assert "queue:route:checks" in scopes


def test_submit_calls_signin_with_correct_scopes(tmp_path):
    task_file = tmp_path / "task.json"
    task_file.write_text(json.dumps(_TASK))
    with (
        patch.object(_mod.tc_aio, "createSession", MagicMock()),
        patch.object(_mod.tc_aio, "Queue", return_value=_make_queue()),
        patch.object(_mod.taskcluster.utils, "slugId", return_value="NEWID"),
        patch.object(_mod, "_signin", return_value=_FAKE_CREDS) as mock_signin,
    ):
        asyncio.run(cmd_submit("https://tc.example.com", str(task_file)))
    mock_signin.assert_called_once()
    tc_url, scopes = mock_signin.call_args[0]
    assert tc_url == "https://tc.example.com"
    assert "queue:create-task:low:code-analysis-1/linux-gw-gcp" in scopes


def test_submit_uses_signin_credentials(tmp_path):
    task_file = tmp_path / "task.json"
    task_file.write_text(json.dumps(_TASK))
    task_id, queue = _run_submit(str(task_file))
    assert task_id == "NEWID"
    queue.createTask.assert_awaited_once()


def test_signin_parses_creds_from_stdout():
    stdout = (
        "export TASKCLUSTER_CLIENT_ID='mozilla-auth0/ad|Mozilla-LDAP|user/cli-abc'\n"
        "export TASKCLUSTER_ACCESS_TOKEN='secret-token'\n"
        "export TASKCLUSTER_ROOT_URL='https://tc.example.com'\n"
    )
    with patch.object(_mod.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout)
        creds = _signin("https://tc.example.com", ["queue:create-task:low:p/w"])
    assert creds["clientId"] == "mozilla-auth0/ad|Mozilla-LDAP|user/cli-abc"
    assert creds["accessToken"] == "secret-token"
    assert "certificate" not in creds


def test_signin_parses_certificate_when_present():
    stdout = (
        "export TASKCLUSTER_CLIENT_ID='x/y'\n"
        "export TASKCLUSTER_ACCESS_TOKEN='tok'\n"
        "export TASKCLUSTER_CERTIFICATE='cert-json'\n"
    )
    with patch.object(_mod.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout)
        creds = _signin("https://tc.example.com", [])
    assert creds["certificate"] == "cert-json"


def test_signin_passes_scopes_to_cli():
    stdout = (
        "export TASKCLUSTER_CLIENT_ID='x/y'\nexport TASKCLUSTER_ACCESS_TOKEN='tok'\n"
    )
    with patch.object(_mod.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(stdout=stdout)
        _signin("https://tc.example.com", ["scope:a", "scope:b"])
    cmd = mock_run.call_args[0][0]
    assert "--scope" in cmd
    assert "scope:a" in cmd
    assert "scope:b" in cmd
    assert "--expires" in cmd
    assert "5m" in cmd


def test_prepare_prints_temp_file_path(caplog):
    with caplog.at_level(logging.INFO):
        path = _run_prepare("https://tc.example.com", task_id="TASKID")
    assert path in caplog.text


@pytest.mark.parametrize("has_stdin", [True, False])
def test_prepare_no_scopes_printed(has_stdin, caplog):
    """prepare no longer prints scopes (submit handles sign-in now)."""
    with caplog.at_level(logging.INFO):
        if has_stdin:
            _run_prepare("https://tc.example.com", stdin_task=dict(_TASK))
        else:
            _run_prepare("https://tc.example.com", task_id="TASKID")
    assert "--scope" not in caplog.text
