"""Run baseline, one-fix variants, and bypass specimens through the real test script."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


TASK = Path(__file__).resolve().parents[1]
IMAGE = "harbor-quality:ice-storage-demand-planner"
GROUPS = ("c1", "c2", "c3", "c4")


def run_command(args):
    return subprocess.run(args, text=True, capture_output=True, check=False)


def specimen(root, label, files, override=None):
    work = root / label / "workspace"
    shutil.copytree(TASK / "environment" / "workspace", work)
    for filename in files:
        shutil.copy2(
            TASK / "solution" / filename,
            work / "coldstore_planner" / filename,
        )
    if override is not None:
        override(work)
    logs = root / label / "logs" / "verifier"
    logs.mkdir(parents=True)
    (root / label).chmod(0o755)
    logs.parent.chmod(0o777)
    logs.chmod(0o777)
    command = [
        "docker",
        "run",
        "--rm",
        "--user",
        "10001:10001",
        "--network",
        "host",
        "-v",
        f"{work}:/workspace:ro",
        "-v",
        f"{TASK / 'tests'}:/tests:ro",
        "-v",
        f"{logs.parent}:/logs",
        IMAGE,
        "bash",
        "/tests/test.sh",
    ]
    outcome = run_command(command)
    reward_path = logs / "reward.txt"
    reward = float(reward_path.read_text(encoding="utf-8").strip()) if reward_path.exists() else None
    evidence = TASK / "solution" / "evidence" / f"{label}.log"
    group_logs = {}
    for group in GROUPS:
        group_log = logs / f"{group}.log"
        group_logs[group] = group_log.read_text(encoding="utf-8") if group_log.exists() else "missing"
    evidence.write_text(
        "Command: "
        + " ".join(command)
        + f"\nExit: {outcome.returncode}\nReward: {reward}\n"
        + "stdout:\n"
        + outcome.stdout
        + "\nstderr:\n"
        + outcome.stderr
        + "".join(f"\n[{group}]\n{text}" for group, text in group_logs.items()),
        encoding="utf-8",
    )
    if reward is None:
        raise RuntimeError(f"{label}: no reward; inspect {evidence}")
    print(f"{label}: {reward}")
    return {"reward": reward, "evidence": str(evidence.relative_to(TASK))}


def empty_output(work):
    (work / "coldstore_planner" / "planner.py").write_text(
        "def solve(data):\n"
        "    return {'site_id': data.get('site_id', ''), 'schedule': [], "
        "'summary': {'energy_cost': 0, 'daytime_peak_kw': 0, "
        "'billed_demand_kw': 0, 'demand_charge': 0, 'total_cost': 0, "
        "'terminal_storage_kwh_th': 0}}\n",
        encoding="utf-8",
    )


def hardcoded_sample(work):
    source = TASK / "solution" / "sample-result.json"
    (work / "coldstore_planner" / "planner.py").write_text(
        "import json\n"
        "from pathlib import Path\n"
        f"_PAYLOAD = json.loads({str(source)!r})\n"
        "def solve(data):\n"
        "    result = json.loads(json.dumps(_PAYLOAD))\n"
        "    result['site_id'] = data['site_id']\n"
        "    return result\n",
        encoding="utf-8",
    )


def malformed_output(work):
    (work / "coldstore_planner" / "planner.py").write_text(
        "def solve(data):\n"
        "    return {'site_id': data['site_id'], 'schedule': [], "
        "'summary': {'total_cost': float('nan')}}\n",
        encoding="utf-8",
    )


def main():
    build = run_command(["docker", "build", "-q", "-t", IMAGE, str(TASK / "environment")])
    if build.returncode:
        raise RuntimeError(build.stderr)
    (TASK / "solution" / "evidence").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ice-quality-") as temporary:
        root = Path(temporary)
        root.chmod(0o755)
        baseline = specimen(root, "baseline", [])
        oracle = specimen(
            root,
            "oracle",
            ["storage.py", "billing.py", "planner.py", "model.py", "cli.py"],
        )
        partials = [
            {"challenge_id": "C1", **specimen(root, "partial-c1", ["storage.py"])},
            {"challenge_id": "C2", **specimen(root, "partial-c2", ["billing.py"])},
            {"challenge_id": "C3", **specimen(root, "partial-c3", ["planner.py"])},
            {"challenge_id": "C4", **specimen(root, "partial-c4", ["model.py"])},
        ]
        bypasses = [
            {
                "id": "B1",
                "description": "返回空调度和全零汇总",
                **specimen(root, "bypass-empty", [], empty_output),
            },
            {
                "id": "B2",
                "description": "固定回放随包样例结果",
                **specimen(root, "bypass-fixed", [], hardcoded_sample),
            },
            {
                "id": "B3",
                "description": "只写截断汇总并带非有限数值",
                **specimen(root, "bypass-malformed", [], malformed_output),
            },
        ]
    report = {
        "baseline": baseline,
        "oracle": oracle,
        "partials": partials,
        "bypasses": bypasses,
    }
    (TASK / "solution" / "quality-gate-results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if baseline["reward"] != 0 or oracle["reward"] != 1:
        raise RuntimeError("baseline/oracle gate failed")
    if any(not 0 < item["reward"] < 1 for item in partials):
        raise RuntimeError("partial gate failed")
    if any(item["reward"] == 1 for item in bypasses):
        raise RuntimeError("bypass gate failed")


if __name__ == "__main__":
    main()
