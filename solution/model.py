"""Input loading and validation for the ice-storage dispatch planner."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any


class InputError(ValueError):
    """Raised when a planning request is malformed or infeasible."""


def _decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise InputError(f"{label} must be a finite number")
    try:
        result = Decimal(str(value))
    except Exception as exc:  # pragma: no cover - defensive conversion
        raise InputError(f"{label} must be a finite number") from exc
    if not result.is_finite():
        raise InputError(f"{label} must be a finite number")
    return result


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InputError(f"{label} must be an object")
    return value


def _exact_decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise InputError(f"{label} must be an integer or an exact JSON decimal")
    result = Decimal(value) if isinstance(value, int) else value
    if not result.is_finite():
        raise InputError(f"{label} must be finite")
    return result


def _multiple_of(value: Decimal, step: Decimal) -> bool:
    return step > 0 and value % step == 0


def normalize_input(raw: Any) -> dict[str, Any]:
    """Validate a request and return a Decimal-backed working structure."""
    data = _mapping(raw, "input")
    site_id = data.get("site_id")
    if not isinstance(site_id, str) or not site_id.strip():
        raise InputError("site_id must be a non-empty string")

    cop = _decimal(data.get("cop"), "cop")
    capacity_kw_th = _decimal(
        data.get("chiller_capacity_kw_th"), "chiller_capacity_kw_th"
    )
    if cop <= 0 or capacity_kw_th <= 0:
        raise InputError("cop and chiller_capacity_kw_th must be positive")

    storage_raw = _mapping(data.get("storage"), "storage")
    capacity = _decimal(storage_raw.get("capacity_kwh_th"), "storage.capacity_kwh_th")
    step = _decimal(
        storage_raw.get("inventory_step_kwh_th"),
        "storage.inventory_step_kwh_th",
    )
    initial = _decimal(storage_raw.get("initial_kwh_th"), "storage.initial_kwh_th")
    terminal = _decimal(storage_raw.get("terminal_kwh_th"), "storage.terminal_kwh_th")
    max_charge = _decimal(
        storage_raw.get("max_charge_kw_th"), "storage.max_charge_kw_th"
    )
    max_discharge = _decimal(
        storage_raw.get("max_discharge_kw_th"), "storage.max_discharge_kw_th"
    )
    charge_efficiency = _decimal(
        storage_raw.get("charge_efficiency"), "storage.charge_efficiency"
    )
    discharge_efficiency = _decimal(
        storage_raw.get("discharge_efficiency"), "storage.discharge_efficiency"
    )
    standing_loss = _decimal(
        storage_raw.get("standing_loss_per_h"), "storage.standing_loss_per_h"
    )

    if capacity < 0 or step <= 0 or not _multiple_of(capacity, step):
        raise InputError("storage capacity must be a non-negative multiple of the step")
    if not (0 <= initial <= capacity and _multiple_of(initial, step)):
        raise InputError("initial storage must lie on the inventory grid")
    if not (0 <= terminal <= capacity and _multiple_of(terminal, step)):
        raise InputError("terminal storage must lie on the inventory grid")
    if max_charge < 0 or max_discharge < 0:
        raise InputError("charge and discharge limits must be non-negative")
    if not (0 < charge_efficiency <= 1 and 0 < discharge_efficiency <= 1):
        raise InputError("storage efficiencies must be in (0, 1]")
    if not (0 <= standing_loss < 1):
        raise InputError("standing_loss_per_h must be in [0, 1)")

    demand_raw = _mapping(data.get("demand"), "demand")
    previous_peak = _decimal(
        demand_raw.get("previous_peak_kw"), "demand.previous_peak_kw"
    )
    rounding = _decimal(demand_raw.get("rounding_kw"), "demand.rounding_kw")
    demand_rate = _decimal(
        demand_raw.get("charge_per_kw"), "demand.charge_per_kw"
    )
    if previous_peak < 0 or rounding <= 0 or demand_rate < 0:
        raise InputError("demand values are outside their allowed ranges")

    periods_raw = data.get("periods")
    if not isinstance(periods_raw, list) or not 1 <= len(periods_raw) <= 24:
        raise InputError("periods must contain between 1 and 24 hourly entries")
    periods: list[dict[str, Decimal]] = []
    for index, period_raw in enumerate(periods_raw):
        period = _mapping(period_raw, f"periods[{index}]")
        load = _decimal(period.get("cooling_load_kw_th"), f"periods[{index}].cooling_load_kw_th")
        price = _decimal(period.get("price_per_kwh"), f"periods[{index}].price_per_kwh")
        if load < 0 or price < 0:
            raise InputError("cooling loads and energy prices must be non-negative")
        periods.append({"cooling_load_kw_th": load, "price_per_kwh": price})

    return {
        "site_id": site_id,
        "cop": cop,
        "chiller_capacity_kw_th": capacity_kw_th,
        "storage": {
            "capacity_kwh_th": capacity,
            "inventory_step_kwh_th": step,
            "initial_kwh_th": initial,
            "terminal_kwh_th": terminal,
            "max_charge_kw_th": max_charge,
            "max_discharge_kw_th": max_discharge,
            "charge_efficiency": charge_efficiency,
            "discharge_efficiency": discharge_efficiency,
            "standing_loss_per_h": standing_loss,
        },
        "demand": {
            "previous_peak_kw": previous_peak,
            "rounding_kw": rounding,
            "charge_per_kw": demand_rate,
        },
        "periods": periods,
    }


def load_input(path: str | Path) -> dict[str, Any]:
    try:
        raw = json.loads(
            Path(path).read_text(encoding="utf-8"),
            parse_float=Decimal,
            parse_int=Decimal,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"cannot read input JSON: {exc}") from exc
    return normalize_input(raw)
