"""Legacy storage transition used by the demonstration scheduler."""


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
    end = start_kwh_th + charge_kwh_th - discharge_kwh_th
    return end, discharge_kwh_th
