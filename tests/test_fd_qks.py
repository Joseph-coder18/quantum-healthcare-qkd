import pytest

from healthcare.requests import HealthcareRequest, Priority
from key_management.pool import KeyPool
from scheduling.fd_qks import QueuePolicy, schedule_requests


def test_critical_deadline_and_reserve():
    requests = [
        HealthcareRequest("ordinary", 0, 5, Priority.URGENT),
        HealthcareRequest("later", 0, 4, Priority.EMERGENCY),
        HealthcareRequest("critical", 0, 2, Priority.EMERGENCY),
        HealthcareRequest("expired", 0, 1, Priority.ROUTINE),
        HealthcareRequest("future", 3, 5, Priority.EMERGENCY),
    ]
    pool = KeyPool(256, emergency_reserve_bits=256)
    pool.replenish((1,) * 256)

    step = schedule_requests(requests, pool, now=2)

    assert [item.request.request_id for item in step.allocated] == ["critical"]
    assert [item.request_id for item in step.expired] == ["expired"]
    assert {item.request_id for item in step.deferred} == {"later", "future", "ordinary"}
    assert pool.available_bits == 0


def test_ageing_promotes_a_waiting_request_without_granting_reserve_access():
    older = HealthcareRequest("older", 0, 25, Priority.ADMINISTRATIVE)
    newer = HealthcareRequest("newer", 20, 30, Priority.URGENT)
    pool = KeyPool(512, emergency_reserve_bits=256)
    pool.replenish((0,) * 512)

    step = schedule_requests([newer, older], pool, now=20)

    assert [item.request for item in step.allocated] == [older]
    assert step.deferred == (newer,)
    assert pool.available_bits == 256


@pytest.mark.parametrize(
    ("policy", "expected"),
    [
        (QueuePolicy.FCFS, "oldest"),
        (QueuePolicy.STATIC_PRIORITY, "highest"),
        (QueuePolicy.EDF, "earliest-deadline"),
    ],
)
def test_baselines_choose_their_documented_order(policy, expected):
    requests = [
        HealthcareRequest("oldest", 0, 25, Priority.ADMINISTRATIVE),
        HealthcareRequest("highest", 1, 15, Priority.EMERGENCY),
        HealthcareRequest("earliest-deadline", 2, 10, Priority.URGENT),
    ]
    pool = KeyPool(256)
    pool.replenish((0,) * 256)

    step = schedule_requests(requests, pool, now=5, policy=policy)

    assert [allocation.request.request_id for allocation in step.allocated] == [expected]


def test_deadline_sensitive_queue_has_emergency_precedence_and_ordinary_urgency():
    routine = HealthcareRequest("routine", 0, 10, Priority.ROUTINE)
    urgent = HealthcareRequest("urgent", 9, 19, Priority.URGENT)
    emergency = HealthcareRequest("emergency", 9, 11, Priority.EMERGENCY)
    pool = KeyPool(1024, 256)
    pool.replenish((0,) * 768)

    result = schedule_requests(
        [urgent, routine, emergency], pool, 10, policy=QueuePolicy.DEADLINE_SENSITIVE,
    )
    assert [allocation.request for allocation in result.allocated] == [emergency, routine]
    assert result.allocated[1].queue_score > 4.0
    assert result.allocated[1].pool_after == 256


def test_deadline_sensitive_allows_zero_slack_request_at_its_deadline():
    request = HealthcareRequest("urgent", 0, 0, Priority.URGENT)
    pool = KeyPool(256)
    pool.replenish((0,) * 256)
    step = schedule_requests([request], pool, 0, policy=QueuePolicy.DEADLINE_SENSITIVE)
    assert step.allocated[0].queue_score == 5.0
