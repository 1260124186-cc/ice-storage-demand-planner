"""Independent checks for the ice-storage day-ahead dispatch planner."""

from __future__ import annotations

import copy
import json
import math
import os
import subprocess
import sys
import tempfile
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

import pytest


WORKSPACE = Path(os.environ.get("PLANNER_WORKSPACE", "/workspace"))
sys.path.insert(0, str(WORKSPACE))


def _d(value):
    """Convert a JSON number to Decimal without carrying binary residue."""
    return Decimal(str(value))


def _ceil_step(value, step):
    """Round a Decimal upward to a multiple of step."""
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def _reference(data):
    """Recompute the optimal schedule by an independent state-space search."""
    storage = data["storage"]
    demand = data["demand"]
    step = _d(storage["inventory_step_kwh_th"])
    capacity = _d(storage["capacity_kwh_th"])
    count = int(capacity / step)
    first_step = int(_d(storage["initial_kwh_th"]) / step)
    last_step = int(_d(storage["terminal_kwh_th"]) / step)
    loss = _d(storage["standing_loss_per_h"])
    charge_eff = _d(storage["charge_efficiency"])
    discharge_eff = _d(storage["discharge_efficiency"])
    rounding = _d(demand["rounding_kw"])
    billed0 = _ceil_step(max(_d(demand["previous_peak_kw"]), Decimal(0)), rounding)
    live = {(first_step, billed0): (Decimal(0), (), ())}

    for hour, period in enumerate(data["periods"]):
        load = _d(period["cooling_load_kw_th"])
        price = _d(period["price_per_kwh"])
        nxt = {}
        for (old_step, billed), (cost, ends, rows) in live.items():
            start = Decimal(old_step) * step
            available = start * (Decimal(1) - loss)
            for new_step in range(count + 1):
                end = Decimal(new_step) * step
                change = end - available
                charge = max(change, Decimal(0)) / charge_eff
                discharge = max(-change, Decimal(0))
                if charge > _d(storage["max_charge_kw_th"]):
                    continue
                if discharge > _d(storage["max_discharge_kw_th"]):
                    continue
                direct = load - discharge_eff * discharge
                if direct < 0:
                    continue
                chiller = direct + charge
                if chiller > _d(data["chiller_capacity_kw_th"]):
                    continue
                grid = chiller / _d(data["cop"])
                peak = max(billed, _ceil_step(grid, rounding))
                new_cost = cost + grid * price
                new_ends = ends + (end,)
                row = {
                    "hour": hour,
                    "cooling_load_kw_th": float(load),
                    "storage_start_kwh_th": float(start),
                    "charge_kwh_th": float(charge),
                    "discharge_kwh_th": float(discharge),
                    "direct_chiller_kw_th": float(direct),
                    "chiller_output_kw_th": float(chiller),
                    "grid_power_kw": float(grid),
                    "storage_end_kwh_th": float(end),
                }
                key = (new_step, peak)
                candidate = (new_cost, new_ends, rows + (row,))
                if key not in nxt or candidate[:2] < nxt[key][:2]:
                    nxt[key] = candidate
        live = nxt

    finals = []
    for (end_step, billed), (energy, ends, rows) in live.items():
        if end_step != last_step:
            continue
        total = energy + billed * _d(demand["charge_per_kw"])
        finals.append((total, ends, billed, energy, rows))
    total, ends, billed, energy, rows = min(finals, key=lambda item: (item[0], item[1]))
    peak = max(_d(row["grid_power_kw"]) for row in rows)
    return {
        "site_id": data["site_id"],
        "schedule": list(rows),
        "summary": {
            "energy_cost": float(energy),
            "daytime_peak_kw": float(peak),
            "billed_demand_kw": float(billed),
            "demand_charge": float(billed * _d(demand["charge_per_kw"])),
            "total_cost": float(total),
            "terminal_storage_kwh_th": float(ends[-1]),
        },
    }


def _run(data, existing=None, cwd=None):
    """Run one planning request and return its status, output text, and directory."""
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "input.json"
        output = root / "result.json"
        source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        if existing is not None:
            output.write_text(existing, encoding="utf-8")
        process = subprocess.run(
            [sys.executable, "-m", "coldstore_planner", str(source), str(output)],
            cwd=str(WORKSPACE if cwd is None else cwd),
            capture_output=True,
            text=True,
            timeout=30,
        )
        payload = output.read_text(encoding="utf-8") if output.exists() else None
        return process.returncode, payload, temporary


