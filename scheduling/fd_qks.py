"""Deadline-aware allocation for the FD-QKS simulation."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from math import floor, isfinite

from healthcare.requests import HealthcareRequest, Priority
from key_management.pool import KeyPool


class QueuePolicy(StrEnum):
    FD_QKS = "fd-qks"
    FCFS = "fcfs"
    STATIC_PRIORITY = "static-priority"
    EDF = "edf"
    DEADLINE_SENSITIVE = "deadline-sensitive"


@dataclass(frozen=True)
class Allocation:
    request: HealthcareRequest
    time: float
    key_bits: tuple[int, ...] = field(repr=False)
    effective_priority: int
    pool_before: int
    pool_after: int
    allocation_id: int
    queue_score: float | None = None


@dataclass(frozen=True)
class SchedulingStep:
    allocated: tuple[Allocation, ...]
    expired: tuple[HealthcareRequest, ...]
    deferred: tuple[HealthcareRequest, ...]


def effective_priority(
    request: HealthcareRequest, now: float, ageing_interval: float | None
) -> int:
    if ageing_interval is None or request.critical:
        return request.priority
    wait = now - request.arrival_time
    return min(Priority.URGENT, request.priority + floor(wait / ageing_interval))


def deadline_sensitive_score(request: HealthcareRequest, now: float) -> float:
    """Score an eligible request using class, elapsed slack and bounded wait."""
    slack = request.deadline - request.arrival_time
    wait = max(0.0, now - request.arrival_time)
    urgency = min(1.0, wait / slack) if slack else 1.0
    return request.priority + 2 * urgency + 0.25 * min(1.0, wait / 20)


def schedule_requests(
    requests: Iterable[HealthcareRequest],
    pool: KeyPool,
    now: float,
    *,
    ageing_interval: float | None = 10.0,
    policy: QueuePolicy = QueuePolicy.FD_QKS,
) -> SchedulingStep:
    """Allocate eligible requests in priority, deadline, then arrival order.

    A request may be served at its deadline. Future and unfunded requests are
    returned for later steps. Disabling ageing preserves base priorities.
    """
    if not isfinite(now) or now < 0:
        raise ValueError("now must be finite and nonnegative")
    if ageing_interval is not None and (not isfinite(ageing_interval) or ageing_interval <= 0):
        raise ValueError("ageing_interval must be positive and finite")

    requests = tuple(requests)
    if len({request.request_id for request in requests}) != len(requests):
        raise ValueError("request IDs must be unique")

    def rank(request: HealthcareRequest) -> tuple:
        arrival_order = (request.arrival_time, request.request_id)
        if policy == QueuePolicy.FCFS:
            return arrival_order
        if policy == QueuePolicy.STATIC_PRIORITY:
            return (-request.priority, *arrival_order)
        if policy == QueuePolicy.EDF:
            return (request.deadline, *arrival_order)
        if policy == QueuePolicy.DEADLINE_SENSITIVE:
            # Emergency precedence is independent of the ordinary score.
            score = 0.0 if request.critical else deadline_sensitive_score(request, now)
            return (not request.critical, -score, request.deadline, *arrival_order)

        priority = effective_priority(request, now, ageing_interval)
        return (-priority, request.deadline, *arrival_order)

    expired = tuple(request for request in requests if request.deadline < now)
    deferred = [request for request in requests if request.arrival_time > now]
    eligible = sorted(
        (request for request in requests if request.arrival_time <= now <= request.deadline),
        key=rank,
    )
    allocated = []
    for request in eligible:
        before = pool.available_bits
        allocation_id = pool.allocated_bits
        bits = pool.allocate(request.required_key_bits, critical=request.critical)
        if bits is None:
            deferred.append(request)
        else:
            priority = effective_priority(
                request, now, ageing_interval if policy == QueuePolicy.FD_QKS else None
            )
            allocated.append(Allocation(
                request, now, bits, priority, before, pool.available_bits, allocation_id,
                deadline_sensitive_score(request, now)
                if policy == QueuePolicy.DEADLINE_SENSITIVE and not request.critical else None,
            ))
    return SchedulingStep(tuple(allocated), expired, tuple(deferred))
