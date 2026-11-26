"""Toeplitz privacy amplification for reconciled BB84 simulation data."""

from collections.abc import Sequence


def amplify_agreed_bits(
    alice_bits: Sequence[int],
    bob_bits: Sequence[int],
    output_length: int,
    public_seed: Sequence[int],
) -> tuple[int, ...]:
    """Check agreement and hash the common bits with a public Toeplitz seed.

    The simulator compares both sequences directly. The caller chooses the
    output length and supplies independent, uniformly random public seed bits.
    Seed position n - 1 sets the main diagonal for n input bits.
    """
    alice = tuple(alice_bits)
    if alice != tuple(bob_bits):
        raise ValueError("Alice and Bob's reconciled bits must agree")
    if any(bit not in (0, 1) for bit in alice):
        raise ValueError("input bits must be 0 or 1")
    if type(output_length) is not int or not 0 <= output_length <= len(alice):
        raise ValueError("output_length must be between zero and the input length")

    seed_length = len(alice) + output_length - 1 if output_length else 0
    if len(public_seed) != seed_length or any(bit not in (0, 1) for bit in public_seed):
        raise ValueError(f"public_seed must contain exactly {seed_length} binary bits")
    if output_length == 0:
        return ()

    # Pack the input in reverse column order so each Toeplitz row is a
    # contiguous window of the packed diagonal values.
    packed_input = int("".join(str(int(bit)) for bit in reversed(alice)), 2)
    packed_seed = int("".join(str(int(bit)) for bit in public_seed), 2)
    return tuple(
        ((packed_seed >> (output_length - 1 - row)) & packed_input).bit_count() % 2
        for row in range(output_length)
    )
