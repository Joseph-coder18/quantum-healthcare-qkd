"""Timed scheduling of synthetic requests and asynchronous BB84 batches."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from math import ceil
from random import Random
from typing import Protocol

from healthcare.encryption import decrypt_record, encrypt_record, key_from_bits
from healthcare.requests import HealthcareRequest, Priority
from key_management.pool import KeyPool
from key_management.replenishment import AdaptiveReplenishment
from qkd.pipeline import BB84Batch, run_bb84_batch
from scheduling.fd_qks import QueuePolicy, schedule_requests


class GenerationPolicy(StrEnum):
    ADAPTIVE = "adaptive"
    FIXED = "fixed"
    DEMAND_ONLY = "demand-only"


class BatchRunner(Protocol):
    def __call__(
        self, num_qubits: int, *, seed: int, depolarizing_probability: float
    ) -> BB84Batch: ...


@dataclass(frozen=True)
class Delivery:
    request_id: str
    priority: Priority
    wait_seconds: float


@dataclass(frozen=True)
class SimulationResult:
    delivered: tuple[Delivery, ...]
    missed: tuple[HealthcareRequest, ...]
    qubits_started: int
    generated_bits: int
    wasted_bits: int
    remaining_bits: int


def simulate_requests(
    requests: Sequence[HealthcareRequest],
    *,
    seed: int,
    qubit_budget: int,
    qubits_per_second: int = 4096,
    reserve_bits: int = 1024,
    ageing_interval: float | None = 10.0,
    depolarizing_probability: float = 0.0,
    queue_policy: QueuePolicy = QueuePolicy.FD_QKS,
    generation_policy: GenerationPolicy = GenerationPolicy.ADAPTIVE,
    fixed_batch_qubits: int = 8192,
    batch_runner: BatchRunner = run_bb84_batch,
) -> SimulationResult:
    """Dispatch at integer-second ticks and account for batch generation delay."""
    if type(qubit_budget) is not int or qubit_budget < 0:
        raise ValueError("qubit_budget must be a nonnegative integer")
    if type(qubits_per_second) is not int or qubits_per_second <= 0:
        raise ValueError("qubits_per_second must be a positive integer")
    if type(fixed_batch_qubits) is not int or fixed_batch_qubits < 1024:
        raise ValueError("fixed_batch_qubits must be an integer of at least 1024")
    if any(request.required_key_bits != 256 for request in requests):
        raise ValueError("encrypted delivery requires 256-bit allocations")
    if len({request.request_id for request in requests}) != len(requests):
        raise ValueError("request IDs must be unique")

    pool = KeyPool(8192, reserve_bits)
    adaptive = AdaptiveReplenishment()
    rng = Random(seed)
    pending = sorted(requests, key=lambda request: request.arrival_time)
    delivered = []
    missed = []
    qubits_started = generated = wasted = 0
    in_flight = None
    last_tick = ceil(max((request.deadline for request in requests), default=0))

    for now in range(last_tick + 1):
        if in_flight is not None and in_flight[0] == now:
            _, qubits, batch_seed = in_flight
            batch = batch_runner(
                qubits, seed=batch_seed, depolarizing_probability=depolarizing_probability
            )
            size = len(batch.amplified_bits)
            adaptive.observe_batch(qubits, size)
            generated += size
            wasted += size - pool.replenish(batch.amplified_bits)
            in_flight = None

        step = schedule_requests(
            pending, pool, now, ageing_interval=ageing_interval, policy=queue_policy
        )
        missed.extend(step.expired)
        for allocation in step.allocated:
            request = allocation.request
            key = key_from_bits(allocation.key_bits)
            envelope = encrypt_record(request.payload, key, request.request_id)
            if decrypt_record(envelope, key) != request.payload:
                raise RuntimeError(f"delivery verification failed for {request.request_id}")
            delivered.append(Delivery(request.request_id, request.priority, now - request.arrival_time))

        pending = list(step.deferred)
        if not pending:
            break
        if in_flight is not None:
            continue

        ordinary = emergency = 0
        for request in pending:
            if request.arrival_time <= now < request.deadline:
                if request.critical:
                    emergency += request.required_key_bits
                else:
                    ordinary += request.required_key_bits
        desired = adaptive.choose_batch(
            pool,
            ordinary_demand=ordinary,
            emergency_demand=emergency,
            demand_only=generation_policy == GenerationPolicy.DEMAND_ONLY,
        )
        if desired and generation_policy == GenerationPolicy.FIXED:
            desired = fixed_batch_qubits
        qubits = min(desired, qubit_budget - qubits_started)
        if qubits >= adaptive.config.min_qubits:
            finish = now + ceil(qubits / qubits_per_second)
            if finish <= max(request.deadline for request in pending):
                qubits_started += qubits
                in_flight = (finish, qubits, rng.getrandbits(64))

    missed.extend(pending)
    return SimulationResult(tuple(delivered), tuple(missed), qubits_started, generated, wasted, pool.available_bits)
