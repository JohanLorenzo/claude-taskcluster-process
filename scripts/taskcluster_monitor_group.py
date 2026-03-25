# /// script
# requires-python = ">=3.10"
# dependencies = ["taskcluster[async]"]
# ///
"""Monitor a Taskcluster CI group to completion, printing logs of failures."""

import argparse
import asyncio
import logging
import sys

import aiohttp
import taskcluster.aio as tc_aio

log = logging.getLogger(__name__)


async def _interval_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def _task_state(queue, task_id):
    return (await queue.status(task_id))["status"]["state"]


async def _group_tasks(queue, decision_task_id):
    tasks, continuation = [], None
    while True:
        resp = await queue.listTaskGroup(
            decision_task_id,
            **({"continuationToken": continuation} if continuation else {}),
        )
        tasks.extend(resp["tasks"])
        continuation = resp.get("continuationToken")
        if not continuation:
            return tasks


async def _show_task_log(queue, session, task_id, name):
    log.info("\n=== FAILED: %s (%s) ===", name, task_id)
    try:
        artifact = await queue.getLatestArtifact(
            task_id, "public/logs/live_backing.log"
        )
        async with session.get(artifact["url"]) as r:
            log.info(await r.text(errors="replace"))
    except (aiohttp.ClientError, KeyError) as e:
        log.info("Could not fetch log: %s", e)


async def run(tc_url, decision_task_id):
    async with tc_aio.createSession() as session:
        queue = tc_aio.Queue({"rootUrl": tc_url}, session=session)

        log.info("Polling decision task %s ...", decision_task_id)
        while (state := await _task_state(queue, decision_task_id)) in (
            "pending",
            "running",
        ):
            await _interval_sleep(15)

        if state != "completed":
            await _show_task_log(queue, session, decision_task_id, "Decision Task")
            return 1

        log.info("Polling task group ...")
        while True:
            tasks = await _group_tasks(queue, decision_task_id)
            states = {t["status"]["state"] for t in tasks}
            if not states & {"pending", "running", "unscheduled"}:
                break
            await _interval_sleep(30)

        log.info("\n=== Final group status ===")
        for state in sorted(states):
            count = sum(1 for t in tasks if t["status"]["state"] == state)
            log.info("  %s: %d", state, count)

        failed = [t for t in tasks if t["status"]["state"] in ("failed", "exception")]
        await asyncio.gather(
            *[
                _show_task_log(
                    queue, session, t["status"]["taskId"], t["task"]["metadata"]["name"]
                )
                for t in failed
            ]
        )

        return 1 if failed else 0


def main():
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tc_url", metavar="TC_ROOT_URL")
    parser.add_argument("decision_task_id", metavar="DECISION_TASK_ID")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.tc_url, args.decision_task_id)))


if __name__ == "__main__":
    main()
