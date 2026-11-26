"""Run BB84 and its simulated key post-processing as one batch."""

from dataclasses import dataclass
from math import ceil
from random import Random

from qkd.bb84 import estimate_qber, simulate_bb84_round
from qkd.finite_key import FiniteKeyEstimate, estimate_finite_key
from qkd.privacy_amplification import amplify_agreed_bits
from qkd.reconciliation import reconcile_bits


@dataclass(frozen=True)
class BB84Batch:
    sifted_count: int
    sampled_count: int
    sampled_qber: float | None
    disclosed_parity_bits: int
    agreement: bool | None
    finite_key: FiniteKeyEstimate | None
    amplified_bits: tuple[int, ...]


def run_bb84_batch(
    num_qubits: int,
    *,
    seed: int | None = None,
    sample_fraction: float = 0.25,
    depolarizing_probability: float = 0.0,
    interception_probability: float = 0.0,
) -> BB84Batch:
    """Return batch metrics and amplified bits for the engineering simulation."""
    if not 0 < sample_fraction < 1:
        raise ValueError("sample_fraction must be between 0 and 1")

    rng = Random(seed)
    round_result = simulate_bb84_round(
        num_qubits,
        seed=rng.getrandbits(64),
        depolarizing_probability=depolarizing_probability,
        interception_probability=interception_probability,
    )
    sifted_count = len(round_result.matched_positions)
    if sifted_count < 2:
        return BB84Batch(sifted_count, 0, None, 0, None, None, ())

    sample_size = min(ceil(sifted_count * sample_fraction), sifted_count - 1)
    sample = estimate_qber(round_result, sample_size, seed=rng.getrandbits(64))
    alice = sample.alice_remaining_bits
    reconciliation = reconcile_bits(alice, sample.bob_remaining_bits, seed=rng.getrandbits(64))
    bob = reconciliation.bob_bits
    finite_key = estimate_finite_key(
        sample.error_count, sample_size, len(alice), reconciliation.disclosed_parity_bits
    )

    agreement = alice == bob
    amplified = ()
    if agreement and finite_key.output_length > 0:
        seed_length = len(alice) + finite_key.output_length - 1
        public_seed = tuple(rng.getrandbits(1) for _ in range(seed_length))
        amplified = amplify_agreed_bits(alice, bob, finite_key.output_length, public_seed)

    return BB84Batch(
        sifted_count,
        sample_size,
        sample.qber,
        reconciliation.disclosed_parity_bits,
        agreement,
        finite_key,
        amplified,
    )
