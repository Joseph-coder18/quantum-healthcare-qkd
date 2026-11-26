import pytest

from key_management.pool import KeyPool


def test_ordinary_allocation_preserves_the_reserve_for_critical_requests():
    pool = KeyPool(capacity_bits=6, emergency_reserve_bits=2)
    assert pool.replenish((1, 0, 1, 0, 0, 1, 1)) == 6

    assert pool.allocate(5) is None
    assert pool.available_bits == 6
    assert pool.allocate(4) == (1, 0, 1, 0)
    assert pool.allocate(1) is None
    assert pool.allocate(2, critical=True) == (0, 1)
    assert pool.available_bits == 0


def test_invalid_replenishment_leaves_the_pool_intact():
    pool = KeyPool(capacity_bits=3)
    pool.replenish((1,))

    with pytest.raises(ValueError, match="integer bits"):
        pool.replenish((0, 2))

    assert pool.available_bits == 1
    assert pool.allocate(1) == (1,)
