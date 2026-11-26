"""In-memory key pool for the healthcare scheduling simulation."""

from collections import deque
from collections.abc import Iterable


class KeyPool:
    """Store simulated key bits and protect a reserve for critical allocations."""

    def __init__(self, capacity_bits: int, emergency_reserve_bits: int = 0) -> None:
        if type(capacity_bits) is not int or capacity_bits <= 0:
            raise ValueError("capacity_bits must be a positive integer")
        if (
            type(emergency_reserve_bits) is not int
            or not 0 <= emergency_reserve_bits <= capacity_bits
        ):
            raise ValueError("emergency_reserve_bits must be between zero and capacity")
        self._capacity_bits = capacity_bits
        self._reserve_bits = emergency_reserve_bits
        self._bits: deque[int] = deque()

    @property
    def available_bits(self) -> int:
        return len(self._bits)

    @property
    def free_capacity_bits(self) -> int:
        return self._capacity_bits - self.available_bits

    @property
    def ordinary_available_bits(self) -> int:
        return max(0, self.available_bits - self._reserve_bits)

    @property
    def emergency_reserve_bits(self) -> int:
        return self._reserve_bits

    def replenish(self, bits: Iterable[int]) -> int:
        """Store as many incoming bits as fit and return the number accepted."""
        incoming = tuple(bits)
        if any(type(bit) is not int or bit not in (0, 1) for bit in incoming):
            raise ValueError("key material must contain only integer bits")
        accepted = min(len(incoming), self.free_capacity_bits)
        self._bits.extend(incoming[:accepted])
        return accepted

    def allocate(self, bit_count: int, *, critical: bool = False) -> tuple[int, ...] | None:
        """Consume a complete allocation in FIFO order, or leave the pool intact."""
        if type(bit_count) is not int or bit_count <= 0:
            raise ValueError("bit_count must be a positive integer")
        available = self.available_bits if critical else self.ordinary_available_bits
        if bit_count > available:
            return None
        return tuple(self._bits.popleft() for _ in range(bit_count))
