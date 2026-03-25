# /// script
# requires-python = ">=3.10"
# dependencies = ["taskcluster[async]"]
# ///
"""Run a Taskcluster task locally using load-task."""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys

import taskcluster.aio as tc_aio

logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
log = logging.getLogger(__name__)


async def _try_find_task(index, path):
    """Return the taskId at the given index path, or None if not found."""
    try:
        result = await index.findTask(path)
        return result["taskId"]
    except Exception:  # noqa: BLE001
        log.debug("Index path not found: %s", path)
        return None


async def _resolve_image_task_id(tc_url, task_label, graph):
    """Look up the cached docker image task ID for the given task."""
    deps = graph[task_label].get("dependencies", {})
    image_label = deps.get("docker-image")
    if not image_label:
        msg = (
            f"Task '{task_label}' has no 'docker-image' dependency; "
            "cannot resolve image automatically"
        )
        raise RuntimeError(msg)

    index_paths = graph[image_label].get("optimization", {}).get("index-search", [])
    if not index_paths:
        msg = f"Docker image task '{image_label}' has no index-search optimization"
        raise RuntimeError(msg)

    async with tc_aio.createSession() as session:
        index = tc_aio.Index({"rootUrl": tc_url}, session=session)
        for path in index_paths:
            task_id = await _try_find_task(index, path)
            if task_id:
                log.info("Found cached image: %s (%s)", image_label, task_id)
                return task_id

    msg = f"No cached image found for '{image_label}'. Build the docker image first."
    raise RuntimeError(msg)


async def run(tc_url, task_label, params_file, taskgraph_root, volumes):
    log.info("Generating task graph for label '%s' ...", task_label)
    tg_cmd = [
        "uv",
        "run",
        "--with-editable",
        str(taskgraph_root),
        "taskgraph",
        "target-graph",
        "--root",
        "taskcluster",
        "-p",
        str(params_file),
        "--json",
    ]
    result = await asyncio.to_thread(
        subprocess.run, tg_cmd, capture_output=True, text=True, check=True
    )
    graph = json.loads(result.stdout)

    if task_label not in graph:
        available = ", ".join(sorted(graph))
        msg = f"Label '{task_label}' not in graph.\nAvailable: {available}"
        raise RuntimeError(msg)

    task = graph[task_label]["task"]
    image_task_id = await _resolve_image_task_id(tc_url, task_label, graph)

    log.info("Running task locally via load-task ...")
    load_cmd = [
        "uv",
        "run",
        "--with-editable",
        f"{taskgraph_root}[load-image]",
        "taskgraph",
        "load-task",
        "--root",
        "taskcluster",
        "--image",
        f"task-id={image_task_id}",
        *[f"--volume={v}" for v in volumes],
        "-",
    ]
    env = {
        **os.environ,
        "DOCKER_DEFAULT_PLATFORM": "linux/amd64",
        "TASKCLUSTER_ROOT_URL": tc_url,
    }
    await asyncio.to_thread(
        subprocess.run,
        load_cmd,
        input=json.dumps(task),
        env=env,
        check=True,
        text=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tc_url", metavar="TC_ROOT_URL")
    parser.add_argument("task_label", metavar="TASK_LABEL")
    parser.add_argument("--params", required=True, metavar="PARAMS_FILE")
    parser.add_argument(
        "--taskgraph-root",
        required=True,
        metavar="PATH",
        help="Path to the taskgraph repo (for uv --with-editable)",
    )
    parser.add_argument(
        "--volume",
        action="append",
        default=[],
        metavar="HOST:CONTAINER",
        help="Extra volume mounts (e.g. ./checkout:/builds/worker/checkouts/vcs)",
    )
    args = parser.parse_args()
    asyncio.run(
        run(args.tc_url, args.task_label, args.params, args.taskgraph_root, args.volume)
    )


if __name__ == "__main__":
    main()
