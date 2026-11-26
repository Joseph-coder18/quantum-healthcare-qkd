from experiments.phase10_study import phase10_manifest, workload
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
