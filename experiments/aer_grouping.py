"""Compare the original and grouped BB84 Aer execution paths."""

import argparse
from pathlib import Path
from time import perf_counter

from experiments.scheduling_study import write_csv
from qkd.bb84 import simulate_bb84_round


CHANNELS = (
    ("ideal", 0.0, 0.0),
    ("depolarizing", 0.2, 0.0),
    ("intercept-resend", 0.0, 1.0),
)


def benchmark(qubits: int, seeds: list[int]) -> list[dict]:
    rows = []
    for seed in seeds:
        for channel, noise, interception in CHANNELS:
            # Alternate which path runs first to reduce order effects.
            modes = (False, True) if seed % 2 == 0 else (True, False)
            for grouped in modes:
                start = perf_counter()
                run = simulate_bb84_round(
                    qubits, seed=seed, depolarizing_probability=noise,
                    interception_probability=interception, grouped=grouped,
                )
                elapsed = perf_counter() - start
                matches = len(run.matched_positions)
                errors = sum(
                    alice != bob for alice, bob in
                    zip(run.alice_sifted_bits, run.bob_sifted_bits, strict=True)
                )
                rows.append({
                    "seed": seed, "channel": channel, "grouped": grouped, "qubits": qubits,
                    "sifted": matches, "errors": errors, "qber": errors / matches if matches else None,
                    "expected_qber": noise / 2 + interception / 4, "wall_seconds": elapsed,
                })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qubits", type=int, default=4096)
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 43, 44])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("--output must name a new file")
    write_csv(args.output, benchmark(args.qubits, args.seeds))


if __name__ == "__main__":
    main()
