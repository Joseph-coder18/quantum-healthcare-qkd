"""Measure grouped and original Aer behavior through BB84 post-processing."""

import argparse
from itertools import product
from pathlib import Path
from time import perf_counter

from experiments.scheduling_study import write_csv
from qkd.pipeline import run_bb84_batch


SIZES = (1024, 4096, 8192)
CONDITIONS = (
    ("ideal", 0.0, 0.0),
    ("low-noise", 0.02, 0.0),
    ("mixed-disturbance", 0.04, 0.1),
    ("interception", 0.0, 0.25),
)


def measure(seeds: list[int]) -> list[dict]:
    rows = []
    for seed, qubits, (channel, noise, interception) in product(seeds, SIZES, CONDITIONS):
        for grouped in (False, True) if seed % 2 == 0 else (True, False):
            start = perf_counter()
            batch = run_bb84_batch(
                qubits, seed=seed, depolarizing_probability=noise,
                interception_probability=interception, grouped=grouped,
            )
            rows.append({
                "seed": seed, "qubits": qubits, "channel": channel, "depolarization": noise,
                "interception": interception, "grouped": grouped, "sifted": batch.sifted_count,
                "sampled": batch.sampled_count, "qber": batch.sampled_qber,
                "agreement": batch.agreement, "estimated_bits": batch.finite_key.output_length,
                "usable_bits": len(batch.amplified_bits), "wall_seconds": perf_counter() - start,
            })
        print(f"Measured seed {seed}, {qubits} qubits, {channel}", flush=True)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", nargs="+", type=int, default=[101, 102, 103, 104])
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("--output must name a new file")
    if len(set(args.seeds)) != len(args.seeds):
        parser.error("seeds must be distinct")
    write_csv(args.output, measure(args.seeds))


if __name__ == "__main__":
    main()
