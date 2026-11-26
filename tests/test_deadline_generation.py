from healthcare.requests import HealthcareRequest, Priority
from key_management.deadline_generation import DeadlineGeneration, YieldObservation
from key_management.pool import KeyPool
from qkd.finite_key import FiniteKeyEstimate
from qkd.pipeline import BB84Batch
from scheduling.simulation import ChannelCondition, GenerationPolicy, simulate_requests


CALIBRATION = (
    YieldObservation(2048, 0.01, 100),
    YieldObservation(4096, 0.01, 400),
    YieldObservation(8192, 0.01, 1024),
    YieldObservation(4096, 0.06, 0),
    YieldObservation(8192, 0.06, 0),
)


def test_candidate_uses_quick_viable_batch_for_an_imminent_emergency():
    controller = DeadlineGeneration(CALIBRATION)
    urgent = HealthcareRequest("emergency", 0, 1, Priority.EMERGENCY)
    ordinary = HealthcareRequest("routine", 0, 5, Priority.ROUTINE)
    choice = controller.choose(
        KeyPool(8192), [urgent, ordinary], now=0,
        remaining_qubits=8192, qubits_per_second=4096, min_qubits=1024, max_qubits=8192,
    )

    assert choice is not None and choice.qubits == 4096
    assert choice.predicted_bits == 400
    assert choice.probability_one_key == 1


def test_low_yield_only_allows_rate_limited_large_recovery_probe():
    controller = DeadlineGeneration(CALIBRATION)
    controller.observe(0.06)
    pending = [HealthcareRequest("routine", 0, 10, Priority.ROUTINE)]
    pool = KeyPool(8192)
    settings = dict(remaining_qubits=8192, qubits_per_second=4096, min_qubits=1024, max_qubits=8192)
    choice = controller.choose(pool, pending, now=0, **settings)
    assert choice is not None and choice.recovery_probe and choice.qubits == 8192
    assert controller.choose(pool, pending, now=5, **settings) is None
    assert controller.choose(pool, pending, now=6, **settings) == choice


def test_deadline_candidate_ignores_future_arrivals_and_records_yield_separately():
    immediate = HealthcareRequest("emergency", 2, 3, Priority.EMERGENCY)
    future = HealthcareRequest("future", 6, 9, Priority.EMERGENCY)

    def runner(num_qubits, **kwargs):
        return BB84Batch(2000, 500, 0.02, 0, True, FiniteKeyEstimate(0.02, 300), (1,) * 300)

    settings = dict(seed=1, qubit_budget=4096, batch_runner=runner,
                    generation_policy=GenerationPolicy.DEADLINE_AWARE,
                    yield_calibration=CALIBRATION)
    original = simulate_requests([immediate], **settings)
    changed = simulate_requests(
        [immediate, future], **settings, channel_schedule=(ChannelCondition(0, 0.2, 0.3),),
    )

    for result in (original, changed):
        batch = result.batches[0]
        assert batch.started_at == 2
        assert batch.observable_qber_at_decision == 0.01
        assert batch.predicted_bits == 400
        assert batch.output_bits == 300
