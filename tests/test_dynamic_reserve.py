import pytest

from healthcare.requests import HealthcareRequest, Priority
from key_management.dynamic_reserve import DynamicReserve, DynamicReserveConfig
from scheduling.simulation import simulate_requests


def test_reserve_increases_immediately_and_releases_after_lower_demand():
    policy = DynamicReserve(
        DynamicReserveConfig(window_seconds=2, release_after=2, maximum_bits=1024), 256
    )
    assert policy.update(0, arriving=2, pending=2, replenishment_seconds=2) == 1024
    assert policy.update(1, arriving=0, pending=0, replenishment_seconds=2) == 1024
    assert policy.update(2, arriving=0, pending=0, replenishment_seconds=2) == 256


def test_dynamic_reserve_never_grants_urgent_requests_emergency_access():
    result = simulate_requests(
        [HealthcareRequest("urgent", 0, 1, Priority.URGENT),
         HealthcareRequest("emergency", 0, 1, Priority.EMERGENCY)],
        seed=1, qubit_budget=0, initial_pool_bits=512,
        dynamic_reserve=DynamicReserveConfig(),
    )
    assert [delivery.request_id for delivery in result.delivered] == ["emergency"]
    assert result.requests[0].reserve_bits_used == 256
    assert result.requests[1].reserve_bits_used == 0
    assert result.remaining_bits == 256


def test_future_emergency_does_not_raise_reserve_early():
    current = HealthcareRequest("routine", 0, 3, Priority.ROUTINE)
    later = HealthcareRequest("later", 8, 10, Priority.EMERGENCY)
    options = dict(seed=1, qubit_budget=0, initial_pool_bits=512, reserve_bits=256,
                   dynamic_reserve=DynamicReserveConfig(safety_margin=0))
    original = simulate_requests([current], **options)
    with_future = simulate_requests([current, later], **options)
    assert original.requests[0] == with_future.requests[0]


def test_dynamic_reserve_rejects_invalid_bounds():
    with pytest.raises(ValueError, match="multiples"):
        DynamicReserveConfig(minimum_bits=257)
