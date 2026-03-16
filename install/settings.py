import copy
import json
import logging
import sys

from .constants import HOOKS_CONFIG_FILE, REPO_ROOT, SETTINGS_FILE
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


def compute_new_settings(old_settings, hooks_config, repo_paths):
    new_settings = copy.deepcopy(old_settings)
    new_settings["hooks"] = hooks_config
    if repo_paths:
        perms = new_settings.setdefault("permissions", {})
        perms["additionalDirectories"] = repo_paths
    return new_settings


def settings_diff(old, new):
    return unified_diff(
        json.dumps(old, indent=2),
        json.dumps(new, indent=2),
        str(SETTINGS_FILE),
        str(SETTINGS_FILE) + " (new)",
    )
