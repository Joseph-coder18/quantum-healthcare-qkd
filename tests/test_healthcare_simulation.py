from dataclasses import replace

import pytest
from cryptography.exceptions import InvalidTag

from healthcare.encryption import decrypt_record, encrypt_record, key_from_bits
from healthcare.requests import HealthcareRequest, Priority
from scheduling.simulation import simulate_requests


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
