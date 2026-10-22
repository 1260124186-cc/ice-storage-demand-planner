"""Demand-charge helpers."""

import math


def billed_demand_kw(daytime_peak_kw, previous_peak_kw, rounding_kw):
    """Ratchet against the historical peak and round the result upward."""
    if not math.isfinite(daytime_peak_kw) or not math.isfinite(previous_peak_kw):
        raise ValueError("peak demand must be finite")
    if not math.isfinite(rounding_kw) or rounding_kw <= 0:
        raise ValueError("demand rounding must be positive")
    raw = max(daytime_peak_kw, previous_peak_kw)
    if raw <= 0:
        return 0.0
    return math.ceil(raw / rounding_kw) * rounding_kw
