import argparse
import logging
import sys

from .constants import LOCAL_CONFIG_FILE
from .local_config import generate_local_config
from .plan import apply_changes, plan_changes, preview_changes
from .tools import check_tools

logger = logging.getLogger(__name__)


def main(args=None):
    parser = argparse.ArgumentParser(description="Install Claude Code hooks and rules.")
    parser.add_argument(
        "search_root",
        nargs="?",
        metavar="PATH",
        help="Root path to search for repos (prompted if omitted).",
    )
    args = parser.parse_args(args)
    logging.basicConfig(level=logging.DEBUG, format="%(message)s", stream=sys.stdout)
    check_tools()
    if not LOCAL_CONFIG_FILE.exists():
        generate_local_config(search_root=args.search_root)
    plan = plan_changes(search_root=args.search_root)
    preview_changes(plan)
    if not plan.has_changes:
        logger.info("\nAlready up to date.")
        sys.exit(0)
    if input("\nApply changes? [y/N]: ").strip().lower() != "y":
        logger.info("No changes made.")
        sys.exit(0)
    apply_changes(plan)
