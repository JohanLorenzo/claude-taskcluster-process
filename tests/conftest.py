from unittest.mock import MagicMock


def make_run(returncode, stdout=""):
    r = MagicMock()
    r.returncode = returncode
    r.stdout = stdout
    return r
