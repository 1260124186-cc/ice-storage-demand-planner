"""Input loading for the existing planning tool."""

import json


class InputError(ValueError):
    """Raised when the request cannot be loaded."""


def normalize_input(raw):
    if not isinstance(raw, dict):
        raise InputError("input must be an object")
    if not isinstance(raw.get("periods"), list):
        raise InputError("periods must be a list")
    return raw


def load_input(path):
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(str(exc)) from exc
    return normalize_input(raw)
