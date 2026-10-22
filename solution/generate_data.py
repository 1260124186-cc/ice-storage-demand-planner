"""Generate the fixed-seed demonstration cases shipped with the task."""

import json
import random
from pathlib import Path


SEED = 20261022


def main() -> None:
    rng = random.Random(SEED)
    base_loads = [40.0, 55.0, 70.0, 84.0, 78.0, 66.0, 52.0, 36.0]
    prices = [0.32, 0.38, 1.25, 1.40, 1.32, 0.74, 0.46, 0.30]
    periods = [
        {
            "cooling_load_kw_th": round(max(0.0, load + rng.uniform(-2.0, 2.0)), 1),
            "price_per_kwh": price,
        }
        for load, price in zip(base_loads, prices, strict=True)
    ]
    day = {
        "site_id": "changshu-plant-c2",
        "cop": 3.1,
        "chiller_capacity_kw_th": 88.0,
        "storage": {
            "capacity_kwh_th": 60.0,
            "inventory_step_kwh_th": 5.0,
            "initial_kwh_th": 10.0,
            "terminal_kwh_th": 10.0,
            "max_charge_kw_th": 24.0,
            "max_discharge_kw_th": 30.0,
            "charge_efficiency": 0.9,
            "discharge_efficiency": 0.95,
            "standing_loss_per_h": 0.01,
        },
        "demand": {
            "previous_peak_kw": 20.0,
            "rounding_kw": 5.0,
            "charge_per_kw": 14.0,
        },
        "periods": periods,
    }
    root = Path(__file__).resolve().parents[1]
    target = root / "environment" / "workspace" / "data" / "day.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(day, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    edge = {
        "site_id": "demo-edge",
        "cop": 2.5,
        "chiller_capacity_kw_th": 60.0,
        "storage": {
            "capacity_kwh_th": 20.0,
            "inventory_step_kwh_th": 5.0,
            "initial_kwh_th": 5.0,
            "terminal_kwh_th": 5.0,
            "max_charge_kw_th": 10.0,
            "max_discharge_kw_th": 10.0,
            "charge_efficiency": 1.0,
            "discharge_efficiency": 1.0,
            "standing_loss_per_h": 0.0,
        },
        "demand": {
            "previous_peak_kw": 0.0,
            "rounding_kw": 1.0,
            "charge_per_kw": 0.0,
        },
        "periods": [
            {"cooling_load_kw_th": 30.0, "price_per_kwh": 1.0},
            {"cooling_load_kw_th": 30.0, "price_per_kwh": 1.0},
        ],
    }
    edge_target = root / "solution" / "testdata" / "edge.json"
    edge_target.parent.mkdir(parents=True, exist_ok=True)
    edge_target.write_text(json.dumps(edge, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
