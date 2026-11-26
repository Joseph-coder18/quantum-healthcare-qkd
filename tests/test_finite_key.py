from qkd.finite_key import FiniteKeyEstimate, estimate_finite_key
from qkd.pipeline import run_bb84_batch


def test_finite_key_inverts_sampling_tail_and_deducts_disclosures():
    # If there is one error in two bits, a one-bit sample misses it half the time.
    assert estimate_finite_key(
        0, 1, 1, 0, sampling_failure_probability=0.5, penalty_bits=0
    ) == FiniteKeyEstimate(1.0, 0)
    assert estimate_finite_key(
        0, 1, 1, 0, sampling_failure_probability=0.75, penalty_bits=0
    ) == FiniteKeyEstimate(0.0, 1)
    assert estimate_finite_key(
        0, 1, 1, 1, sampling_failure_probability=0.75, penalty_bits=0
    ) == FiniteKeyEstimate(0.0, 0)


def test_ideal_batch_amplifies_to_the_estimated_length():
    batch = run_bb84_batch(4096, seed=42)

    assert batch.agreement is True
    assert batch.sampled_qber == 0
    assert batch.finite_key is not None
    assert len(batch.amplified_bits) == batch.finite_key.output_length > 0


def test_batch_without_enough_sifted_bits_produces_no_output():
    batch = run_bb84_batch(1, seed=42)

    assert batch.sampled_qber is None
    assert batch.amplified_bits == ()
