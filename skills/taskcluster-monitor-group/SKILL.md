---
name: taskcluster-monitor-group
description: >-
  Monitor a Taskcluster CI group to completion and report failures.
  TRIGGER when: a decision task ID is available and CI needs to be watched
  (e.g. after pushing a branch, after submitting a task, or when asked to
  monitor/poll/watch CI results). Do NOT trigger for one-off task status
  checks — only when waiting for an entire group to finish.
allowed-tools: Bash
argument-hint: "<TC_ROOT_URL> <DECISION_TASK_ID>"
---

# Monitor Taskcluster Group

The user's argument: **$ARGUMENTS**

Run the monitoring script in the background:

```bash
uv run ~/.claude/skills/taskcluster-monitor-group/scripts/taskcluster_monitor_group.py <TC_ROOT_URL> <DECISION_TASK_ID>
```

Report the final outcome: summarise task states and paste log excerpts for failures.
