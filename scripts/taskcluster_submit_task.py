# /// script
# requires-python = ">=3.10"
# dependencies = ["taskcluster[async]"]
# ///
"""Prepare and submit Taskcluster tasks without shelling out to the TC CLI."""

import argparse
import asyncio
import datetime
import json
import logging
import sys
import tempfile
from pathlib import Path

import taskcluster.aio as tc_aio
import taskcluster.utils

logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
log = logging.getLogger(__name__)


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _extract_scopes(task):
    """Return the scopes needed to submit this task."""
    priority = task.get("priority", "lowest")
    provisioner = task["provisionerId"]
    worker = task["workerType"]
    scopes = [
        f"queue:create-task:{priority}:{provisioner}/{worker}",
        f"queue:scheduler-id:{task.get('schedulerId', '-')}",
        "queue:route:checks",
    ]
    scopes.extend(task.get("scopes", []))
    scopes.extend(f"queue:route:{r}" for r in task.get("routes", []))
    return sorted(set(scopes))


def _update_timestamps(task):
    now = _now()
    task["created"] = now.isoformat()
    task["deadline"] = (now + datetime.timedelta(hours=2)).isoformat()
    task["expires"] = (now + datetime.timedelta(days=1)).isoformat()
    for art in task.get("payload", {}).get("artifacts", {}).values():
        if not isinstance(art.get("expires"), str):
            art["expires"] = (now + datetime.timedelta(days=7)).isoformat()


async def cmd_prepare(tc_url, task_id):
    async with tc_aio.createSession() as session:
        queue = tc_aio.Queue({"rootUrl": tc_url}, session=session)

        if task_id:
            log.info("Fetching task definition for %s ...", task_id)
            task = await queue.task(task_id)
        else:
            log.info("Reading task JSON from stdin ...")
            task = json.load(sys.stdin)

    _update_timestamps(task)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="tc-task-", delete=False
    ) as tmp:
        json.dump(task, tmp, indent=2)
        path = tmp.name

    scopes = _extract_scopes(task)

    log.info("\nTask written to: %s", path)
    log.info("\nRequired scopes for submission:")
    for scope in scopes:
        log.info("  --scope '%s'", scope)
    log.info(
        "\nSign in, edit the file if needed (Step 5b), then run:\n"
        "  uv run %s submit %s %s",
        __file__,
        tc_url,
        path,
    )
    return path


async def cmd_submit(tc_url, task_file):
    task = json.loads(await asyncio.to_thread(Path(task_file).read_text))

    task_id = taskcluster.utils.slugId()
    log.info("Submitting task %s ...", task_id)

    async with tc_aio.createSession() as session:
        queue = tc_aio.Queue({"rootUrl": tc_url}, session=session)
        result = await queue.createTask(task_id, task)

    url = f"{tc_url}/tasks/{task_id}"
    log.info("Task created: %s", url)
    log.info("State: %s", result["status"]["state"])
    return task_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    prep = sub.add_parser(
        "prepare", help="Fetch/read task, update timestamps, print scopes"
    )
    prep.add_argument("tc_url", metavar="TC_ROOT_URL")
    src = prep.add_mutually_exclusive_group(required=True)
    src.add_argument("--task-id", metavar="TASK_ID", help="Fetch live task definition")
    src.add_argument(
        "-", dest="read_stdin", action="store_true", help="Read task JSON from stdin"
    )

    sub_submit = sub.add_parser("submit", help="Sign in and submit the prepared task")
    sub_submit.add_argument("tc_url", metavar="TC_ROOT_URL")
    sub_submit.add_argument("task_file", metavar="TASK_FILE")

    args = parser.parse_args()

    if args.command == "prepare":
        asyncio.run(cmd_prepare(args.tc_url, args.task_id))
    elif args.command == "submit":
        asyncio.run(cmd_submit(args.tc_url, args.task_file))


if __name__ == "__main__":
    main()
