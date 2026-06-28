from __future__ import annotations

import sys

from quality_runner import __version__


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["--version"]:
        print(__version__)
        return 0

    print("quality-runner-mcp scaffold: stdio server is not implemented", file=sys.stderr)
    return 2
