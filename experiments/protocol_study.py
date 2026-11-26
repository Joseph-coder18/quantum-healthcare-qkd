"""Measure simulated BB84 correctness, disturbance, yield, and AES delivery."""

import argparse
from dataclasses import replace
from pathlib import Path
from time import perf_counter_ns

from cryptography.exceptions import InvalidTag

from experiments.scheduling_study import write_csv
from healthcare.encryption import decrypt_record, encrypt_record
from qkd.bb84 import simulate_bb84_round
from qkd.pipeline import run_bb84_batch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True, help="new output directory")
    destination = parser.parse_args().output_dir
    if destination.exists():
        parser.error("--output-dir must name a new directory")
    correctness = []
    protocol = []
    for seed in (42, 43, 44):
        ideal = simulate_bb84_round(4096, seed=seed)
        correctness.append({
            "seed": seed,
            "qubits": 4096,
            "sifted": len(ideal.matched_positions),
            "sifted_errors": sum(a != b for a, b in
                                 zip(ideal.alice_sifted_bits, ideal.bob_sifted_bits)),
        })
        cases = [
            ("interception", 4096, 0.0, fraction) for fraction in (0.0, 0.25, 0.5, 1.0)
        ] + [
            ("noise", 4096, noise, 0.0) for noise in (0.0, 0.01, 0.02, 0.04, 0.08)
        ] + [
            ("finite_key", size, 0.02, 0.0) for size in (1024, 2048, 4096, 8192)
        ]
        batches = {}
        for experiment, size, noise, intercept in cases:
            settings = (size, noise, intercept)
            if settings not in batches:
                batches[settings] = run_bb84_batch(
                    size, seed=seed, depolarizing_probability=noise,
                    interception_probability=intercept,
                )
            batch = batches[settings]
            protocol.append({
                "experiment": experiment, "seed": seed, "qubits": size,
                "depolarization": noise, "interception": intercept,
                "sifted": batch.sifted_count, "sampled": batch.sampled_count,
                "sampled_qber": batch.sampled_qber,
                "remaining_bit_error_upper": batch.finite_key.remaining_bit_error_upper,
                "disclosed_parity_bits": batch.disclosed_parity_bits,
                "agreement": batch.agreement, "estimated_bits": batch.finite_key.output_length,
                "amplified_bits": len(batch.amplified_bits),
            })
        print(f"Completed BB84 seed {seed}", flush=True)

    encryption = []
    for size in (128, 1024, 16384):
        payload = b"x" * size
        for trial in range(30):
            key = (size * 30 + trial).to_bytes(32, "big")
            start = perf_counter_ns()
            record = encrypt_record(payload, key, f"{size}-{trial}")
            encrypted_at = perf_counter_ns()
            recovered = decrypt_record(record, key)
            decrypted_at = perf_counter_ns()
            if recovered != payload:
                raise RuntimeError("plaintext mismatch")

            corrupted = bytes([record.ciphertext[0] ^ 1]) + record.ciphertext[1:]
            try:
                decrypt_record(replace(record, ciphertext=corrupted), key)
            except InvalidTag:
                tamper_rejected = True
            else:
                raise RuntimeError("tampering was accepted")
            encryption.append({
                "payload_bytes": size, "trial": trial, "round_trip_correct": True,
                "tamper_rejected": tamper_rejected, "encrypt_ns": encrypted_at - start,
                "decrypt_ns": decrypted_at - encrypted_at,
            })
    destination.mkdir(parents=True)
    write_csv(destination / "bb84_correctness.csv", correctness)
    write_csv(destination / "bb84_channel_and_yield.csv", protocol)
    write_csv(destination / "encryption.csv", encryption)


if __name__ == "__main__":
    main()
