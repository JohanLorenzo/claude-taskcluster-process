import copy
import json
import logging
import sys

from .constants import (
    HOOKS_CONFIG_FILE,
    PERMISSIONS_CONFIG_FILE,
    REPO_ROOT,
    SETTINGS_FILE,
    SKILLS_DIR,
)
from .utils import unified_diff

logger = logging.getLogger(__name__)


def load_hooks_config():
    with HOOKS_CONFIG_FILE.open() as f:
        raw = json.load(f)

    def resolve_hooks(hooks_list):
        for entry in hooks_list:
            for hook in entry.get("hooks", []):
                if "command" in hook:
                    hook["command"] = str(REPO_ROOT / hook["command"])
        return hooks_list

    return {event: resolve_hooks(entries) for event, entries in raw.items()}


def load_settings():
    if not SETTINGS_FILE.exists():
        logger.error("ERROR: %s not found.", SETTINGS_FILE)
        sys.exit(1)
    try:
        with SETTINGS_FILE.open() as f:
            return json.load(f)
    except json.JSONDecodeError:
        logger.exception("ERROR: %s is not valid JSON", SETTINGS_FILE)
        sys.exit(1)


_TC_READ_COMMANDS = [
    "taskcluster task def",
    "taskcluster task log",
    "taskcluster task status",
    "taskcluster group list",
    "taskcluster group status",
]
_TC_POLL_COMMANDS = [
    "taskcluster task status",
    "taskcluster group status",
]


def load_permissions_config(repo_paths=None, taskgraph_repo=None):
    if not PERMISSIONS_CONFIG_FILE.exists():
        return []
    with PERMISSIONS_CONFIG_FILE.open() as f:
        config = json.load(f)
    rules = list(config.get("static", []))
    for url in config.get("taskcluster_instances", []):
        rules.extend(
            f"Bash(TASKCLUSTER_ROOT_URL={url} {cmd}:*)" for cmd in _TC_READ_COMMANDS
        )
        rules.extend(
            f"Bash(until TASKCLUSTER_ROOT_URL={url} {cmd}:*)"
            for cmd in _TC_POLL_COMMANDS
        )
    skill_script = (
        f"{SKILLS_DIR}/taskcluster-monitor-group/scripts/taskcluster_monitor_group.py"
    )
    rules.append(f"Bash(uv run {skill_script}:*)")
    git_ops = config.get("git_c_operations", [])
    for path in repo_paths or []:
        rules.extend(f"Bash(git -C {path} {op}:*)" for op in git_ops)
    if taskgraph_repo:
        for extra in config.get("uv_taskgraph_extras", []):
            suffix = f"[{extra}]" if extra else ""
            rules.append(
                f"Bash(uv run --with-editable '{taskgraph_repo}{suffix}' taskgraph:*)"
            )
    return rules


def compute_new_settings(old_settings, hooks_config, repo_paths, managed_allow=None):
    new_settings = copy.deepcopy(old_settings)
    new_settings["hooks"] = hooks_config
    perms = new_settings.setdefault("permissions", {})
    if repo_paths:
        perms["additionalDirectories"] = repo_paths
    if managed_allow:
        existing = set(perms.get("allow", []))
        perms["allow"] = sorted(existing | set(managed_allow))
    return new_settings


def settings_diff(old, new):
    return unified_diff(
        json.dumps(old, indent=2),
        json.dumps(new, indent=2),
        str(SETTINGS_FILE),
        str(SETTINGS_FILE) + " (new)",
    )
