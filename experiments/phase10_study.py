"""Run replayable Phase 10 comparisons on preassigned workload families."""

import argparse
import csv
from dataclasses import asdict
from pathlib import Path
from random import Random

from experiments.scheduling_study import CONTROLLED_POLICIES, Policy, build_manifest, run_study
from healthcare.requests import Priority
from key_management.dynamic_reserve import DynamicReserveConfig
from scheduling.fd_qks import QueuePolicy
from scheduling.simulation import ChannelCondition, GenerationPolicy


DEVELOPMENT_SEEDS = range(2000, 2030)
HELD_OUT_SEEDS = range(3000, 3030)
DEVELOPMENT = ("simultaneous", "temporary-scarcity", "overload", "channel-shift", "emergency-burst")
HELD_OUT = ("staggered-ties", "repeated-outage", "late-emergencies")


def workload(scenario: str, seed: int) -> dict:
    rng = Random(f"{scenario}:{seed}")
    # Each row is arrival, relative deadline and original priority.
    requests = []
    budget = 32768
    initial_stock = 1536
    channel = [ChannelCondition(0)]

    def add(arrival: int, slack: int, priority: Priority) -> None:
        requests.append({
            "request_id": f"{len(requests):03d}", "arrival_time": arrival,
            "deadline": arrival + slack, "priority": priority.name, "required_key_bits": 256,
        })

    if scenario in {"simultaneous", "staggered-ties"}:
        # Offer more classes at the same tick than the initial pool can serve.
        for tick in (0, 4, 9):
            if scenario == "staggered-ties":
                tick += rng.randrange(2)
            block = [Priority.ADMINISTRATIVE, Priority.ROUTINE, Priority.URGENT,
                     Priority.EMERGENCY, Priority.ROUTINE, Priority.URGENT]
            rng.shuffle(block)
            for priority in block:
                slack = rng.randint(1, 3) if priority == Priority.EMERGENCY else rng.randint(1, 12)
                add(tick, slack, priority)
    else:
        count = 30 if scenario == "overload" else 22
        horizon = 10 if scenario == "overload" else 21
        for _ in range(count):
            priority = rng.choices(tuple(Priority), weights=(3, 4, 4, 1))[0]
            slack = rng.randint(1, 3) if priority == Priority.EMERGENCY else rng.randint(2, 15)
            add(rng.randrange(horizon), slack, priority)

    if scenario == "temporary-scarcity":
        initial_stock = 768
        channel = [ChannelCondition(0, 0.06), ChannelCondition(6, 0.01)]
    elif scenario == "overload":
        budget = 24576
    elif scenario == "channel-shift":
        channel = [ChannelCondition(0, 0.01), ChannelCondition(5, 0.02, 0.20), ChannelCondition(12)]
    elif scenario == "repeated-outage":
        initial_stock = 1024
        channel = [ChannelCondition(0, 0.02, 0.12), ChannelCondition(5),
                   ChannelCondition(11, 0.05, 0.18), ChannelCondition(16, 0.02)]
    elif scenario in {"emergency-burst", "late-emergencies"}:
        burst = 6 if scenario == "emergency-burst" else 15
        for _ in range(6):
            add(burst + rng.randrange(2), rng.randrange(1, 4), Priority.EMERGENCY)
        if scenario == "late-emergencies":
            channel = [ChannelCondition(0, 0.025), ChannelCondition(12, 0.01, 0.10)]

    return {
        "scenario": scenario, "seed": seed, "qubit_budget": budget, "initial_pool_bits": initial_stock,
        "depolarizing_probability": 0.0, "channel_schedule": [asdict(item) for item in channel],
        "requests": requests,
    }


def phase10_manifest(
    split: str, *, grouped: bool = False, comparison: str = "baseline", calibration: Path | None = None,
) -> dict:
    if split == "development":
        scenarios, seeds = DEVELOPMENT, DEVELOPMENT_SEEDS
    elif split == "held-out":
        scenarios, seeds = HELD_OUT, HELD_OUT_SEEDS
    else:
        raise ValueError("split must be development or held-out")
    manifest = build_manifest([42], ["normal"], controlled=False)
    manifest["phase10_split"] = split
    manifest["aer_execution"] = "grouped" if grouped else "original"
    manifest["workloads"] = [workload(scenario, seed) for scenario in scenarios for seed in seeds]
    if comparison == "reserve":
        manifest["comparison"] = "phase10-reserve"
        manifest["policies"] = {
            "fd-qks": asdict(Policy()),
            "dynamic-reserve": asdict(Policy(dynamic_reserve=DynamicReserveConfig())),
        }
    elif comparison == "generation":
        if calibration is None:
            raise ValueError("the generation comparison requires a calibration CSV")
        with calibration.open(newline="", encoding="utf-8") as source:
            manifest["yield_calibration"] = [
                {"qubits": int(row["qubits"]), "qber": float(row["qber"]),
                 "usable_bits": int(row["usable_bits"])}
                for row in csv.DictReader(source)
            ]
        manifest["comparison"] = "phase10-generation"
        manifest["policies"] = {
            "fd-qks": asdict(Policy()),
            "fixed-generation": asdict(Policy(generation=GenerationPolicy.FIXED)),
            "deadline-generation": asdict(Policy(generation=GenerationPolicy.DEADLINE_AWARE)),
        }
    elif comparison == "queue":
        manifest["comparison"] = "controlled"
        manifest["policies"] = {name: asdict(policy) for name, policy in CONTROLLED_POLICIES.items()}
        manifest["policies"]["deadline-sensitive"] = asdict(Policy(
            queue=QueuePolicy.DEADLINE_SENSITIVE, generation=GenerationPolicy.FIXED, ageing=None,
        ))
    elif comparison != "baseline":
        raise ValueError("unknown Phase 10 comparison")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("development", "held-out"), required=True)
    parser.add_argument("--grouped", action="store_true")
    parser.add_argument("--comparison", choices=("baseline", "reserve", "generation", "queue"),
                        default="baseline")
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run_study(args.output_dir, phase10_manifest(
        args.split, grouped=args.grouped, comparison=args.comparison, calibration=args.calibration,
    ))


if __name__ == "__main__":
    main()
