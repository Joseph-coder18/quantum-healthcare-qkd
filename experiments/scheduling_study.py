"""Run paired synthetic workload comparisons and write per-class CSV results."""

import argparse
import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from random import Random
from statistics import mean

from healthcare.requests import HealthcareRequest, Priority, RELATIVE_DEADLINE_SECONDS
from qkd.pipeline import run_bb84_batch
from scheduling.fd_qks import QueuePolicy
from scheduling.simulation import GenerationPolicy, simulate_requests


@dataclass(frozen=True)
class Policy:
    queue: QueuePolicy = QueuePolicy.FD_QKS
    generation: GenerationPolicy = GenerationPolicy.ADAPTIVE
    reserve: int = 1024
    ageing: float | None = 10.0


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


def run_study(destination: Path, seeds: list[int], scenarios: list[str]) -> None:
    # Reuse deterministic Aer batches when policies request the same channel,
    # seed, and batch size. Every policy is still charged its own qubit usage.
    batch_runner = lru_cache(maxsize=256)(run_bb84_batch)
    rows = []
    for scenario in scenarios:
        _, _, budget, noise = SCENARIOS[scenario]
        for seed in seeds:
            requests = synthetic_workload(scenario, seed)
            for name, policy in POLICIES.items():
                result = simulate_requests(
                    requests, seed=seed, qubit_budget=budget, reserve_bits=policy.reserve,
                    ageing_interval=policy.ageing, depolarizing_probability=noise,
                    queue_policy=policy.queue, generation_policy=policy.generation,
                    batch_runner=batch_runner,
                )
                if result.generated_bits != (
                    256 * len(result.delivered) + result.wasted_bits + result.remaining_bits
                ):
                    raise RuntimeError("key conservation failed")
                if len(result.delivered) + len(result.missed) != len(requests):
                    raise RuntimeError("request accounting failed")
                for priority in (None, *Priority):
                    served = [item.wait_seconds for item in result.delivered
                              if priority is None or item.priority == priority]
                    missed = sum(priority is None or item.priority == priority for item in result.missed)
                    rows.append({
                        "scenario": scenario, "seed": seed, "policy": name,
                        "priority": priority.name.lower() if priority is not None else "all",
                        "offered": len(served) + missed, "delivered": len(served), "missed": missed,
                        "mean_wait_seconds": round(mean(served), 4) if served else "",
                        "maximum_wait_seconds": max(served) if served else "",
                        "qubit_budget": budget, "qubits_started": result.qubits_started,
                        "generated_bits": result.generated_bits, "wasted_bits": result.wasted_bits,
                        "remaining_bits": result.remaining_bits,
                    })
            print(f"Completed {scenario}, seed {seed}", flush=True)

    with destination.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 43, 44])
    parser.add_argument("--scenarios", nargs="+", choices=tuple(SCENARIOS), default=list(SCENARIOS))
    parser.add_argument("--output", type=Path, default=Path("results/scheduling.csv"))
    args = parser.parse_args()
    run_study(args.output, args.seeds, args.scenarios)


if __name__ == "__main__":
    main()
