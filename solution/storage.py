"""Ice-storage state transition helpers."""


def advance_inventory(
    start_kwh_th,
    charge_kwh_th,
    discharge_kwh_th,
    charge_efficiency,
    discharge_efficiency,
    standing_loss_per_h,
    max_charge_kw_th=None,
    max_discharge_kw_th=None,
):
    """Return ``(end_kwh_th, load_served_kwh_th)`` for one hourly step."""
    values = (
        start_kwh_th,
        charge_kwh_th,
        discharge_kwh_th,
        charge_efficiency,
        discharge_efficiency,
        standing_loss_per_h,
    )
    if any(value < 0 for value in values):
        raise ValueError("storage quantities must be non-negative")
    if charge_kwh_th > 0 and discharge_kwh_th > 0:
        raise ValueError("simultaneous charging and discharging is not allowed")
    if not (0 < charge_efficiency <= 1 and 0 < discharge_efficiency <= 1):
        raise ValueError("storage efficiencies must be in (0, 1]")
    if not (0 <= standing_loss_per_h < 1):
        raise ValueError("standing loss must be in [0, 1)")
    if max_charge_kw_th is not None and charge_kwh_th > max_charge_kw_th:
        raise ValueError("charge exceeds the hourly limit")
    if max_discharge_kw_th is not None and discharge_kwh_th > max_discharge_kw_th:
        raise ValueError("discharge exceeds the hourly limit")

    available = start_kwh_th * (1.0 - standing_loss_per_h)
    end = available + charge_efficiency * charge_kwh_th - discharge_kwh_th
    served = discharge_efficiency * discharge_kwh_th
    if end < 0:
        raise ValueError("storage inventory cannot become negative")
    return end, served
