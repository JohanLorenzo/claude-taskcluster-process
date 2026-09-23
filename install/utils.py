import difflib
import os
import sys

RED = "\033[31m"
GREEN = "\033[32m"
CYAN = "\033[36m"
BOLD = "\033[1m"
RESET = "\033[0m"


def unified_diff(old_text, new_text, fromfile, tofile):
    return list(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=fromfile,
            tofile=tofile,
        )
    )


def _color_for(line):
    if line.startswith(("---", "+++")):
        return BOLD
    if line.startswith("@@"):
        return CYAN
    if line.startswith("+"):
        return GREEN
    if line.startswith("-"):
        return RED
    return None


def _use_color():
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def format_diff(lines, color=None):
    if color is None:
        color = _use_color()
    if not color:
        return "".join(lines)
    formatted = []
    for line in lines:
        c = _color_for(line)
        if c is None:
            formatted.append(line)
        else:
            formatted.append(f"{c}{line.rstrip(chr(10))}{RESET}\n")
    return "".join(formatted)
