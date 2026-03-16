import logging

import pytest


@pytest.fixture(autouse=True)
def reset_logging():
    """Clear logging handlers between tests so basicConfig re-applies fresh each run."""
    root = logging.getLogger()
    root.handlers.clear()
    yield
    root.handlers.clear()
