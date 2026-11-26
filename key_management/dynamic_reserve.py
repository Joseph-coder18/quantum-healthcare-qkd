"""Causal emergency reserve policy for the FD-QKS candidate study."""

from collections import deque
from dataclasses import dataclass
from math import ceil, isfinite


@dataclass(frozen=True)
class DynamicReserveConfig:
    minimum_bits: int = 256
    maximum_bits: int = 1536
    window_seconds: int = 8
    safety_margin: float = 1.0
    release_after: int = 3

    def __post_init__(self) -> None:
        if not all(type(bits) is int and bits >= 0 and bits % 256 == 0
                   for bits in (self.minimum_bits, self.maximum_bits)):
            raise ValueError("reserve bounds must be nonnegative multiples of 256")
        if self.minimum_bits > self.maximum_bits:
            raise ValueError("minimum reserve must not exceed maximum reserve")
        if not isfinite(self.safety_margin) or self.safety_margin < 0:
            raise ValueError("safety_margin must be finite and nonnegative")
        if not all(type(value) is int and value > 0
                   for value in (self.window_seconds, self.release_after)):
            raise ValueError("reserve timing settings must be positive whole seconds")


class DynamicReserve:
    """Raise protection immediately and release it after sustained lower demand."""

    def __init__(self, config: DynamicReserveConfig, initial_bits: int) -> None:
        self.config = config
        self.bits = min(config.maximum_bits, max(config.minimum_bits, initial_bits))
        self._arrivals: deque[tuple[int, int]] = deque()
        self._recent_count = 0
        self._lower_ticks = 0

    def update(
        self, now: int, *, arriving: int, pending: int, replenishment_seconds: int
    ) -> int:
        if arriving:
            self._arrivals.append((now, arriving))
            self._recent_count += arriving
        while self._arrivals and self._arrivals[0][0] <= now - self.config.window_seconds:
            _, count = self._arrivals.popleft()
            self._recent_count -= count
        rate = self._recent_count / self.config.window_seconds
        keys = ceil(pending + rate * replenishment_seconds + self.config.safety_margin)
        target = min(self.config.maximum_bits, max(self.config.minimum_bits, 256 * keys))
        if target >= self.bits:
            self.bits = target
            self._lower_ticks = 0
        else:
            self._lower_ticks += 1
            if self._lower_ticks >= self.config.release_after:
                self.bits = target
                self._lower_ticks = 0
        return self.bits
