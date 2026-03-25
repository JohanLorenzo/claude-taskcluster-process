import asyncio
import importlib.util
import json
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_SCRIPT = Path(__file__).parents[2] / "scripts/taskcluster_local_test.py"
spec = importlib.util.spec_from_file_location("taskcluster_local_test", _SCRIPT)
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)

run = _mod.run
_resolve_image_task_id = _mod._resolve_image_task_id  # noqa: SLF001

_TASK = {
    "provisionerId": "code-analysis-1",
    "workerType": "linux-gw-gcp",
    "payload": {
        "image": {
            "type": "task-image",
            "path": "public/image.tar.zst",
            "taskId": {"task-reference": "<docker-image>"},
        }
    },
    "metadata": {"name": "build-bot"},
    "dependencies": [],
    "requires": "all-completed",
}

_GRAPH = {
    "build-bot": {
        "label": "build-bot",
        "task": _TASK,
        "dependencies": {"docker-image": "docker-image-taskboot"},
    },
    "docker-image-taskboot": {
        "label": "docker-image-taskboot",
        "task": {},
        "dependencies": {},
        "optimization": {
            "index-search": [
                "code-analysis.cache.pr.docker-images.v2.taskboot.hash.abc123"
            ]
        },
    },
}


def _make_index(task_id="IMAGE-TASK-ID"):
    index = AsyncMock()
    index.findTask.return_value = {"taskId": task_id}
    return index


def _run_resolve(tc_url, task_label, graph, index_task_id="IMAGE-TASK-ID"):
    @asynccontextmanager
    async def mock_session():
        yield MagicMock()

    with (
        patch.object(_mod.tc_aio, "createSession", mock_session),
        patch.object(_mod.tc_aio, "Index", return_value=_make_index(index_task_id)),
    ):
        return asyncio.run(_resolve_image_task_id(tc_url, task_label, graph))


def test_resolve_finds_cached_image():
    task_id = _run_resolve("https://tc.example.com", "build-bot", _GRAPH)
    assert task_id == "IMAGE-TASK-ID"


def test_resolve_tries_index_paths():
    @asynccontextmanager
    async def mock_session():
        yield MagicMock()

    index = _make_index()
    with (
        patch.object(_mod.tc_aio, "createSession", mock_session),
        patch.object(_mod.tc_aio, "Index", return_value=index),
    ):
        asyncio.run(
            _resolve_image_task_id("https://tc.example.com", "build-bot", _GRAPH)
        )
    index.findTask.assert_awaited_once_with(
        "code-analysis.cache.pr.docker-images.v2.taskboot.hash.abc123"
    )


def test_resolve_raises_if_no_docker_image_dep():
    graph = {
        "my-task": {
            "label": "my-task",
            "task": {},
            "dependencies": {},
        }
    }
    with pytest.raises(RuntimeError, match="no 'docker-image' dependency"):
        _run_resolve("https://tc.example.com", "my-task", graph)


def test_resolve_raises_if_not_in_index():
    @asynccontextmanager
    async def mock_session():
        yield MagicMock()

    index = AsyncMock()
    index.findTask.side_effect = Exception("not found")
    with (
        patch.object(_mod.tc_aio, "createSession", mock_session),
        patch.object(_mod.tc_aio, "Index", return_value=index),
        pytest.raises(RuntimeError, match="No cached image found"),
    ):
        asyncio.run(
            _resolve_image_task_id("https://tc.example.com", "build-bot", _GRAPH)
        )


def test_run_invokes_load_task(tmp_path):
    params = tmp_path / "params.yml"
    params.write_text("tasks_for: github-pull-request\n")

    tg_result = MagicMock()
    tg_result.stdout = json.dumps(_GRAPH)

    load_result = MagicMock()

    @asynccontextmanager
    async def mock_session():
        yield MagicMock()

    with (
        patch.object(_mod, "_resolve_image_task_id", return_value="IMG-ID"),
        patch.object(_mod.tc_aio, "createSession", mock_session),
        patch.object(
            _mod.subprocess,
            "run",
            side_effect=[tg_result, load_result],
        ) as mock_run,
    ):
        asyncio.run(
            run(
                "https://tc.example.com",
                "build-bot",
                str(params),
                "/path/to/taskgraph",
                [],
            )
        )

    expected_calls = 2
    calls = mock_run.call_args_list
    assert len(calls) == expected_calls
    tg_cmd = calls[0][0][0]
    assert "taskgraph" in tg_cmd
    assert "target-graph" in tg_cmd
    load_cmd = calls[1][0][0]
    assert "load-task" in load_cmd
    assert "task-id=IMG-ID" in " ".join(load_cmd)


def test_run_raises_if_label_not_in_graph(tmp_path):
    params = tmp_path / "params.yml"
    params.write_text("")
    tg_result = MagicMock()
    tg_result.stdout = json.dumps(
        {"other-task": {"label": "other-task", "task": {}, "dependencies": {}}}
    )

    with (
        patch.object(_mod.subprocess, "run", return_value=tg_result),
        pytest.raises(RuntimeError, match="not in graph"),
    ):
        asyncio.run(
            run("https://tc.example.com", "missing-label", str(params), "/tg", [])
        )


def test_run_passes_volumes(tmp_path):
    params = tmp_path / "params.yml"
    params.write_text("")
    tg_result = MagicMock()
    tg_result.stdout = json.dumps(_GRAPH)

    @asynccontextmanager
    async def mock_session():
        yield MagicMock()

    with (
        patch.object(_mod, "_resolve_image_task_id", return_value="IMG"),
        patch.object(_mod.tc_aio, "createSession", mock_session),
        patch.object(
            _mod.subprocess, "run", side_effect=[tg_result, MagicMock()]
        ) as mock_run,
    ):
        asyncio.run(
            run(
                "https://tc.example.com",
                "build-bot",
                str(params),
                "/tg",
                ["./checkout:/builds/worker/checkouts/vcs"],
            )
        )
    load_cmd = mock_run.call_args_list[1][0][0]
    assert "--volume=./checkout:/builds/worker/checkouts/vcs" in load_cmd
