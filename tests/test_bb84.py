from math import sqrt

import pytest
from qiskit import transpile
from qiskit.quantum_info import Statevector
from qiskit_aer import AerSimulator

from qkd.bb84 import (
    BB84Round,
    estimate_qber,
    measure_bb84_state,
    prepare_bb84_state,
    sift_positions,
    simulate_bb84_round,
)


@pytest.mark.parametrize(
    ("bit", "basis", "expected"),
    [
        (0, "Z", [1, 0]),
        (1, "Z", [0, 1]),
        (0, "X", [1 / sqrt(2), 1 / sqrt(2)]),
        (1, "X", [1 / sqrt(2), -1 / sqrt(2)]),
    ],
    ids=["zero", "one", "plus", "minus"],
)
def test_prepare_bb84_state(bit, basis, expected):
    circuit = prepare_bb84_state(bit, basis)

    assert circuit.num_qubits == 1
    assert circuit.num_clbits == 0
    assert Statevector.from_instruction(circuit).equiv(Statevector(expected))


@pytest.mark.parametrize(("bit", "basis"), [(-1, "Z"), (2, "X"), (0, "Y")])
def test_prepare_bb84_state_rejects_invalid_input(bit, basis):
    with pytest.raises(ValueError):
        prepare_bb84_state(bit, basis)


@pytest.mark.parametrize("bit", [0, 1])
@pytest.mark.parametrize("alice_basis", ["Z", "X"])
@pytest.mark.parametrize("bob_basis", ["Z", "X"])
def test_measure_bb84_state(bit, alice_basis, bob_basis):
    state = prepare_bb84_state(bit, alice_basis)
    measured = measure_bb84_state(state, bob_basis)
    assert state.num_clbits == 0

    simulator = AerSimulator()
    shots = 1000
    compiled = transpile(measured, simulator)
    counts = simulator.run(compiled, shots=shots, seed_simulator=42).result().get_counts()

    if alice_basis == bob_basis:
        assert counts == {str(bit): shots}
    else:
        assert set(counts) == {"0", "1"}
        assert sum(counts.values()) == shots
        assert 400 <= counts["0"] <= 600


def test_measure_bb84_state_rejects_invalid_basis():
    state = prepare_bb84_state(0, "Z")
    with pytest.raises(ValueError, match="basis"):
        measure_bb84_state(state, "Y")


@pytest.mark.parametrize(
    ("alice_bases", "bob_bases", "expected"),
    [
        ("ZXZXXZZZ", "ZZXXZXXZ", (0, 3, 7)),
        ("ZX", "XZ", ()),
        ("", "", ()),
    ],
)
def test_sift_positions(alice_bases, bob_bases, expected):
    assert sift_positions(alice_bases, bob_bases) == expected


@pytest.mark.parametrize(("alice_bases", "bob_bases"), [("Z", ""), ("Z", "Y")])
def test_sift_positions_rejects_invalid_bases(alice_bases, bob_bases):
    with pytest.raises(ValueError):
        sift_positions(alice_bases, bob_bases)


@pytest.mark.parametrize("num_qubits", [1, 128])
def test_simulate_bb84_round(num_qubits):
    round_result = simulate_bb84_round(num_qubits, seed=42)

    assert len(round_result.alice_bits) == len(round_result.bob_bits) == num_qubits
    expected_positions = tuple(
        index
        for index in range(num_qubits)
        if round_result.alice_bases[index] == round_result.bob_bases[index]
    )
    assert round_result.matched_positions == expected_positions
    assert round_result.alice_sifted_bits == round_result.bob_sifted_bits
    assert round_result == simulate_bb84_round(num_qubits, seed=42)


def test_fully_depolarized_channel_randomizes_matched_basis_bits():
    round_result = simulate_bb84_round(1024, seed=42, depolarizing_probability=1.0)
    estimate = estimate_qber(round_result, 400, seed=43)

    assert 0.4 <= estimate.qber <= 0.6


@pytest.mark.parametrize("probability", [-0.01, 1.01, float("nan")])
def test_simulate_bb84_round_rejects_invalid_noise(probability):
    with pytest.raises(ValueError, match="depolarizing_probability"):
        simulate_bb84_round(1, depolarizing_probability=probability)


def test_full_intercept_resend_produces_expected_qber():
    round_result = simulate_bb84_round(2048, seed=42, interception_probability=1.0)
    estimate = estimate_qber(round_result, 750, seed=43)

    assert estimate.qber == pytest.approx(0.25, abs=0.05)


def test_simulate_bb84_round_rejects_invalid_interception():
    with pytest.raises(ValueError, match="interception_probability"):
        simulate_bb84_round(1, interception_probability=1.01)


def test_estimate_qber_excludes_disclosed_and_unsifted_bits():
    round_result = BB84Round(
        alice_bits=(0, 1, 0, 1),
        bob_bits=(1, 0, 0, 1),
        alice_bases=("Z", "Z", "X", "X"),
        bob_bases=("Z", "X", "X", "X"),
        matched_positions=(0, 2, 3),
    )

    estimate = estimate_qber(round_result, 2, seed=42)

    assert estimate.disclosed_positions == (0, 3)
    assert estimate.error_count == 1
    assert estimate.qber == 0.5
    assert estimate.alice_remaining_bits == estimate.bob_remaining_bits == (0,)


def test_estimate_qber_handles_an_ideal_round():
    round_result = simulate_bb84_round(128, seed=42)
    sample_size = 16

    estimate = estimate_qber(round_result, sample_size, seed=42)

    assert len(estimate.disclosed_positions) == sample_size
    assert estimate.qber == 0
    assert len(estimate.alice_remaining_bits) == len(round_result.matched_positions) - sample_size
    assert estimate.alice_remaining_bits == estimate.bob_remaining_bits


@pytest.mark.parametrize("sample_size", [0, 1, 2])
def test_estimate_qber_rejects_sampling_when_no_bits_were_sifted(sample_size):
    round_result = BB84Round((0,), (1,), ("Z",), ("X",), ())

    with pytest.raises(ValueError, match="sample_size"):
        estimate_qber(round_result, sample_size)
