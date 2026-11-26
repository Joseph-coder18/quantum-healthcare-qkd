"""Run paired synthetic workload comparisons and write per-class CSV results."""

import argparse
import csv
from dataclasses import asdict, dataclass, fields
from functools import lru_cache, partial
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
from platform import python_version
from random import Random
from statistics import mean, stdev

from scipy.stats import t

from healthcare.requests import HealthcareRequest, Priority, RELATIVE_DEADLINE_SECONDS
from key_management.deadline_generation import YieldObservation
from key_management.dynamic_reserve import DynamicReserveConfig
from key_management.replenishment import ReplenishmentConfig
from qkd.pipeline import run_bb84_batch
from scheduling.fd_qks import QueuePolicy
from scheduling.simulation import (
    BatchRunner, BatchStatus, BatchTrace, ChannelCondition, GenerationPolicy, RequestTrace,
    simulate_requests,
)


@dataclass(frozen=True)
class Policy:
    queue: QueuePolicy = QueuePolicy.FD_QKS
    generation: GenerationPolicy = GenerationPolicy.ADAPTIVE
    reserve: int = 1024
    ageing: float | None = 10.0
    dynamic_reserve: DynamicReserveConfig | None = None


POLICIES = {
    "fd-qks": Policy(),
    "fcfs": Policy(QueuePolicy.FCFS, GenerationPolicy.FIXED, 0, None),
    "static-priority": Policy(QueuePolicy.STATIC_PRIORITY, GenerationPolicy.FIXED, 0, None),
    "edf": Policy(QueuePolicy.EDF, GenerationPolicy.FIXED, 0, None),
    "ddka-inspired": Policy(QueuePolicy.FCFS, GenerationPolicy.DEMAND_ONLY, 0, None),
    "apr-inspired": Policy(QueuePolicy.STATIC_PRIORITY, GenerationPolicy.FIXED, 1024, None),
    "without-ageing": Policy(ageing=None),
    "without-reserve": Policy(reserve=0),
    "without-adaptive": Policy(generation=GenerationPolicy.FIXED),
}

SCENARIOS = {
    "normal": (48, 27, 65536, 0.0),
    "scarcity": (48, 36, 40960, 0.0),
    "emergency-surge": (48, 30, 65536, 0.0),
    "sustained-load": (105, 65, 98304, 0.0),
    "noisy": (48, 27, 65536, 0.02),
}

CONTROLLED_POLICIES = {
    policy.value: Policy(
        queue=policy, generation=GenerationPolicy.FIXED, reserve=1024,
        ageing=10.0 if policy == QueuePolicy.FD_QKS else None,
    )
    for policy in QueuePolicy if policy != QueuePolicy.DEADLINE_SENSITIVE
}

ENGINE_CONFIG = {
    "qubits_per_second": 4096,
    "fixed_batch_qubits": 8192,
    "pool_capacity_bits": 8192,
}


def synthetic_workload(scenario: str, seed: int) -> tuple[HealthcareRequest, ...]:
    horizon, count, _, _ = SCENARIOS[scenario]
    rng = Random(seed)
    requests = []
    for index in range(count):
        priority = rng.choices(tuple(Priority), weights=(2, 4, 3, 1))[0]
        arrival = rng.randrange(horizon)
        if scenario == "emergency-surge" and index >= count - 9:
            priority = Priority.EMERGENCY
            arrival = 18 + rng.randrange(3)
        request_id = f"{index:03d}"
        requests.append(HealthcareRequest(
            request_id,
            arrival,
            arrival + RELATIVE_DEADLINE_SECONDS[priority],
            priority,
            payload=f"Synthetic {priority.name.lower()} case {request_id}".encode(),
        ))
    return tuple(requests)


