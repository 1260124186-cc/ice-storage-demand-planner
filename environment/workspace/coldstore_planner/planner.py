"""Price-band demonstration scheduler retained from the prototype."""

from .billing import billed_demand_kw
from .storage import advance_inventory


def solve(data):
    periods = data["periods"]
    storage = data["storage"]
    demand = data["demand"]
    prices = sorted(float(period["price_per_kwh"]) for period in periods)
    low_cut = prices[max(0, len(prices) // 3 - 1)]
    high_cut = prices[min(len(prices) - 1, (2 * len(prices)) // 3)]
    capacity = float(storage["capacity_kwh_th"])
    step = float(storage["inventory_step_kwh_th"])
    start = float(storage["initial_kwh_th"])
    rows = []
    energy_cost = 0.0

    for hour, period in enumerate(periods):
        price = float(period["price_per_kwh"])
        load = float(period["cooling_load_kw_th"])
        if price <= low_cut:
            end = min(capacity, start + 2.0 * step)
        elif price >= high_cut:
            end = max(0.0, start - 2.0 * step)
        else:
            end = start
        if end >= start:
            charge = end - start
            discharge = 0.0
        else:
            charge = 0.0
            discharge = start - end
        next_storage, served = advance_inventory(
            start,
            charge,
            discharge,
            storage["charge_efficiency"],
            storage["discharge_efficiency"],
            storage["standing_loss_per_h"],
        )
        direct = load - served
        chiller_output = direct + charge
        grid_power = chiller_output / float(data["cop"])
        energy_cost += grid_power * price
        rows.append(
            {
                "hour": hour,
                "cooling_load_kw_th": load,
                "storage_start_kwh_th": start,
                "charge_kwh_th": charge,
                "discharge_kwh_th": discharge,
                "direct_chiller_kw_th": direct,
                "chiller_output_kw_th": chiller_output,
                "grid_power_kw": grid_power,
                "storage_end_kwh_th": next_storage,
            }
        )
        start = next_storage

    daytime_peak = max(row["grid_power_kw"] for row in rows)
    billed = billed_demand_kw(
        daytime_peak,
        float(demand["previous_peak_kw"]),
        float(demand["rounding_kw"]),
    )
    demand_charge = billed * float(demand["charge_per_kw"])
    return {
        "site_id": data["site_id"],
        "schedule": rows,
        "summary": {
            "energy_cost": energy_cost,
            "daytime_peak_kw": daytime_peak,
            "billed_demand_kw": billed,
            "demand_charge": demand_charge,
            "total_cost": energy_cost + demand_charge,
            "terminal_storage_kwh_th": start,
        },
    }
