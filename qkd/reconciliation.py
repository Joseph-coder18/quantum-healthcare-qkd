"""Parity-based error reconciliation for simulated sifted BB84 bits."""

from collections.abc import Sequence
from dataclasses import dataclass
from random import Random


@dataclass(frozen=True)
class ReconciliationResult:
    bob_bits: tuple[int, ...]
    corrections: int
    disclosed_parity_bits: int


def reconcile_bits(
    alice_bits: Sequence[int],
    bob_bits: Sequence[int],
    *,
    block_sizes: Sequence[int] = (8, 16, 32, 64),
    seed: int | None = None,
) -> ReconciliationResult:
    """Run shuffled parity passes with binary search within odd-error blocks.

    Each comparison exchanges two parity bits. Errors may remain after the
    final pass, so callers must verify agreement before using the result.
    """
    if len(alice_bits) != len(bob_bits):
        raise ValueError("Alice and Bob must have the same number of bits")
    if any(bit not in (0, 1) for bit in alice_bits) or any(
        bit not in (0, 1) for bit in bob_bits
    ):
        raise ValueError("Alice and Bob's bits must be 0 or 1")
    if not block_sizes or any(type(size) is not int or size < 1 for size in block_sizes):
        raise ValueError("block_sizes must contain positive integers")

    corrected = list(bob_bits)
    positions = list(range(len(alice_bits)))
    random = Random(seed)
    corrections = 0
    disclosed_parity_bits = 0

    def parity_differs(block: Sequence[int]) -> bool:
        nonlocal disclosed_parity_bits
        disclosed_parity_bits += 2
        alice_parity = sum(alice_bits[index] for index in block) % 2
        bob_parity = sum(corrected[index] for index in block) % 2
        return alice_parity != bob_parity

    for size in block_sizes:
        random.shuffle(positions)
        for start in range(0, len(positions), size):
            block = positions[start : start + size]
            if not parity_differs(block):
                continue

            # An odd parity difference guarantees one odd half at each split.
            while len(block) > 1:
                midpoint = len(block) // 2
                left = block[:midpoint]
                block = left if parity_differs(left) else block[midpoint:]
            corrected[block[0]] ^= 1
            corrections += 1

    return ReconciliationResult(tuple(corrected), corrections, disclosed_parity_bits)