def _same_plan(actual, wanted):
    """Return whether two plan payloads agree within numerical tolerance."""
    if actual is None or wanted is None:
        return False
    if actual.get("site_id") != wanted["site_id"]:
        return False
    schedule = actual.get("schedule")
    summary = actual.get("summary")
    if not isinstance(schedule, list) or len(schedule) != len(wanted["schedule"]):
        return False
    if not isinstance(summary, dict):
        return False
    schedule_fields = (
        "cooling_load_kw_th",
        "storage_start_kwh_th",
        "charge_kwh_th",
        "discharge_kwh_th",
        "direct_chiller_kw_th",
        "chiller_output_kw_th",
        "grid_power_kw",
        "storage_end_kwh_th",
    )
    row_matches = []
    for got, want in zip(schedule, wanted["schedule"], strict=True):
        row_matches.append(got.get("hour") == want["hour"])
        row_matches.append(
            all(
                math.isclose(
                    float(got.get(name, math.nan)),
                    float(want[name]),
                    rel_tol=1e-9,
                    abs_tol=1e-9,
                )
                for name in schedule_fields
            )
        )
    summary_fields = (
        "energy_cost",
        "daytime_peak_kw",
        "billed_demand_kw",
        "demand_charge",
        "total_cost",
        "terminal_storage_kwh_th",
    )
    summary_matches = all(
        math.isclose(
            float(summary.get(name, math.nan)),
            float(wanted["summary"][name]),
            rel_tol=1e-9,
            abs_tol=1e-9,
        )
        for name in summary_fields
    )
    return all(row_matches) and summary_matches


def _base_case():
    """Return a compact feasible case used by several checks."""
    return {
        "site_id": "test-plant",
        "cop": 2.0,
        "chiller_capacity_kw_th": 80.0,
        "storage": {
            "capacity_kwh_th": 20.0,
            "inventory_step_kwh_th": 5.0,
            "initial_kwh_th": 5.0,
            "terminal_kwh_th": 5.0,
            "max_charge_kw_th": 20.0,
            "max_discharge_kw_th": 20.0,
            "charge_efficiency": 0.9,
            "discharge_efficiency": 0.95,
            "standing_loss_per_h": 0.01,
        },
        "demand": {
            "previous_peak_kw": 10.0,
            "rounding_kw": 5.0,
            "charge_per_kw": 8.0,
        },
        "periods": [
            {"cooling_load_kw_th": 24.0, "price_per_kwh": 0.3},
            {"cooling_load_kw_th": 48.0, "price_per_kwh": 1.2},
            {"cooling_load_kw_th": 32.0, "price_per_kwh": 0.6},
        ],
    }


def test_c1_charge_efficiency_changes_inventory():
    """Charge efficiency applies only to the energy entering storage."""
    from coldstore_planner.storage import advance_inventory

    end, served = advance_inventory(10.0, 8.0, 0.0, 0.9, 0.95, 0.0)
    assert math.isclose(end, 17.2, rel_tol=0.0, abs_tol=1e-12)
    assert math.isclose(served, 0.0, rel_tol=0.0, abs_tol=1e-12)


def test_c1_discharge_efficiency_changes_served_load():
    """Discharge efficiency determines useful cooling, not inventory withdrawal."""
    from coldstore_planner.storage import advance_inventory

    end, served = advance_inventory(20.0, 0.0, 6.0, 0.9, 0.85, 0.0)
    assert math.isclose(end, 14.0, rel_tol=0.0, abs_tol=1e-12)
    assert math.isclose(served, 5.1, rel_tol=0.0, abs_tol=1e-12)


def test_c1_standing_loss_precedes_flows():
    """Standing loss is applied to opening inventory before hourly flows."""
    from coldstore_planner.storage import advance_inventory

    end, _ = advance_inventory(10.0, 9.0, 0.0, 0.5, 1.0, 0.1)
    assert math.isclose(end, 13.5, rel_tol=0.0, abs_tol=1e-12)


def test_c1_rejects_charge_above_hourly_limit():
    """A charge above the hourly maximum is rejected."""
    from coldstore_planner.storage import advance_inventory

    with pytest.raises(ValueError):
        advance_inventory(0.0, 12.0, 0.0, 0.9, 0.9, 0.0, max_charge_kw_th=10.0)


def test_c2_rounds_demand_up_to_step():
    """A demand above a step boundary is rounded upward."""
    from coldstore_planner.billing import billed_demand_kw

    value = billed_demand_kw(37.1, 12.0, 5.0)
    assert math.isclose(value, 40.0, rel_tol=0.0, abs_tol=1e-12)


def test_c2_previous_peak_sets_ratchet():
    """The previous monthly peak wins when it exceeds today's peak."""
    from coldstore_planner.billing import billed_demand_kw

    value = billed_demand_kw(11.0, 43.0, 5.0)
    assert math.isclose(value, 45.0, rel_tol=0.0, abs_tol=1e-12)


