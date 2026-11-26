from dataclasses import replace

import pytest
from cryptography.exceptions import InvalidTag

from scheduling import simulation
from healthcare.encryption import decrypt_record, encrypt_record, key_from_bits
from healthcare.requests import HealthcareRequest, Priority
from qkd.finite_key import FiniteKeyEstimate
from qkd.pipeline import BB84Batch
from scheduling.simulation import BatchStatus, simulate_requests


def test_encryption_authenticates_payload_and_key_identifier():
    key = key_from_bits((0, 1) * 128)
    record = encrypt_record(b"synthetic diagnosis", key, "case-1")

    assert decrypt_record(record, key) == b"synthetic diagnosis"
    altered = bytes([record.ciphertext[0] ^ 1]) + record.ciphertext[1:]
    with pytest.raises(InvalidTag):
        decrypt_record(replace(record, ciphertext=altered), key)
    with pytest.raises(InvalidTag):
        decrypt_record(replace(record, key_id="case-2"), key)


def test_simulation_waits_for_generation_and_accounts_for_key_material():
    request = HealthcareRequest("case-1", 0, 2, Priority.EMERGENCY, payload=b"synthetic")

    result = simulate_requests([request], seed=42, qubit_budget=8192)

    assert [item.request_id for item in result.delivered] == ["case-1"]
    assert result.delivered[0].wait_seconds == 2
    assert not result.missed
    assert result.qubits_started == 8192
    assert result.generated_bits == 256 + result.wasted_bits + result.remaining_bits


def test_simulation_records_a_miss_when_no_qubit_budget_remains():
    request = HealthcareRequest("case-1", 0, 2, Priority.EMERGENCY)

    result = simulate_requests([request], seed=42, qubit_budget=0)

    assert result.missed == (request,)
    assert not result.delivered
    assert result.qubits_started == 0


def test_fractional_times_are_rejected_by_integer_tick_simulator():
    request = HealthcareRequest("case-1", 0.1, 0.9, Priority.EMERGENCY)
    with pytest.raises(ValueError, match="whole seconds"):
        simulate_requests([request], seed=42, qubit_budget=8192)


def accepted_batch(num_qubits, **kwargs):
    return BB84Batch(2048, 512, 0.0, 0, True, FiniteKeyEstimate(0.0, 1536), (1,) * 1536)


def test_early_exit_accounts_for_started_and_cancelled_generation():
    emergency = HealthcareRequest("a", 0, 2, Priority.EMERGENCY)
    routine = HealthcareRequest("b", 3, 6, Priority.ROUTINE)
    result = simulate_requests(
        [emergency, routine], seed=42, qubit_budget=16384, batch_runner=accepted_batch
    )

    assert result.qubits_started == 16384
    assert result.qubits_for(BatchStatus.COMPLETED) == 8192
    assert result.qubits_for(BatchStatus.CANCELLED) == 8192
    assert result.qubits_for(BatchStatus.UNFINISHED) == 0
    assert result.batches[1].cancelled_at == 3
    assert result.generated_bits == 1536
    assert [trace.allocation_id for trace in result.requests] == [0, 256]
    assert result.requests[1].pool_after == 1024


def test_explicit_observation_cutoff_preserves_unfinished_batch():
    request = HealthcareRequest("case-1", 0, 2, Priority.EMERGENCY)
    result = simulate_requests(
        [request], seed=42, qubit_budget=8192, batch_runner=accepted_batch, end_time=1
    )

    assert result.qubits_for(BatchStatus.UNFINISHED) == 8192
    assert result.batches[0].completed_at is None
    assert result.requests[0].reason == "observation_ended"
    assert result.unresolved == (request,)
    assert not result.missed


def test_rejected_batch_cannot_supply_key_material():
    request = HealthcareRequest("case-1", 0, 2, Priority.EMERGENCY)
    def rejected_batch(num_qubits, **kwargs):
        return replace(accepted_batch(num_qubits, **kwargs), agreement=False)

    with pytest.raises(RuntimeError, match="rejected or inconsistent"):
        simulate_requests([request], seed=42, qubit_budget=8192, batch_runner=rejected_batch)


def test_rejected_batch_is_traced_without_depositing_bits():
    request = HealthcareRequest("case-1", 0, 2, Priority.EMERGENCY)

    def rejected_batch(num_qubits, **kwargs):
        return replace(accepted_batch(num_qubits, **kwargs), agreement=False, amplified_bits=())

    result = simulate_requests(
        [request], seed=42, qubit_budget=8192, batch_runner=rejected_batch
    )

    assert result.missed == (request,)
    assert result.batches[0].rejection_reason == "reconciliation_failed"
    assert result.batches[0].estimated_bits == 1536
    assert result.generated_bits == result.batches[0].admitted_bits == 0


def test_duplicate_fifo_allocation_is_detected(monkeypatch):
    original = simulation.schedule_requests

    def defective_dispatch(*args, **kwargs):
        step = original(*args, **kwargs)
        allocations = tuple(replace(allocation, allocation_id=0) for allocation in step.allocated)
        return replace(step, allocated=allocations)

    monkeypatch.setattr(simulation, "schedule_requests", defective_dispatch)
    requests = [HealthcareRequest(str(index), 0, 2, Priority.EMERGENCY) for index in range(2)]
    with pytest.raises(RuntimeError, match="duplicate or out-of-order FIFO"):
        simulate_requests(requests, seed=42, qubit_budget=8192, batch_runner=accepted_batch)
