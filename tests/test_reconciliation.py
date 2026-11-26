from qkd.reconciliation import ReconciliationResult, reconcile_bits


def test_reconciliation_corrects_one_error_and_counts_both_directions():
    alice = (0, 0, 0, 0)
    bob = (0, 1, 0, 0)

    result = reconcile_bits(alice, bob, block_sizes=(4,), seed=42)

    assert result == ReconciliationResult(alice, 1, 6)


def test_even_error_block_can_leave_residual_errors():
    alice = (0, 0, 0, 0)
    bob = (1, 1, 0, 0)

    result = reconcile_bits(alice, bob, block_sizes=(4,), seed=42)

    assert result == ReconciliationResult(bob, 0, 2)


def test_reconciliation_handles_empty_sequences():
    assert reconcile_bits((), ()) == ReconciliationResult((), 0, 0)
