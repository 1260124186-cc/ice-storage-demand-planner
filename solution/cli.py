"""Command-line entry point for the ice-storage planner."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from .model import InputError, load_input
from .planner import solve


def _write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, allow_nan=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: python -m coldstore_planner INPUT.json OUTPUT.json", file=sys.stderr)
        return 2
    try:
        data = load_input(args[0])
        result = solve(data)
    except (InputError, ValueError, OSError) as exc:
        print(f"planning failed: {exc}", file=sys.stderr)
        return 1
    try:
        _write_atomic(Path(args[1]), result)
    except (OSError, TypeError, ValueError) as exc:
        print(f"cannot write output: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
