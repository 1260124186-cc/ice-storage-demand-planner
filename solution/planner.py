"""Exact day-ahead dispatch over the ice-storage inventory grid."""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING
from typing import Any


def _decimal(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _round_up(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def solve(data: dict[str, Any]) -> dict[str, Any]:
    storage = {key: _decimal(value) for key, value in data["storage"].items()}
    demand = {key: _decimal(value) for key, value in data["demand"].items()}
    periods = [
        {key: _decimal(value) for key, value in period.items()}
        for period in data["periods"]
    ]
    cop = _decimal(data["cop"])
    chiller_capacity = _decimal(data["chiller_capacity_kw_th"])
    step = storage["inventory_step_kwh_th"]
    capacity = storage["capacity_kwh_th"]
    steps = int(capacity / step)
    initial_step = int(storage["initial_kwh_th"] / step)
    terminal_step = int(storage["terminal_kwh_th"] / step)
    loss = storage["standing_loss_per_h"]
    charge_eff = storage["charge_efficiency"]
    discharge_eff = storage["discharge_efficiency"]
    initial_billed = _round_up(
        max(demand["previous_peak_kw"], Decimal(0)), demand["rounding_kw"]
    )

    states: dict[tuple[int, Decimal], tuple[Decimal, tuple[Decimal, ...], tuple[dict[str, Decimal], ...]]] = {
        (initial_step, initial_billed): (Decimal(0), (), ())
    }

    for hour, period in enumerate(periods):
        next_states = {}
        load = period["cooling_load_kw_th"]
        price = period["price_per_kwh"]
        for (current_step, billed), (energy_cost, end_path, rows) in states.items():
            start = Decimal(current_step) * step
            available = start * (Decimal(1) - loss)
            for next_step in range(steps + 1):
                end = Decimal(next_step) * step
                delta = end - available
                if delta >= 0:
                    charge = delta / charge_eff
                    discharge = Decimal(0)
                else:
                    charge = Decimal(0)
                    discharge = -delta
                if charge > storage["max_charge_kw_th"]:
                    continue
                if discharge > storage["max_discharge_kw_th"]:
                    continue
                direct = load - discharge_eff * discharge
                if direct < 0:
                    continue
                chiller_output = direct + charge
                if chiller_output > chiller_capacity:
                    continue
                grid_power = chiller_output / cop
                peak_after = max(billed, _round_up(grid_power, demand["rounding_kw"]))
                new_energy = energy_cost + grid_power * price
                new_path = end_path + (end,)
                row = {
                    "hour": Decimal(hour),
                    "cooling_load_kw_th": load,
                    "storage_start_kwh_th": start,
                    "charge_kwh_th": charge,
                    "discharge_kwh_th": discharge,
                    "direct_chiller_kw_th": direct,
                    "chiller_output_kw_th": chiller_output,
                    "grid_power_kw": grid_power,
                    "storage_end_kwh_th": end,
                }
                key = (next_step, peak_after)
                candidate = (new_energy, new_path, rows + (row,))
                existing = next_states.get(key)
                if existing is None or candidate[:2] < existing[:2]:
                    next_states[key] = candidate
        states = next_states
        if not states:
            raise ValueError("no feasible ice-storage schedule")

    finals = [
        (energy + billed * demand["charge_per_kw"], end_path, billed, rows)
        for (end_step, billed), (energy, end_path, rows) in states.items()
        if end_step == terminal_step
    ]
    if not finals:
        raise ValueError("terminal storage cannot be reached")
    total_cost, end_path, billed_demand, rows = min(finals, key=lambda item: (item[0], item[1]))
    energy_cost = total_cost - billed_demand * demand["charge_per_kw"]

    return {
        "site_id": data["site_id"],
        "schedule": [
            {
                "hour": int(row["hour"]),
                "cooling_load_kw_th": float(row["cooling_load_kw_th"]),
                "storage_start_kwh_th": float(row["storage_start_kwh_th"]),
                "charge_kwh_th": float(row["charge_kwh_th"]),
                "discharge_kwh_th": float(row["discharge_kwh_th"]),
                "direct_chiller_kw_th": float(row["direct_chiller_kw_th"]),
                "chiller_output_kw_th": float(row["chiller_output_kw_th"]),
                "grid_power_kw": float(row["grid_power_kw"]),
                "storage_end_kwh_th": float(row["storage_end_kwh_th"]),
            }
            for row in rows
        ],
        "summary": {
            "energy_cost": float(energy_cost),
            "daytime_peak_kw": float(max(row["grid_power_kw"] for row in rows)),
            "billed_demand_kw": float(billed_demand),
            "demand_charge": float(billed_demand * demand["charge_per_kw"]),
            "total_cost": float(total_cost),
            "terminal_storage_kwh_th": float(end_path[-1]),
        },
    }
