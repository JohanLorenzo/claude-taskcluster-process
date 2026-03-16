import logging
import sys

from .constants import LOCAL_CONFIG_FILE
from .local_config import generate_local_config
from .plan import apply_changes, plan_changes, preview_changes
from .tools import check_tools

logger = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=logging.DEBUG, format="%(message)s", stream=sys.stdout)
    check_tools()
    if not LOCAL_CONFIG_FILE.exists():
        generate_local_config()
    plan = plan_changes()
    preview_changes(plan)
    if not plan.has_changes:
        logger.info("\nAlready up to date.")
        sys.exit(0)
    if input("\nApply changes? [y/N]: ").strip().lower() != "y":
        logger.info("No changes made.")
        sys.exit(0)
    apply_changes(plan)
