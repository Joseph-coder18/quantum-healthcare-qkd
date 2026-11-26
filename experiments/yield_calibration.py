"""Calibrate usable BB84 output from independently sampled quality probes."""

import argparse
from itertools import product
from pathlib import Path

from experiments.scheduling_study import write_csv
from qkd.pipeline import run_bb84_batch


SIZES = (2048, 4096, 6144, 8192)
CONDITIONS = ((0.0, 0.0), (0.01, 0.0), (0.02, 0.0), (0.04, 0.0),
              (0.06, 0.0), (0.02, 0.20), (0.02, 0.12))
CALIBRATION_SEEDS = range(1000, 1012)


def calibrate() -> list[dict]:
    rows = []
    for seed, (noise, interception) in product(CALIBRATION_SEEDS, CONDITIONS):
        conditions = {
            "depolarizing_probability": noise, "interception_probability": interception,
            "grouped": True,
        }
        probe = run_bb84_batch(4096, seed=seed * 10, **conditions)
        for index, qubits in enumerate(SIZES, 1):
            batch = run_bb84_batch(qubits, seed=seed * 10 + index, **conditions)
            rows.append({
                "seed": seed, "qubits": qubits, "depolarization": noise,
                "interception": interception, "qber": probe.sampled_qber,
                "batch_qber": batch.sampled_qber,
                "usable_bits": len(batch.amplified_bits),
            })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("--output must name a new file")
    write_csv(args.output, calibrate())


if __name__ == "__main__":
    main()
