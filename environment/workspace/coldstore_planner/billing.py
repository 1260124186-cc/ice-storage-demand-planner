"""Legacy demand-charge calculation."""


def billed_demand_kw(daytime_peak_kw, previous_peak_kw, rounding_kw):
    return max(daytime_peak_kw, previous_peak_kw)