def build_manifest(seeds: list[int], scenarios: list[str], *, controlled: bool) -> dict:
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("provide one or more distinct paired seeds")
    if not scenarios or len(set(scenarios)) != len(scenarios):
        raise ValueError("provide one or more distinct scenarios")
    return {
        "schema_version": 1,
        "comparison": "controlled" if controlled else "original",
        "engine": dict(ENGINE_CONFIG),
        "replenishment": asdict(ReplenishmentConfig()),
        "policies": {name: asdict(policy) for name, policy in
                     (CONTROLLED_POLICIES if controlled else POLICIES).items()},
        "workloads": [
            {
                "scenario": scenario,
                "seed": seed,
                "qubit_budget": SCENARIOS[scenario][2],
                "depolarizing_probability": SCENARIOS[scenario][3],
                "requests": [
                    {"request_id": request.request_id, "arrival_time": request.arrival_time,
                     "deadline": request.deadline, "priority": request.priority.name,
                     "required_key_bits": request.required_key_bits}
                    for request in synthetic_workload(scenario, seed)
                ],
            }
            for scenario in scenarios for seed in seeds
        ],
    }


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    with path.open("x", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields if fields is not None else list(rows[0]),
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def paired_intervals(rows: list[dict]) -> list[dict]:
    """Compare seed-level delivery rates and qubit use with FD-QKS."""
    runs = {(row["scenario"], row["seed"], row["policy"], row["priority"]): row for row in rows}
    pairs: dict[tuple[str, str, str, str], list[float]] = {}
    for (scenario, seed, policy, priority), row in runs.items():
        if policy == "fd-qks":
            continue
        reference = runs[scenario, seed, "fd-qks", priority]
        if row["offered"] != reference["offered"]:
            raise ValueError("paired policies must be offered the same workload")
        if row["offered"]:
            delta = (row["delivered"] - reference["delivered"]) / row["offered"]
            pairs.setdefault((scenario, policy, priority, "delivery_rate"), []).append(delta)
        if priority == "all":
            delta = row["qubits_started"] - reference["qubits_started"]
            pairs.setdefault((scenario, policy, priority, "qubits_started"), []).append(delta)
    intervals = []
    for (scenario, policy, priority, metric), values in sorted(pairs.items()):
        center = mean(values)
        count = len(values)
        margin = t.ppf(0.975, df=count - 1) * stdev(values) / count**0.5 if count > 1 else None
        intervals.append({
            "scenario": scenario, "policy": policy, "reference": "fd-qks",
            "priority": priority, "metric": metric, "paired_seeds": count, "mean_delta": center,
            "lower_95": center - margin if margin is not None else None,
            "upper_95": center + margin if margin is not None else None,
        })
    return intervals


def run_study(destination: Path, manifest: dict, *, runner: BatchRunner = run_bb84_batch) -> None:
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported experiment manifest schema")
    workload_ids = [(job["scenario"], job["seed"]) for job in manifest["workloads"]]
    if not workload_ids or len(set(workload_ids)) != len(workload_ids):
        raise ValueError("manifest must define distinct scenario and seed pairs")
    policies = {name: Policy(
        QueuePolicy(settings["queue"]), GenerationPolicy(settings["generation"]),
        settings["reserve"], settings["ageing"],
        DynamicReserveConfig(**settings["dynamic_reserve"]) if settings.get("dynamic_reserve") else None,
    ) for name, settings in manifest["policies"].items()}
    if "fd-qks" not in policies:
        raise ValueError("manifest requires an fd-qks reference policy")
    if manifest["comparison"] == "controlled" and (
        len({(policy.generation, policy.reserve, policy.dynamic_reserve)
             for policy in policies.values()}) != 1
    ):
        raise ValueError("controlled comparison requires shared generation and reserve settings")
    if destination.exists():
        raise FileExistsError(f"choose a new output directory: {destination}")
    config = ReplenishmentConfig(**manifest["replenishment"])
    calibration = tuple(YieldObservation(**row) for row in manifest.get("yield_calibration", ()))
    root = Path(__file__).resolve().parents[1]
    sources = [*root.glob("qkd/*.py"), *root.glob("healthcare/*.py"),
               *root.glob("key_management/*.py"), *root.glob("scheduling/*.py"),
               *root.glob("experiments/*.py")]
    recorded = {**manifest, "environment": {
        "python": python_version(),
        **{name: version(name) for name in ("qiskit", "qiskit-aer", "scipy", "cryptography")},
        "lock_sha256": sha256((root / "requirements-lock.txt").read_bytes()).hexdigest(),
        "source_sha256": {str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest()
                          for path in sorted(sources)},
    }}

    # Reuse deterministic Aer batches when policies request the same channel,
    # seed, and batch size. Every policy is still charged its own qubit usage.
    if manifest.get("aer_execution", "original") not in {"original", "grouped"}:
        raise ValueError("aer_execution must be original or grouped")
    if manifest.get("aer_execution") == "grouped":
        runner = partial(runner, grouped=True)
    batch_runner = lru_cache(maxsize=256)(runner)
    rows = []
    request_rows = []
    batch_rows = []
    for job in manifest["workloads"]:
        scenario, seed = job["scenario"], job["seed"]
        budget, noise = job["qubit_budget"], job["depolarizing_probability"]
        channel_schedule = tuple(ChannelCondition(**item) for item in job.get("channel_schedule", ()))
        initial_pool_bits = job.get("initial_pool_bits", 0)
        requests = tuple(
            HealthcareRequest(
                item["request_id"], item["arrival_time"], item["deadline"],
                Priority[item["priority"]], item["required_key_bits"],
                f"Synthetic {item['priority'].lower()} case {item['request_id']}".encode(),
            )
            for item in job["requests"]
        )
        for name, policy in policies.items():
            result = simulate_requests(
                requests, seed=seed, qubit_budget=budget, reserve_bits=policy.reserve,
                ageing_interval=policy.ageing, depolarizing_probability=noise,
                queue_policy=policy.queue, generation_policy=policy.generation,
                batch_runner=batch_runner, replenishment=config, **manifest["engine"],
                channel_schedule=channel_schedule, initial_pool_bits=initial_pool_bits,
                dynamic_reserve=policy.dynamic_reserve,
                yield_calibration=calibration,
            )
            if len(result.delivered) + len(result.missed) != len(requests):
                raise RuntimeError("request accounting failed")
            identity = {"scenario": scenario, "seed": seed, "policy": name}
            request_rows.extend({**identity, **asdict(trace)} for trace in result.requests)
            batch_rows.extend({**identity, **asdict(trace)} for trace in result.batches)
            qubit_costs = {f"qubits_{status.value}": result.qubits_for(status) for status in BatchStatus}
            for priority in (None, *Priority):
                served = [item.wait_seconds for item in result.delivered
                          if priority is None or item.priority == priority]
                missed = sum(priority is None or item.priority == priority for item in result.missed)
                rows.append({
                    **identity, "priority": priority.name.lower() if priority is not None else "all",
                    "offered": len(served) + missed, "delivered": len(served), "missed": missed,
                    "mean_wait_seconds": round(mean(served), 4) if served else "",
                    "maximum_wait_seconds": max(served) if served else "",
                    "qubit_budget": budget, "qubits_started": result.qubits_started, **qubit_costs,
                    "generated_bits": result.generated_bits, "wasted_bits": result.wasted_bits,
                    "remaining_bits": result.remaining_bits, "initial_pool_bits": initial_pool_bits,
                    "reserve_bits_used": sum(trace.reserve_bits_used for trace in result.requests
                                             if priority is None or trace.priority == priority.name.lower()),
                })
        print(f"Completed {scenario}, seed {seed}", flush=True)

    intervals = paired_intervals(rows)
    destination.mkdir(parents=True)
    write_csv(destination / "scheduling.csv", rows)
    identifiers = ["scenario", "seed", "policy"]
    write_csv(destination / "requests.csv", request_rows,
              identifiers + [field.name for field in fields(RequestTrace)])
    write_csv(destination / "batches.csv", batch_rows,
              identifiers + [field.name for field in fields(BatchTrace)])
    write_csv(destination / "paired_intervals.csv", intervals, [
        "scenario", "policy", "reference", "priority", "metric", "paired_seeds",
        "mean_delta", "lower_95", "upper_95",
    ])
    (destination / "manifest.json").write_text(json.dumps(recorded, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", nargs="+", type=int)
    parser.add_argument("--scenarios", nargs="+", choices=tuple(SCENARIOS))
    parser.add_argument("--controlled", action="store_true")
    parser.add_argument("--replay", type=Path, help="reuse workload rows and settings from a manifest")
    parser.add_argument("--output-dir", type=Path, required=True, help="new directory for experiment outputs")
    args = parser.parse_args()
    if args.replay:
        if args.seeds or args.scenarios or args.controlled:
            parser.error("--replay supplies seeds, scenarios and comparison settings")
        manifest = json.loads(args.replay.read_text(encoding="utf-8"))
    else:
        manifest = build_manifest(
            args.seeds or [42, 43, 44], args.scenarios or list(SCENARIOS),
            controlled=args.controlled,
        )
    run_study(args.output_dir, manifest)


if __name__ == "__main__":
    main()
