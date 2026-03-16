import sys

from .constants import LOCAL_CONFIG_FILE
from .local_config import generate_local_config
from .plan import apply_changes, plan_changes, preview_changes
from .tools import check_tools


def main():
    check_tools()
    if not LOCAL_CONFIG_FILE.exists():
        generate_local_config()
    plan = plan_changes()
    preview_changes(plan)
    if not plan.has_changes:
        print("\nAlready up to date.")
        sys.exit(0)
    if input("\nApply changes? [y/N]: ").strip().lower() != "y":
        print("No changes made.")
        sys.exit(0)
    apply_changes(plan)
