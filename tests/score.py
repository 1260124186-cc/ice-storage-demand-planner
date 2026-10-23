"""Validate a trusted JUnit report and emit the final reward artifacts."""

import json
import os
import sys
import xml.etree.ElementTree as ET


GROUPS = {
    "c1": (2, {
        "test_c1_charge_efficiency_changes_inventory",
        "test_c1_discharge_efficiency_changes_served_load",
        "test_c1_standing_loss_precedes_flows",
        "test_c1_rejects_charge_above_hourly_limit",
    }),
    "c2": (2, {
        "test_c2_rounds_demand_up_to_step",
        "test_c2_previous_peak_sets_ratchet",
        "test_c2_summary_counts_demand_charge_once",
    }),
    "c3": (5, {
        "test_c3_shifts_load_to_limit_demand_peak",
        "test_c3_efficiency_can_make_arbitrage_unattractive",
        "test_c3_terminal_inventory_is_exact",
        "test_c3_rejects_unreachable_terminal_inventory",
        "test_c3_schema_and_load_balance",
        "test_c3_shipped_sample_matches_reference",
        "test_c3_tie_break_uses_smaller_end_inventory_path",
    }),
    "c4": (1, {
        "test_c4_invalid_inputs_leave_no_artifact",
        "test_c4_failure_preserves_existing_output",
    }),
}


def write_reward(path, value):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(f"{value:.6f}\n")
    os.chmod(path, 0o444)


def incomplete(reason, reward_path, status_path, scoring_path):
    with open(status_path, "w", encoding="utf-8") as handle:
        handle.write(f"INCOMPLETE: {reason}\n")
    with open(scoring_path, "w", encoding="utf-8") as handle:
        json.dump({"status": "INCOMPLETE", "reason": reason}, handle, indent=2)
        handle.write("\n")
    write_reward(reward_path, 0.0)
    raise SystemExit(0)


def main():
    report_path, reward_path, status_path, scoring_path, pytest_status = sys.argv[1:]
    if not os.path.isfile(report_path) or os.path.getsize(report_path) == 0:
        incomplete(
            "pytest report missing or empty",
            reward_path,
            status_path,
            scoring_path,
        )

    try:
        root = ET.parse(report_path).getroot()
    except ET.ParseError:
        incomplete(
            "pytest report could not be parsed",
            reward_path,
            status_path,
            scoring_path,
        )

    outcomes = {}
    for case in root.iter("testcase"):
        name = case.get("name", "")
        if "::" in name:
            name = name.rsplit("::", 1)[-1]
        failed = any(
            child.tag in {"failure", "error", "skipped"} for child in case
        )
        outcomes[name] = not failed

    expected = {name for _, names in GROUPS.values() for name in names}
    if not expected.issubset(outcomes):
        missing = sorted(expected - set(outcomes))
        incomplete(
            "pytest report is incomplete: " + ", ".join(missing[:5]),
            reward_path,
            status_path,
            scoring_path,
        )

    group_results = {}
    earned = 0
    for group, (weight, names) in GROUPS.items():
        passed = all(outcomes.get(name, False) for name in names)
        group_results[group] = {"passed": passed, "weight": weight}
        if passed:
            earned += weight

    value = min(1.0, earned / 10.0)
    with open(status_path, "w", encoding="utf-8") as handle:
        handle.write(f"COMPLETED: score={value:.6f}\n")
    with open(scoring_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "status": "COMPLETED",
                "pytest_exit": int(pytest_status),
                "score": value,
                "groups": group_results,
                "test_count": len(outcomes),
            },
            handle,
            indent=2,
        )
        handle.write("\n")
    write_reward(reward_path, value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
