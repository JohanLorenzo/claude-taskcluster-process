import asyncio
import importlib.util
import io
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_SCRIPT = Path(__file__).parents[2] / "scripts/taskcluster_submit_task.py"
spec = importlib.util.spec_from_file_location("taskcluster_submit_task", _SCRIPT)
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)

cmd_prepare = _mod.cmd_prepare
cmd_submit = _mod.cmd_submit
_extract_scopes = _mod._extract_scopes  # noqa: SLF001
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


def _run_submit(task_file):
    @asynccontextmanager
    async def mock_session():
        yield MagicMock()

    queue = _make_queue()
    with (
        patch.object(_mod.tc_aio, "createSession", mock_session),
        patch.object(_mod.tc_aio, "Queue", return_value=queue),
        patch.object(_mod.taskcluster.utils, "slugId", return_value="NEWID"),
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


def test_submit_calls_create_task(tmp_path):
    task_file = tmp_path / "task.json"
    task_file.write_text(json.dumps(_TASK))
    task_id, queue = _run_submit(str(task_file))
    assert task_id == "NEWID"
    queue.createTask.assert_awaited_once()
    call_task_id, call_payload = queue.createTask.call_args[0]
    assert call_task_id == "NEWID"
    assert call_payload["provisionerId"] == "code-analysis-1"


def test_prepare_prints_scopes(tmp_path, caplog):
    with caplog.at_level(logging.INFO):
        _run_prepare("https://tc.example.com", task_id="TASKID")
    assert "queue:create-task:low:code-analysis-1/linux-gw-gcp" in caplog.text


def test_prepare_prints_temp_file_path(tmp_path, caplog):
    with caplog.at_level(logging.INFO):
        path = _run_prepare("https://tc.example.com", task_id="TASKID")
    assert path in caplog.text