def test_c2_summary_counts_demand_charge_once():
    """The demand charge is one daily charge added to energy cost."""
    case = _base_case()
    case["storage"].update(
        {
            "capacity_kwh_th": 0.0,
            "initial_kwh_th": 0.0,
            "terminal_kwh_th": 0.0,
            "max_charge_kw_th": 0.0,
            "max_discharge_kw_th": 0.0,
        }
    )
    status, payload, _ = _run(case)
    actual = json.loads(payload) if payload is not None else None
    assert status == 0 and actual is not None
    summary = actual["summary"]
    expected_energy = sum(
        row["grid_power_kw"] * period["price_per_kwh"]
        for row, period in zip(actual["schedule"], case["periods"], strict=True)
    )
    assert math.isclose(summary["energy_cost"], expected_energy, rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(
        summary["total_cost"],
        summary["energy_cost"] + summary["demand_charge"],
        rel_tol=1e-9,
        abs_tol=1e-9,
    )


def test_c3_shifts_load_to_limit_demand_peak():
    """A high demand charge drives charging before the two peak hours."""
    case = {
        "site_id": "peak-limited",
        "cop": 1.0,
        "chiller_capacity_kw_th": 80.0,
        "storage": {
            "capacity_kwh_th": 60.0,
            "inventory_step_kwh_th": 10.0,
            "initial_kwh_th": 0.0,
            "terminal_kwh_th": 0.0,
            "max_charge_kw_th": 50.0,
            "max_discharge_kw_th": 60.0,
            "charge_efficiency": 1.0,
            "discharge_efficiency": 1.0,
            "standing_loss_per_h": 0.0,
        },
        "demand": {
            "previous_peak_kw": 0.0,
            "rounding_kw": 10.0,
            "charge_per_kw": 100.0,
        },
        "periods": [
            {"cooling_load_kw_th": 20.0, "price_per_kwh": 0.5},
            {"cooling_load_kw_th": 20.0, "price_per_kwh": 0.5},
            {"cooling_load_kw_th": 80.0, "price_per_kwh": 2.0},
            {"cooling_load_kw_th": 40.0, "price_per_kwh": 1.0},
        ],
    }
    wanted = _reference(case)
    status, payload, _ = _run(case)
    actual = json.loads(payload) if payload is not None else None
    matches = _same_plan(actual, wanted)
    assert status == 0 and matches
    assert actual["summary"]["billed_demand_kw"] <= 50.0


def test_c3_efficiency_can_make_arbitrage_unattractive():
    """Low round-trip efficiency can leave the storage idle despite a price gap."""
    case = _base_case()
    case["cop"] = 1.0
    case["chiller_capacity_kw_th"] = 30.0
    case["storage"].update(
        {
            "capacity_kwh_th": 10.0,
            "inventory_step_kwh_th": 5.0,
            "initial_kwh_th": 0.0,
            "terminal_kwh_th": 0.0,
            "max_charge_kw_th": 10.0,
            "max_discharge_kw_th": 10.0,
            "charge_efficiency": 0.5,
            "discharge_efficiency": 1.0,
            "standing_loss_per_h": 0.0,
        }
    )
    case["demand"].update({"previous_peak_kw": 0.0, "rounding_kw": 1.0, "charge_per_kw": 0.0})
    case["periods"] = [
        {"cooling_load_kw_th": 10.0, "price_per_kwh": 0.8},
        {"cooling_load_kw_th": 10.0, "price_per_kwh": 1.0},
    ]
    wanted = _reference(case)
    status, payload, _ = _run(case)
    actual = json.loads(payload) if payload is not None else None
    matches = _same_plan(actual, wanted)
    assert status == 0 and matches
    assert all(
        abs(row["charge_kwh_th"]) < 1e-12 and abs(row["discharge_kwh_th"]) < 1e-12
        for row in actual["schedule"]
    )


def test_c3_terminal_inventory_is_exact():
    """The final stored energy must equal terminal_kwh_th exactly."""
    case = _base_case()
    case["cop"] = 1.0
    case["storage"].update(
        {
            "capacity_kwh_th": 15.0,
            "inventory_step_kwh_th": 5.0,
            "initial_kwh_th": 5.0,
            "terminal_kwh_th": 10.0,
            "max_charge_kw_th": 10.0,
            "max_discharge_kw_th": 10.0,
            "charge_efficiency": 1.0,
            "discharge_efficiency": 1.0,
            "standing_loss_per_h": 0.0,
        }
    )
    case["demand"].update({"previous_peak_kw": 0.0, "rounding_kw": 1.0, "charge_per_kw": 0.0})
    case["periods"] = [
        {"cooling_load_kw_th": 5.0, "price_per_kwh": 1.0},
        {"cooling_load_kw_th": 5.0, "price_per_kwh": 1.0},
    ]
    status, payload, _ = _run(case)
    actual = json.loads(payload) if payload is not None else None
    assert status == 0 and actual is not None
    assert math.isclose(
        actual["summary"]["terminal_storage_kwh_th"],
        10.0,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    assert [row["storage_end_kwh_th"] for row in actual["schedule"]] == [0.0, 10.0]


def test_c3_rejects_unreachable_terminal_inventory():
    """An unreachable terminal inventory must fail without an output artifact."""
    case = _base_case()
    case["storage"].update(
        {
            "capacity_kwh_th": 10.0,
            "initial_kwh_th": 0.0,
            "terminal_kwh_th": 5.0,
            "max_charge_kw_th": 0.0,
            "max_discharge_kw_th": 0.0,
        }
    )
    case["periods"] = [{"cooling_load_kw_th": 5.0, "price_per_kwh": 1.0}]
    status, payload, _ = _run(case)
    assert status != 0 and payload is None


def test_c3_schema_and_load_balance():
    """A successful plan has the specified fields and balances each hour."""
    case = _base_case()
    wanted = _reference(case)
    status, payload, _ = _run(case)
    actual = json.loads(payload) if payload is not None else None
    matches = _same_plan(actual, wanted)
    assert status == 0 and matches
    expected_fields = {
        "hour",
        "cooling_load_kw_th",
        "storage_start_kwh_th",
        "charge_kwh_th",
        "discharge_kwh_th",
        "direct_chiller_kw_th",
        "chiller_output_kw_th",
        "grid_power_kw",
        "storage_end_kwh_th",
    }
    assert all(set(row) == expected_fields for row in actual["schedule"])
    assert all(
        math.isclose(
            row["direct_chiller_kw_th"]
            + case["storage"]["discharge_efficiency"] * row["discharge_kwh_th"],
            row["cooling_load_kw_th"],
            rel_tol=1e-9,
            abs_tol=1e-9,
        )
        for row in actual["schedule"]
    )


def test_c3_shipped_sample_matches_reference():
    """The generated demonstration day matches an independent optimum."""
    source = WORKSPACE / "data" / "day.json"
    case = json.loads(source.read_text(encoding="utf-8"))
    wanted = _reference(case)
    status, payload, _ = _run(case)
    actual = json.loads(payload) if payload is not None else None
    matches = _same_plan(actual, wanted)
    assert status == 0 and matches
    assert math.isclose(
        actual["summary"]["terminal_storage_kwh_th"],
        case["storage"]["terminal_kwh_th"],
        rel_tol=0.0,
        abs_tol=1e-12,
    )


def test_c3_tie_break_uses_smaller_end_inventory_path():
    """Equal zero cost paths are decided by the storage-end sequence."""
    case = _base_case()
    case["cop"] = 1.0
    case["storage"].update(
        {
            "capacity_kwh_th": 10.0,
            "inventory_step_kwh_th": 5.0,
            "initial_kwh_th": 0.0,
            "terminal_kwh_th": 0.0,
            "max_charge_kw_th": 10.0,
            "max_discharge_kw_th": 10.0,
            "charge_efficiency": 1.0,
            "discharge_efficiency": 1.0,
            "standing_loss_per_h": 0.0,
        }
    )
    case["demand"].update({"previous_peak_kw": 0.0, "rounding_kw": 1.0, "charge_per_kw": 0.0})
    case["periods"] = [
        {"cooling_load_kw_th": 10.0, "price_per_kwh": 0.0},
        {"cooling_load_kw_th": 10.0, "price_per_kwh": 0.0},
    ]
    wanted = _reference(case)
    status, payload, _ = _run(case)
    actual = json.loads(payload) if payload is not None else None
    matches = _same_plan(actual, wanted)
    assert status == 0 and matches
    assert [row["storage_end_kwh_th"] for row in actual["schedule"]] == [0.0, 0.0]


def test_c4_invalid_inputs_leave_no_artifact():
    """Malformed structure, ranges, and non-finite values are rejected."""
    valid = _base_case()
    cases = []
    bad_efficiency = copy.deepcopy(valid)
    bad_efficiency["storage"]["charge_efficiency"] = 1.2
    cases.append(bad_efficiency)
    bad_grid = copy.deepcopy(valid)
    bad_grid["storage"]["capacity_kwh_th"] = 22.0
    cases.append(bad_grid)
    no_periods = copy.deepcopy(valid)
    no_periods["periods"] = []
    cases.append(no_periods)
    nonfinite = copy.deepcopy(valid)
    nonfinite["periods"][0]["price_per_kwh"] = float("nan")
    cases.append(nonfinite)
    outcomes = []
    for case in cases:
        status, payload, _ = _run(case)
        outcomes.append(status != 0 and payload is None)
    assert all(outcomes)


def test_c4_failure_preserves_existing_output():
    """A rejected request does not replace an existing output file."""
    case = _base_case()
    case["storage"]["standing_loss_per_h"] = 1.0
    status, payload, _ = _run(case, existing="previous accepted plan")
    assert status != 0 and payload == "previous accepted plan"
