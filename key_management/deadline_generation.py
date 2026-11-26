"""Causal BB84 candidate selection from empirical usable-yield profiles."""

from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil, floor

from healthcare.requests import HealthcareRequest
from key_management.pool import KeyPool


@dataclass(frozen=True)
class YieldObservation:
    qubits: int
    qber: float
    usable_bits: int

    def __post_init__(self) -> None:
        if type(self.qubits) is not int or self.qubits <= 0:
            raise ValueError("calibration qubits must be a positive integer")
        if not 0 <= self.qber <= 1 or not 0 <= self.usable_bits <= self.qubits:
            raise ValueError("invalid yield observation")


@dataclass(frozen=True)
class BatchChoice:
    qubits: int
    predicted_bits: float
    probability_one_key: float
    observable_qber: float
    recovery_probe: bool = False


def _quality_bin(qber: float) -> int:
    return sum(qber >= limit for limit in (0.005, 0.015, 0.03, 0.05))


class DeadlineGeneration:
    """Compare feasible sizes using expected stock and deadlines known now."""

    def __init__(self, observations: Sequence[YieldObservation]) -> None:
        if not observations:
            raise ValueError("deadline generation requires empirical yield observations")
        groups: dict[int, dict[int, list[int]]] = {}
        for row in observations:
            groups.setdefault(row.qubits, {}).setdefault(_quality_bin(row.qber), []).append(row.usable_bits)
        self._profiles: dict[int, dict[int, tuple[float, float]]] = {
            size: {
                bucket: (sum(bits) / len(bits), sum(value >= 256 for value in bits) / len(bits))
                for bucket, bits in buckets.items()
            }
            for size, buckets in groups.items()
        }
        self.observable_qber = 0.01
        self._last_launch = -6

    def observe(self, qber: float | None) -> None:
        if qber is not None:
            self.observable_qber = qber

    def choose(
        self, pool: KeyPool, pending: Sequence[HealthcareRequest], *, now: int,
        remaining_qubits: int, qubits_per_second: int, min_qubits: int, max_qubits: int,
    ) -> BatchChoice | None:
        active = [request for request in pending if request.arrival_time <= now < request.deadline]
        if not active or pool.free_capacity_bits < 256:
            return None
        available = pool.available_bits
        reserve = pool.emergency_reserve_bits
        candidates = []
        probes = []
        quality = _quality_bin(self.observable_qber)
        for size, profiles in self._profiles.items():
            if not min_qubits <= size <= min(max_qubits, remaining_qubits):
                continue
            duration = ceil(size / qubits_per_second)
            viable = [request for request in active if request.deadline >= now + duration]
            if not viable:
                continue
            emergency = sum(request.critical for request in viable)
            ordinary = len(viable) - emergency
            if available >= 256 * (emergency + ordinary) + (reserve if ordinary else 0):
                continue
            bucket = min(profiles, key=lambda key: (abs(key - quality), -key))
            predicted, probability = profiles[bucket]
            choice = BatchChoice(size, predicted, probability, self.observable_qber)
            if predicted < 256 or probability < 0.5:
                if size >= 4096:
                    probes.append(choice)
                continue
            stock = available + min(pool.free_capacity_bits, floor(predicted))
            served_emergency = min(emergency, stock // 256)
            served_ordinary = min(ordinary, max(0, stock - 256 * served_emergency - reserve) // 256)
            existing_emergency = min(emergency, available // 256)
            existing_ordinary = min(
                ordinary, max(0, available - 256 * existing_emergency - reserve) // 256
            )
            gain = served_emergency + served_ordinary - existing_emergency - existing_ordinary
            if gain > 0:
                priority = (served_emergency - existing_emergency, gain, -duration, -size)
                candidates.append((priority, choice))
        if candidates:
            choice = max(candidates, key=lambda item: item[0])[1]
        elif probes and now - self._last_launch >= 6:
            probe = max(probes, key=lambda item: item.qubits)
            choice = BatchChoice(
                probe.qubits, probe.predicted_bits, probe.probability_one_key,
                probe.observable_qber, recovery_probe=True,
            )
        else:
            return None
        self._last_launch = now
        return choice
