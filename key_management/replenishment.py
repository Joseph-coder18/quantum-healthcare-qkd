"""Adaptive BB84 batch sizing for a bounded simulated key pool."""

from dataclasses import dataclass
from math import ceil

from key_management.pool import KeyPool


@dataclass(frozen=True)
class ReplenishmentConfig:
    low_watermark: int = 2048
    high_watermark: int = 6144
    min_qubits: int = 1024
    max_qubits: int = 8192
    qubit_increment: int = 1024
    initial_yield: float = 0.12
    smoothing: float = 0.5

    def __post_init__(self) -> None:
        if not 0 <= self.low_watermark < self.high_watermark:
            raise ValueError("watermarks must be nonnegative and increasing")
        if not 0 < self.min_qubits <= self.max_qubits or self.qubit_increment <= 0:
            raise ValueError("batch sizes and increment must be positive and ordered")
        if not 0 < self.initial_yield <= 1 or not 0 < self.smoothing <= 1:
            raise ValueError("initial_yield and smoothing must be in (0, 1]")


class AdaptiveReplenishment:
    """Refill toward the high watermark using an observed bits-per-qubit yield."""

    def __init__(self, config: ReplenishmentConfig = ReplenishmentConfig()) -> None:
        self.config = config
        self.estimated_yield = config.initial_yield
        self._refilling = False

    def choose_batch(
        self,
        pool: KeyPool,
        *,
        ordinary_demand: int = 0,
        emergency_demand: int = 0,
        demand_only: bool = False,
    ) -> int:
        """Return a requested batch size, or zero when generation can wait."""
        if ordinary_demand < 0 or emergency_demand < 0:
            raise ValueError("pending demand must be nonnegative")
        config = self.config
        available = pool.available_bits
        capacity = available + pool.free_capacity_bits
        if config.high_watermark > capacity:
            raise ValueError("high watermark must fit in the pool")

        required_stock = emergency_demand
        if ordinary_demand:
            required_stock += pool.emergency_reserve_bits + ordinary_demand

        self._refilling = available < config.high_watermark and (
            self._refilling or available <= config.low_watermark
        )
        target_gap = config.high_watermark - available if self._refilling and not demand_only else 0
        demand_gap = max(0, required_stock - available)
        desired_bits = min(pool.free_capacity_bits, max(demand_gap, target_gap))
        if desired_bits == 0:
            return 0

        # Bound the estimate before rounding to avoid very large batch requests
        # when several consecutive BB84 batches give no usable output.
        if desired_bits >= config.max_qubits * self.estimated_yield:
            return config.max_qubits
        steps = ceil(desired_bits / (self.estimated_yield * config.qubit_increment))
        return min(config.max_qubits, max(config.min_qubits, steps * config.qubit_increment))

    def observe_batch(self, transmitted_qubits: int, generated_bits: int) -> None:
        """Update the estimate using output before pool-capacity truncation."""
        if not 0 <= generated_bits <= transmitted_qubits or transmitted_qubits <= 0:
            raise ValueError("batch counts must satisfy 0 <= generated <= transmitted")
        weight = self.config.smoothing
        observed_yield = generated_bits / transmitted_qubits
        self.estimated_yield = (1 - weight) * self.estimated_yield + weight * observed_yield
