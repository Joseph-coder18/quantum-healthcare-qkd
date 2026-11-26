"""Summarize Phase 10 traces and paired differences by independent seed."""

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean, quantiles, stdev

from scipy.stats import t

from experiments.scheduling_study import write_csv


def _read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def _ratio(numerator: float, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _wait_metrics(waits: list[float]) -> dict:
    p = quantiles(waits, n=100, method="inclusive") if len(waits) > 1 else waits * 99
    return {"served_wait_p50": p[49] if p else None, "served_wait_p90": p[89] if p else None}


def _metrics(requests: list[dict], runs: list[dict]) -> dict:
    served = [row for row in requests if row["completion_time"]]
    waits = [float(row["completion_time"]) - float(row["arrival"]) for row in served]
    low_priority = [row for row in requests if row["priority"] in {"administrative", "routine"}]
    started = sum(int(row["qubits_started"]) for row in runs)
    completed = sum(int(row["qubits_completed"]) for row in runs)
    reserved = sum(
        int(row["reserve_bits_used"]) if "reserve_bits_used" in row
        else min(int(row["pool_before"]), int(row["reserve_bits"]))
        - min(int(row["pool_after"]), int(row["reserve_bits"]))
        for row in served
    )
    return {
        "offered": len(requests), "delivered": len(served),
        "deadline_missed": sum(row["reason"] == "deadline_missed" for row in requests),
        "delivery_rate": _ratio(len(served), len(requests)),
        "low_priority_expiry_rate": _ratio(
            sum(row["reason"] == "deadline_missed" for row in low_priority), len(low_priority)
        ),
        "reserve_bits_used": reserved, **_wait_metrics(waits),
        "remaining_bits": sum(int(row["remaining_bits"]) for row in runs) if runs else None,
        "qubits_started": started if runs else None, "qubits_completed": completed if runs else None,
        "started_qubits_per_delivery": _ratio(started, len(served)) if runs else None,
        "completed_qubits_per_delivery": _ratio(completed, len(served)) if runs else None,
    }


def summarize(directory: Path, *, reference_policy: str = "fd-qks") -> tuple[list[dict], list[dict]]:
    requests = _read(directory / "requests.csv")
    runs = [row for row in _read(directory / "scheduling.csv") if row["priority"] == "all"]
    request_groups = defaultdict(list)
    run_groups = defaultdict(list)
    for row in requests:
        for scenario in (row["scenario"], "all-scenarios"):
            for seed in (row["seed"], "pooled"):
                for priority in (row["priority"], "all"):
                    request_groups[scenario, seed, row["policy"], priority].append(row)
    for row in runs:
        for scenario in (row["scenario"], "all-scenarios"):
            for seed in (row["seed"], "pooled"):
                run_groups[scenario, seed, row["policy"], "all"].append(row)

    metrics = {key: _metrics(records, run_groups.get(key, []))
               for key, records in request_groups.items()}
    if reference_policy not in {key[2] for key in metrics}:
        raise ValueError("reference policy is absent from the study")
    summary = [{"scenario": scenario, "policy": policy, "priority": priority, **values}
               for (scenario, seed, policy, priority), values in sorted(metrics.items())
               if seed == "pooled"]
    comparisons = defaultdict(list)
    for (scenario, seed, policy, priority), candidate in metrics.items():
        if seed == "pooled" or policy == reference_policy:
            continue
        reference = metrics.get((scenario, seed, reference_policy, priority), {})
        for metric, value in candidate.items():
            if value is not None and reference.get(metric) is not None:
                comparisons[scenario, policy, priority, metric].append(value - reference[metric])
    intervals = []
    for (scenario, policy, priority, metric), deltas in sorted(comparisons.items()):
        n = len(deltas)
        center = mean(deltas)
        margin = t.ppf(0.975, n - 1) * stdev(deltas) / n**0.5 if n > 1 else None
        intervals.append({
            "scenario": scenario, "policy": policy, "priority": priority, "metric": metric,
            "paired_seeds": n, "mean_delta": center,
            "lower_95": center - margin if margin is not None else None,
            "upper_95": center + margin if margin is not None else None,
        })
    return summary, intervals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--reference", default="fd-qks", help="policy used for paired differences")
    args = parser.parse_args()
    summary, intervals = summarize(args.directory, reference_policy=args.reference)
    if args.reference == "fd-qks":
        write_csv(args.directory / "metrics.csv", summary)
        filename = "paired_trace_intervals.csv"
    else:
        filename = f"paired_vs_{args.reference}.csv"
    if intervals:
        write_csv(args.directory / filename, intervals)


if __name__ == "__main__":
    main()
