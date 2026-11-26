from key_management.pool import KeyPool
from key_management.replenishment import AdaptiveReplenishment, ReplenishmentConfig


def controller():
    return AdaptiveReplenishment(ReplenishmentConfig(
        low_watermark=256, high_watermark=512, min_qubits=256,
        max_qubits=2048, qubit_increment=256, initial_yield=0.5,
    ))


def test_watermark_hysteresis_and_observed_yield():
    pool = KeyPool(1024)
    pool.replenish((0,) * 256)
    adaptive = controller()

    assert adaptive.choose_batch(pool) == 512
    adaptive.observe_batch(512, 0)
    assert adaptive.choose_batch(pool) == 1024
    pool.replenish((0,) * 128)
    assert adaptive.choose_batch(pool) == 512
    pool.replenish((0,) * 128)
    assert adaptive.choose_batch(pool) == 0


def test_pending_demand_accounts_for_emergencies_before_ordinary_requests():
    pool = KeyPool(1024, emergency_reserve_bits=256)
    pool.replenish((0,) * 512)
    adaptive = controller()

    assert adaptive.choose_batch(pool, ordinary_demand=256) == 0
    assert adaptive.choose_batch(pool, ordinary_demand=256, emergency_demand=256) == 512


def test_zero_estimated_yield_uses_the_bounded_batch_size():
    adaptive = AdaptiveReplenishment(ReplenishmentConfig(smoothing=1))
    adaptive.observe_batch(8192, 0)

    assert adaptive.choose_batch(KeyPool(8192)) == 8192


def test_pending_ordinary_demand_includes_an_underfilled_reserve():
    pool = KeyPool(1024, emergency_reserve_bits=768)
    pool.replenish((0,) * 512)

    assert controller().choose_batch(pool, ordinary_demand=256) == 1024
