"""Finite-sample key yield model for BB84 simulation experiments."""

from dataclasses import dataclass
from math import floor, log2

from scipy.stats import hypergeom


@dataclass(frozen=True)
class FiniteKeyEstimate:
    remaining_bit_error_upper: float
    output_length: int


def estimate_finite_key(
    sample_errors: int,
    sample_size: int,
    remaining_bits: int,
    disclosed_parity_bits: int,
    *,
    sampling_failure_probability: float = 0.01,
    penalty_bits: int = 128,
) -> FiniteKeyEstimate:
    """Estimate yield using a bit-error bound as a proxy for phase errors.

    The output length is a simulation metric. The sampling confidence
    applies to the undisclosed bit errors prior to reconciliation.
    """
    if any(
        type(value) is not int or value < 0
        for value in (sample_errors, sample_size, remaining_bits, disclosed_parity_bits, penalty_bits)
    ):
        raise ValueError("bit counts must be nonnegative integers")
    if sample_size == 0 or sample_errors > sample_size:
        raise ValueError("sample must be nonempty with at most one error per sampled bit")
    if not 0 < sampling_failure_probability < 1:
        raise ValueError("sampling_failure_probability must be between 0 and 1")
    if remaining_bits == 0:
        return FiniteKeyEstimate(0.0, 0)

    # Invert the lower tail of the number of errors sampled without replacement.
    population_size = sample_size + remaining_bits
    low, high = sample_errors, sample_errors + remaining_bits
    while low < high:
        total_errors = (low + high + 1) // 2
        probability = hypergeom.cdf(sample_errors, population_size, total_errors, sample_size)
        if probability >= sampling_failure_probability:
            low = total_errors
        else:
            high = total_errors - 1

    upper = (low - sample_errors) / remaining_bits
    # Entropy over the allowed interval reaches its maximum at one half.
    error_rate = min(upper, 0.5)
    entropy = (
        -error_rate * log2(error_rate) - (1 - error_rate) * log2(1 - error_rate)
        if error_rate > 0
        else 0.0
    )
    output_length = floor(remaining_bits * (1 - entropy)) - disclosed_parity_bits - penalty_bits
    return FiniteKeyEstimate(upper, max(0, output_length))
