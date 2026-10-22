"""Command-line entry point for the prototype planner."""

import json
import sys

from .model import InputError, load_input
from .planner import solve


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: python -m coldstore_planner INPUT.json OUTPUT.json", file=sys.stderr)
        return 2
    try:
        result = solve(load_input(args[0]))
    except (InputError, KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        print(f"planning failed: {exc}", file=sys.stderr)
        return 1
    try:
        with open(args[1], "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except OSError as exc:
        print(f"cannot write output: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
