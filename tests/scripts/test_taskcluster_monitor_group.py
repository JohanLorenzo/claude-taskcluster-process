import asyncio
import importlib.util
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_SCRIPT = Path(__file__).parents[2] / "scripts/taskcluster_monitor_group.py"
spec = importlib.util.spec_from_file_location("taskcluster_monitor_group", _SCRIPT)
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)

run = _mod.run

_LOG_ARTIFACT = "public/logs/live_backing.log"


def _make_task(task_id, name, state):
    return {
        "status": {"taskId": task_id, "state": state},
        "task": {"metadata": {"name": name}},
    }


def _make_queue(decision_state="completed", group_task_states=None, *, paginate=False):
    if group_task_states is None:
        group_task_states = [("T1", "lint", "completed")]

    queue = AsyncMock()
    queue.status.return_value = {"status": {"state": decision_state}}

    all_tasks = [_make_task(tid, name, state) for tid, name, state in group_task_states]
    if paginate:
        queue.listTaskGroup.side_effect = [
            {"tasks": all_tasks[:1], "continuationToken": "tok"},
            {"tasks": all_tasks[1:]},
        ]
    else:
        queue.listTaskGroup.return_value = {"tasks": all_tasks}

    queue.getLatestArtifact.return_value = {
        "storageType": "s3",
        "url": "https://example.com/log.txt",
    }
    return queue


def _make_session(log_content="task log output\n"):
    response = AsyncMock()
    response.text = AsyncMock(return_value=log_content)

    @asynccontextmanager
    async def _get(*args, **kwargs):
        yield response

    session = MagicMock()
    session.get = _get
    return session


def _run(queue, session):
    @asynccontextmanager
    async def mock_create_session():
        yield session

    with (
        patch.object(_mod.tc_aio, "createSession", mock_create_session),
        patch.object(_mod.tc_aio, "Queue", return_value=queue),
        patch.object(_mod, "_interval_sleep", new_callable=AsyncMock),
    ):
        return asyncio.run(run("https://tc.example.com", "DECISION"))


def test_all_completed_exits_zero():
    code = _run(_make_queue(), _make_session())
    assert code == 0


def test_decision_task_failure_fetches_log_and_exits_one():
    queue = _make_queue(decision_state="failed")
    code = _run(queue, _make_session())
    assert code == 1
    queue.getLatestArtifact.assert_awaited_once_with("DECISION", _LOG_ARTIFACT)


def test_failed_task_in_group_fetches_log_and_exits_one():
    queue = _make_queue(
        decision_state="completed",
        group_task_states=[("T1", "test-bot", "failed")],
    )
    code = _run(queue, _make_session())
    assert code == 1
    queue.getLatestArtifact.assert_awaited_once_with("T1", _LOG_ARTIFACT)


def test_multiple_failed_tasks_logs_fetched_concurrently(caplog):
    expected_fetch_count = 2
    queue = _make_queue(
        decision_state="completed",
        group_task_states=[
            ("T1", "test-bot", "failed"),
            ("T2", "test-backend", "failed"),
            ("T3", "lint", "completed"),
        ],
    )
    with caplog.at_level(logging.INFO):
        code = _run(queue, _make_session())
    assert code == 1
    assert queue.getLatestArtifact.await_count == expected_fetch_count
    assert "test-bot" in caplog.text
    assert "test-backend" in caplog.text


def test_listtaskgroup_pagination_collects_all_tasks():
    expected_call_count = 2
    queue = _make_queue(
        decision_state="completed",
        group_task_states=[("T1", "lint", "completed"), ("T2", "test", "completed")],
        paginate=True,
    )
    code = _run(queue, _make_session())
    assert code == 0
    assert queue.listTaskGroup.await_count == expected_call_count


def test_group_polled_until_settled():
    expected_call_count = 2
    queue = AsyncMock()
    queue.status.return_value = {"status": {"state": "completed"}}
    queue.listTaskGroup.side_effect = [
        {"tasks": [_make_task("T1", "lint", "running")]},
        {"tasks": [_make_task("T1", "lint", "completed")]},
    ]
    code = _run(queue, _make_session())
    assert code == 0
    assert queue.listTaskGroup.await_count == expected_call_count
