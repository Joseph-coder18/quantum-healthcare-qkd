from experiments.phase10_study import phase10_manifest, workload
from experiments.phase10_metrics import _metrics
from healthcare.requests import HealthcareRequest, Priority
from qkd.finite_key import FiniteKeyEstimate
from qkd.pipeline import BB84Batch
from scheduling.simulation import ChannelCondition, simulate_requests


def test_development_and_held_out_workloads_use_disjoint_families_and_seeds():
    development = phase10_manifest("development")["workloads"]
    held_out = phase10_manifest("held-out")["workloads"]

    assert len({job["seed"] for job in development}) == 30
    assert len({job["seed"] for job in held_out}) == 30
    for field in ("scenario", "seed"):
        assert {job[field] for job in development}.isdisjoint(job[field] for job in held_out)
    assert development[0] == workload(development[0]["scenario"], development[0]["seed"])
    simultaneous = development[0]
    assert sum(request["arrival_time"] == 0 for request in simultaneous["requests"]) == 6
    assert any(condition["interception_probability"] > 0
               for job in development for condition in job["channel_schedule"])


def test_batches_retain_channel_at_start_and_initial_stock_is_conserved():
    calls = []

    def runner(num_qubits, **kwargs):
        calls.append((kwargs["depolarizing_probability"], kwargs.get("interception_probability", 0)))
        return BB84Batch(1, 1, 0, 0, True, FiniteKeyEstimate(0, 256), (1,) * 256)

    result = simulate_requests(
        [HealthcareRequest("first", 0, 2, Priority.EMERGENCY),
         HealthcareRequest("second", 4, 6, Priority.ROUTINE)],
        seed=42, qubit_budget=16384, initial_pool_bits=256, batch_runner=runner,
        channel_schedule=(ChannelCondition(0, 0.01), ChannelCondition(1, 0.05, 0.1)),
    )

    assert calls == [(0.01, 0), (0.05, 0.1)]
    assert [batch.interception_probability for batch in result.batches] == [0, 0.1]
    assert 256 + result.generated_bits == (
        256 * len(result.delivered) + result.remaining_bits + result.wasted_bits
    )


def test_phase10_metrics_keep_deadline_misses_out_of_served_waits():
    requests = [
        {"priority": "emergency", "arrival": "0", "completion_time": "0",
         "reason": "", "reserve_bits_used": "256"},
        {"priority": "routine", "arrival": "0", "completion_time": "4",
         "reason": "", "reserve_bits_used": "0"},
        {"priority": "routine", "arrival": "0", "completion_time": "",
         "reason": "deadline_missed", "reserve_bits_used": "0"},
    ]
    runs = [{"qubits_started": "8192", "qubits_completed": "4096", "remaining_bits": "256"}]
    result = _metrics(requests, runs)
    assert result["delivered"] == 2
    assert result["served_wait_p50"] == 2
    assert result["served_wait_p90"] == 3.6
    assert result["low_priority_expiry_rate"] == 0.5
    assert result["reserve_bits_used"] == 256
    assert result["started_qubits_per_delivery"] == 4096


def test_combined_manifest_has_a_paired_ablation_for_each_selected_component(tmp_path):
    calibration = tmp_path / "calibration.csv"
    calibration.write_text("qubits,qber,usable_bits\n4096,0.01,400\n")
    manifest = phase10_manifest(
        "held-out", grouped=True, comparison="combined", calibration=calibration,
        selection={"components": ["deadline-generation", "deadline-sensitive"]},
    )
    policies = manifest["policies"]
    assert policies["combined-v2"]["queue"] == "deadline-sensitive"
    assert policies["combined-v2"]["generation"] == "deadline-aware"
    assert policies["combined-without-deadline-generation"]["generation"] == "adaptive"
    assert policies["combined-without-deadline-sensitive"]["queue"] == "fd-qks"
    assert len({workload["seed"] for workload in manifest["workloads"]}) == 30
