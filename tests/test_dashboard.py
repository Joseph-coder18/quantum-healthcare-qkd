from dataclasses import asdict
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from dashboard.logic import (
    DEFAULT_POLICY, LAB_POLICIES, MAX_QUBITS, pool_events, quantum_experiment,
    simulate_workload, transfer_record,
)
from scheduling.fd_qks import QueuePolicy
from scheduling.simulation import BatchStatus, GenerationPolicy


def test_live_quantum_summary_uses_simulated_output_and_separates_expectation():
    result = quantum_experiment(4096, 0.0, 0.0, 42)
    assert result.qber == result.theoretical_qber == 0
    assert result.sifted == 2060
    assert result.parity_bits > 0 and result.agreement is True
    assert result.amplified_bits == result.estimated_bits == 565
    assert "amplified_bits" in asdict(result)
    with pytest.raises(ValueError, match="Qubits"):
        quantum_experiment(MAX_QUBITS + 1, 0, 0, 42)
    disturbed = quantum_experiment(1, 0.2, 1, 42)
    assert disturbed.theoretical_qber == pytest.approx(0.30)
    assert disturbed.qber is None and disturbed.amplified_bits == 0


def test_pool_ledger_tracks_cutoff_and_uses_stabilized_v1_default():
    default = LAB_POLICIES[DEFAULT_POLICY]
    assert default.queue == QueuePolicy.FD_QKS
    assert default.generation == GenerationPolicy.ADAPTIVE
    assert default.reserve == 1024
    run = simulate_workload(
        "simultaneous", DEFAULT_POLICY, 42, 16384, noise=0, interception=0,
        use_workload_channel=True, cutoff=1,
    )
    assert run.result.qubits_for(BatchStatus.UNFINISHED) == 8192
    assert run.result.unresolved
    history = pool_events(run)
    assert history[0]["pool_bits"] == run.initial_stock
    assert history[-1]["pool_bits"] == run.result.remaining_bits
    assert all(event["protected_bits"] <= event["pool_bits"] for event in history)
    assert [event["seconds"] for event in history] == sorted(event["seconds"] for event in history)


def test_synthetic_transfer_verifies_and_returns_no_key():
    outcome = transfer_record("Synthetic triage note", demonstrate_tampering=True)
    assert outcome.verified and outcome.modified_rejected
    assert outcome.usable_bits >= 256
    assert len(bytes.fromhex(outcome.nonce_hex)) == 12
    assert len(bytes.fromhex(outcome.ciphertext_hex)) == len(outcome.plaintext_json.encode()) + 16
    assert set(asdict(outcome)) == {
        "usable_bits", "verified", "modified_rejected", "ciphertext_hex", "nonce_hex", "plaintext_json",
    }
    refused = transfer_record("Synthetic triage note", demonstrate_tampering=True, noise=1)
    assert not refused.verified and refused.ciphertext_hex is None


def test_all_six_dashboard_sections_and_live_actions():
    app = Path(__file__).resolve().parents[1] / "app.py"
    view = AppTest.from_file(str(app), default_timeout=30).run()
    assert not view.exception and len(view.metric) == 3

    def visit(section):
        view.get("segmented_control")[0].set_value(section).run()
        assert not view.exception, [item.message for item in view.exception]
        assert view.title[0].value == section

    def click(label):
        next(button for button in view.button if button.label == label).click().run()
        assert not view.exception, [item.message for item in view.exception]

    visit("Quantum Lab")
    click("Run BB84")
    assert {metric.label: metric.value for metric in view.metric}["Amplified output"] == "565 bits"
    visit("Scheduler Lab")
    assert view.selectbox[0].value == DEFAULT_POLICY
    click("Run scheduler")
    assert len(view.get("plotly_chart")) == 1 and len(view.dataframe) == 1
    visit("Key Management")
    assert len(view.get("plotly_chart")) == 1
    click("Run pool demonstration")
    assert any(metric.label == "Completed" for metric in view.metric)
    visit("Healthcare Transfer")
    click("Encrypt and verify")
    assert any("modified ciphertext was rejected" in item.value for item in view.success)
    visit("Research Results")
    assert len(view.get("plotly_chart")) == 2
    assert len(view.get("download_button")) == 3
