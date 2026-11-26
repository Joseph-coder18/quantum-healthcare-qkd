"""Timed scheduling of synthetic requests and asynchronous BB84 batches."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from math import ceil
from random import Random
from typing import Protocol

from healthcare.encryption import decrypt_record, encrypt_record, key_from_bits
from healthcare.requests import HealthcareRequest, Priority
from key_management.dynamic_reserve import DynamicReserve, DynamicReserveConfig
from key_management.pool import KeyPool
from key_management.replenishment import AdaptiveReplenishment, ReplenishmentConfig
from qkd.pipeline import BB84Batch, run_bb84_batch
from scheduling.fd_qks import QueuePolicy, effective_priority, schedule_requests


class GenerationPolicy(StrEnum):
    ADAPTIVE = "adaptive"
    FIXED = "fixed"
    DEMAND_ONLY = "demand-only"


class BatchRunner(Protocol):
    def __call__(
        self, num_qubits: int, *, seed: int, depolarizing_probability: float
    ) -> BB84Batch: ...


@dataclass(frozen=True)
class ChannelCondition:
    start: int
    depolarizing_probability: float = 0.0
    interception_probability: float = 0.0

    def __post_init__(self) -> None:
        if type(self.start) is not int or self.start < 0:
            raise ValueError("channel start must be a nonnegative whole second")
        if not all(0 <= p <= 1 for p in (
            self.depolarizing_probability, self.interception_probability,
        )):
            raise ValueError("channel probabilities must be between zero and one")


class BatchStatus(StrEnum):
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    UNFINISHED = "unfinished"


@dataclass(frozen=True)
class BatchTrace:
    batch_id: int
    batch_seed: int
    qubits: int
    started_at: int
    scheduled_completion: int
    status: BatchStatus = BatchStatus.UNFINISHED
    completed_at: int | None = None
    cancelled_at: int | None = None
    sampled_qber: float | None = None
    estimated_bits: int | None = None
    output_bits: int | None = None
    admitted_bits: int = 0
    rejection_reason: str | None = None
    pool_at_start: int = 0
    pool_before: int = 0
    pool_after: int = 0
    reserve_bits: int = 0
    depolarizing_probability: float = 0.0
    interception_probability: float = 0.0


@dataclass(frozen=True)
class RequestTrace:
    request_id: str
    priority: str
    arrival: float
    deadline: float
    effective_priority: int
    allocation_time: float | None
    completion_time: float | None
    reason: str | None
    pool_before: int
    pool_after: int
    reserve_bits: int
    allocation_id: int | None = None
    outcome_at: float | None = None
    reserve_bits_used: int = 0


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
    requests: tuple[RequestTrace, ...]
    batches: tuple[BatchTrace, ...]
    unresolved: tuple[HealthcareRequest, ...] = ()

    def qubits_for(self, status: BatchStatus) -> int:
        return sum(batch.qubits for batch in self.batches if batch.status == status)


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
    end_time: int | None = None,
    pool_capacity_bits: int = 8192,
    replenishment: ReplenishmentConfig = ReplenishmentConfig(),
    channel_schedule: Sequence[ChannelCondition] = (),
    initial_pool_bits: int = 0,
    dynamic_reserve: DynamicReserveConfig | None = None,
) -> SimulationResult:
    """Dispatch at integer-second ticks and account for batch generation delay."""
    if type(qubit_budget) is not int or qubit_budget < 0:
        raise ValueError("qubit_budget must be a nonnegative integer")
    if type(qubits_per_second) is not int or qubits_per_second <= 0:
        raise ValueError("qubits_per_second must be a positive integer")
    if type(fixed_batch_qubits) is not int or fixed_batch_qubits < replenishment.min_qubits:
        raise ValueError("fixed_batch_qubits must be an integer at least as large as min_qubits")
    if any(request.required_key_bits != 256 for request in requests):
        raise ValueError("encrypted delivery requires 256-bit allocations")
    if len({request.request_id for request in requests}) != len(requests):
        raise ValueError("request IDs must be unique")
    if any(int(value) != value for request in requests
           for value in (request.arrival_time, request.deadline)):
        raise ValueError("simulation request arrivals and deadlines must be whole seconds")
    if end_time is not None and (type(end_time) is not int or end_time < 0):
        raise ValueError("end_time must be a nonnegative integer")
    if type(initial_pool_bits) is not int or not 0 <= initial_pool_bits <= pool_capacity_bits:
        raise ValueError("initial_pool_bits must be a whole bit count within pool capacity")
    if channel_schedule and (
        channel_schedule[0].start != 0
        or any(a.start >= b.start for a, b in zip(channel_schedule, channel_schedule[1:]))
    ):
        raise ValueError("channel schedule must start at zero and have increasing start times")

    pool = KeyPool(pool_capacity_bits, reserve_bits)
    if dynamic_reserve is not None and dynamic_reserve.maximum_bits > pool_capacity_bits:
        raise ValueError("maximum dynamic reserve must fit in the pool")
    reserve_controller = DynamicReserve(dynamic_reserve, reserve_bits) if dynamic_reserve else None
    adaptive = AdaptiveReplenishment(replenishment)
    rng = Random(seed)
    initial_rng = Random(f"initial-pool:{seed}")
    pool.replenish(initial_rng.getrandbits(1) for _ in range(initial_pool_bits))
    channel = ChannelCondition(0, depolarizing_probability)
    changes = iter(channel_schedule)
    next_channel = next(changes, None)
    pending = sorted(requests, key=lambda request: request.arrival_time)
    delivered = []
    missed = []
    request_traces = []
    batches = []
    allocated_ids = set()
    consumed = 0
    qubits_started = generated = wasted = 0
    in_flight = None
    last_tick = int(max((request.deadline for request in requests), default=0))
    if end_time is not None:
        last_tick = min(last_tick, end_time)

    def record_unserved(request: HealthcareRequest, tick: int, reason: str) -> None:
        priority = effective_priority(
            request, max(tick, request.arrival_time),
            ageing_interval if queue_policy == QueuePolicy.FD_QKS else None,
        )
        request_traces.append(RequestTrace(
            request.request_id, request.priority.name.lower(), request.arrival_time,
            request.deadline, priority, None, None, reason, pool.available_bits,
            pool.available_bits, pool.emergency_reserve_bits, outcome_at=tick,
        ))

    for now in range(last_tick + 1):
        if next_channel is not None and next_channel.start == now:
            channel = next_channel
            next_channel = next(changes, None)
        if in_flight is not None and in_flight.scheduled_completion == now:
            disturbance = {}
            if in_flight.interception_probability:
                disturbance["interception_probability"] = in_flight.interception_probability
            batch = batch_runner(
                in_flight.qubits, seed=in_flight.batch_seed,
                depolarizing_probability=in_flight.depolarizing_probability, **disturbance,
            )
            size = len(batch.amplified_bits)
            estimate = batch.finite_key.output_length if batch.finite_key is not None else None
            if size and (batch.agreement is not True or size != estimate):
                raise RuntimeError("rejected or inconsistent batch supplied key material")
            adaptive.observe_batch(in_flight.qubits, size)
            generated += size
            before = pool.available_bits
            admitted = pool.replenish(batch.amplified_bits)
            wasted += size - admitted
            reason = None
            if batch.agreement is None:
                reason = "insufficient_sifted_bits"
            elif batch.agreement is False:
                reason = "reconciliation_failed"
            elif not size:
                reason = "zero_usable_output"
            batches.append(replace(
                in_flight, status=BatchStatus.COMPLETED, completed_at=now,
                sampled_qber=batch.sampled_qber, estimated_bits=estimate, output_bits=size,
                admitted_bits=admitted, rejection_reason=reason, pool_before=before,
                pool_after=pool.available_bits,
            ))
            in_flight = None

        if reserve_controller is not None:
            emergencies = [
                request for request in pending
                if request.critical and request.arrival_time <= now <= request.deadline
            ]
            replenishment_seconds = (
                in_flight.scheduled_completion - now if in_flight is not None
                else ceil(fixed_batch_qubits / qubits_per_second)
            )
            pool.set_emergency_reserve(reserve_controller.update(
                now, arriving=sum(request.arrival_time == now for request in emergencies),
                pending=len(emergencies), replenishment_seconds=replenishment_seconds,
            ))
        current_reserve = pool.emergency_reserve_bits
        stock_before_dispatch = pool.available_bits
        step = schedule_requests(
            pending, pool, now, ageing_interval=ageing_interval, policy=queue_policy
        )
        missed.extend(step.expired)
        for request in step.expired:
            if request.deadline >= now:
                raise RuntimeError("request expired before its deadline")
            record_unserved(request, now, "deadline_missed")
        for allocation in step.allocated:
            request = allocation.request
            if request.request_id in allocated_ids:
                raise RuntimeError("duplicate allocation")
            if allocation.allocation_id != consumed:
                raise RuntimeError("duplicate or out-of-order FIFO key allocation")
            if not request.arrival_time <= allocation.time <= request.deadline:
                raise RuntimeError("allocation outside request timing window")
            if allocation.pool_before != stock_before_dispatch or (
                allocation.pool_before - allocation.pool_after != request.required_key_bits
            ):
                raise RuntimeError("allocation stock conservation failed")
            if not request.critical and allocation.pool_after < current_reserve:
                raise RuntimeError("ordinary allocation consumed the emergency reserve")
            key = key_from_bits(allocation.key_bits)
            envelope = encrypt_record(request.payload, key, request.request_id)
            if decrypt_record(envelope, key) != request.payload:
                raise RuntimeError(f"delivery verification failed for {request.request_id}")
            delivered.append(Delivery(request.request_id, request.priority, now - request.arrival_time))
            allocated_ids.add(request.request_id)
            request_traces.append(RequestTrace(
                request.request_id, request.priority.name.lower(), request.arrival_time,
                request.deadline, allocation.effective_priority, allocation.time, now, None,
                allocation.pool_before, allocation.pool_after, current_reserve,
                allocation.allocation_id, now,
                min(allocation.pool_before, current_reserve) - min(allocation.pool_after, current_reserve),
            ))
            consumed += request.required_key_bits
            stock_before_dispatch = allocation.pool_after
        if stock_before_dispatch != pool.available_bits:
            raise RuntimeError("dispatch stock conservation failed")

        pending = list(step.deferred)
        if not pending:
            if in_flight is not None:
                batches.append(replace(in_flight, status=BatchStatus.CANCELLED, cancelled_at=now))
                in_flight = None
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
                in_flight = BatchTrace(
                    len(batches), rng.getrandbits(64), qubits, now, finish,
                    pool_at_start=pool.available_bits, pool_before=pool.available_bits,
                    pool_after=pool.available_bits,
                    reserve_bits=current_reserve,
                    depolarizing_probability=channel.depolarizing_probability,
                    interception_probability=channel.interception_probability,
                )

    if in_flight is not None:
        batches.append(in_flight)
    unresolved = []
    for request in pending:
        reason = "deadline_missed" if request.deadline <= last_tick else "observation_ended"
        record_unserved(request, last_tick, reason)
        if reason == "deadline_missed":
            missed.append(request)
        else:
            unresolved.append(request)
    if qubits_started != sum(batch.qubits for batch in batches) or qubits_started > qubit_budget:
        raise RuntimeError("generation budget conservation failed")
    if initial_pool_bits + generated != consumed + wasted + pool.available_bits or (
        initial_pool_bits + sum(batch.admitted_bits for batch in batches)
        != consumed + pool.available_bits
    ) or pool.allocated_bits != consumed:
        raise RuntimeError("key conservation failed")
    if len({trace.request_id for trace in request_traces}) != len(requests):
        raise RuntimeError("request trace accounting failed")
    return SimulationResult(
        tuple(delivered), tuple(missed), qubits_started, generated, wasted, pool.available_bits,
        tuple(request_traces), tuple(batches), tuple(unresolved),
    )
