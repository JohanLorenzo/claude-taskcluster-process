import copy
import json
import logging
import sys

from .constants import (
    HOOKS_CONFIG_FILE,
    PERMISSIONS_CONFIG_FILE,
    REPO_ROOT,
    SANDBOX_CONFIG_FILE,
    SETTINGS_CONFIG_FILE,
    SETTINGS_FILE,
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


def load_permissions_config():
    if not PERMISSIONS_CONFIG_FILE.exists():
        return []
    with PERMISSIONS_CONFIG_FILE.open() as f:
        config = json.load(f)
    return list(config.get("static", []))


def load_permissions_deny():
    if not PERMISSIONS_CONFIG_FILE.exists():
        return []
    with PERMISSIONS_CONFIG_FILE.open() as f:
        config = json.load(f)
    return list(config.get("deny", []))


def load_static_settings():
    if not SETTINGS_CONFIG_FILE.exists():
        return {}
    with SETTINGS_CONFIG_FILE.open() as f:
        return json.load(f)


def load_sandbox_config(repo_paths=None):
    if not SANDBOX_CONFIG_FILE.exists():
        return None
    with SANDBOX_CONFIG_FILE.open() as f:
        data = json.load(f)
    sandbox = data["sandbox"]
    existing = sandbox.setdefault("filesystem", {}).get("allowWrite", [])
    sandbox["filesystem"]["allowWrite"] = list(repo_paths or []) + existing
    return sandbox


def _merge_rules(perms, key, rules):
    existing = set(perms.get(key, []))
    perms[key] = sorted(existing | set(rules))


def compute_new_settings(
    old_settings, hooks_config, repo_paths, managed=None, overrides=None
):
    new_settings = copy.deepcopy(old_settings)
    new_settings["hooks"] = hooks_config
    perms = new_settings.setdefault("permissions", {})
    if repo_paths:
        perms["additionalDirectories"] = repo_paths
    for key, rules in (managed or {}).items():
        if rules:
            _merge_rules(perms, key, rules)
    for key, value in (overrides or {}).items():
        if value is not None:
            new_settings[key] = value
    return new_settings


def settings_diff(old, new):
    return unified_diff(
        json.dumps(old, indent=2),
        json.dumps(new, indent=2),
        str(SETTINGS_FILE),
        str(SETTINGS_FILE) + " (new)",
    )
