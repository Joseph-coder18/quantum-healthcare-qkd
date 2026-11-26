"""Check Phase 10 experiment CSV accounting against its manifest."""

import argparse
from collections import defaultdict
import json
from pathlib import Path

from experiments.phase10_metrics import _read


def verify(directory: Path) -> tuple[int, int, int]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    workloads = {(row["scenario"], str(row["seed"])): row for row in manifest["workloads"]}
    expected = {(scenario, seed, policy) for scenario, seed in workloads
                for policy in manifest["policies"]}
    request_groups = defaultdict(list)
    batch_groups = defaultdict(list)
    totals = {}

    def key(row: dict) -> tuple[str, str, str]:
        return row["scenario"], row["seed"], row["policy"]

    for row in _read(directory / "requests.csv"):
        request_groups[key(row)].append(row)
    for row in _read(directory / "batches.csv"):
        batch_groups[key(row)].append(row)
    for row in _read(directory / "scheduling.csv"):
        if row["priority"] == "all":
            if key(row) in totals:
                raise ValueError(f"duplicate run {key(row)}")
            totals[key(row)] = row
    if set(totals) != expected or set(request_groups) != expected or set(batch_groups) - expected:
        raise ValueError("trace run identities do not match manifest")

    for run, row in totals.items():
        job = workloads[run[:2]]
        requests = request_groups[run]
        batches = batch_groups[run]
        declared = {item["request_id"]: item for item in job["requests"]}
        offered = int(row["offered"])
        if len(requests) != offered or len(declared) != offered or {r["request_id"] for r in requests} != declared.keys():
            raise ValueError(f"request identities disagree for {run}")
        served = sorted((r for r in requests if r["allocation_id"]), key=lambda r: int(r["allocation_id"]))
        for trace in requests:
            item = declared[trace["request_id"]]
            if (float(trace["arrival"]) != item["arrival_time"]
                    or float(trace["deadline"]) != item["deadline"]
                    or trace["priority"].upper() != item["priority"]):
                raise ValueError(f"trace does not match request in {run}")
            if not trace["allocation_id"] and trace["reason"] != "deadline_missed":
                raise ValueError(f"run did not resolve a request in {run}")
        for index, trace in enumerate(served):
            before, after, reserve = map(int, (trace["pool_before"], trace["pool_after"], trace["reserve_bits"]))
            ticks = (float(trace["arrival"]), float(trace["allocation_time"]),
                     float(trace["completion_time"]), float(trace["deadline"]))
            if tuple(sorted(ticks)) != ticks or before - after != 256 or int(trace["allocation_id"]) != 256 * index:
                raise ValueError(f"invalid allocation or deadline in {run}")
            if trace["priority"] != "emergency" and after < reserve:
                raise ValueError(f"ordinary request consumed reserve in {run}")
        if len(served) != int(row["delivered"]) or offered - len(served) != int(row["missed"]):
            raise ValueError(f"outcome counts disagree for {run}")

        initial = job.get("initial_pool_bits", 0)
        generated = sum(int(batch["output_bits"] or 0) for batch in batches)
        admitted = sum(int(batch["admitted_bits"]) for batch in batches)
        stock = int(row["remaining_bits"])
        if initial + admitted != len(served) * 256 + stock or generated - admitted != int(row["wasted_bits"]):
            raise ValueError(f"key conservation failed for {run}")
        if generated != int(row["generated_bits"]):
            raise ValueError(f"generated key count disagrees for {run}")
        started = sum(int(batch["qubits"]) for batch in batches)
        if started != int(row["qubits_started"]) or started > job["qubit_budget"]:
            raise ValueError(f"qubit budget failed for {run}")
        for status in ("completed", "cancelled", "unfinished"):
            count = sum(int(batch["qubits"]) for batch in batches if batch["status"] == status)
            if count != int(row[f"qubits_{status}"]):
                raise ValueError(f"{status} cost failed for {run}")
        for batch in batches:
            output = int(batch["output_bits"] or 0)
            accepted = int(batch["admitted_bits"])
            if not 0 <= accepted <= output or (
                (batch["status"] != "completed" or batch["rejection_reason"]) and (accepted or output)
            ) or (output and output != int(batch["estimated_bits"])):
                raise ValueError(f"rejected key material in output for {run}")

    return len(totals), sum(map(len, request_groups.values())), sum(map(len, batch_groups.values()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, nargs="+")
    for directory in parser.parse_args().directory:
        runs, requests, batches = verify(directory)
        print(f"{directory}: {runs} runs, {requests} request traces, {batches} batch traces")


if __name__ == "__main__":
    main()
