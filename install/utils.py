import difflib


def _unified_diff(old_text, new_text, fromfile, tofile):
    return list(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=fromfile,
            tofile=tofile,
        )
    )
