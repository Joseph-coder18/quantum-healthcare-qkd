"""Quantum circuit construction for the BB84 protocol."""

from collections.abc import Sequence
from dataclasses import dataclass
from random import Random

from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
from qiskit_aer.noise import depolarizing_error, pauli_error


@dataclass(frozen=True)
class BB84Round:
    alice_bits: tuple[int, ...]
    bob_bits: tuple[int, ...]
    alice_bases: tuple[str, ...]
    bob_bases: tuple[str, ...]
    matched_positions: tuple[int, ...]

    @property
    def alice_sifted_bits(self) -> tuple[int, ...]:
        return tuple(self.alice_bits[index] for index in self.matched_positions)

    @property
    def bob_sifted_bits(self) -> tuple[int, ...]:
        return tuple(self.bob_bits[index] for index in self.matched_positions)


@dataclass(frozen=True)
class QBEREstimate:
    disclosed_positions: tuple[int, ...]
    error_count: int
    alice_remaining_bits: tuple[int, ...]
    bob_remaining_bits: tuple[int, ...]

    @property
    def qber(self) -> float:
        return self.error_count / len(self.disclosed_positions)


def estimate_qber(
    round_result: BB84Round, sample_size: int, *, seed: int | None = None
) -> QBEREstimate:
    """Compare a random sample of sifted bits and exclude it from both remaining keys."""
    matched = round_result.matched_positions
    if type(sample_size) is not int or not 1 <= sample_size <= len(matched):
        raise ValueError("sample_size must be between 1 and the number of sifted bits")

    disclosed = tuple(sorted(Random(seed).sample(matched, sample_size)))
    disclosed_set = set(disclosed)
    remaining = tuple(index for index in matched if index not in disclosed_set)
    alice_bits = round_result.alice_bits
    bob_bits = round_result.bob_bits

    return QBEREstimate(
        disclosed_positions=disclosed,
        error_count=sum(alice_bits[index] != bob_bits[index] for index in disclosed),
        alice_remaining_bits=tuple(alice_bits[index] for index in remaining),
        bob_remaining_bits=tuple(bob_bits[index] for index in remaining),
    )


def prepare_bb84_state(bit: int, basis: str) -> QuantumCircuit:
    """Encode a binary bit in the Z or X basis of an unmeasured qubit."""
    if type(bit) is not int or bit not in (0, 1):
        raise ValueError("bit must be the integer 0 or 1")
    if basis not in ("Z", "X"):
        raise ValueError("basis must be 'Z' or 'X'")

    circuit = QuantumCircuit(1)
    if bit == 1:
        circuit.x(0)
    if basis == "X":
        circuit.h(0)
    return circuit


def measure_bb84_state(state: QuantumCircuit, basis: str) -> QuantumCircuit:
    """Return a copy of a prepared BB84 circuit with Bob's measurement added."""
    if basis not in ("Z", "X"):
        raise ValueError("basis must be 'Z' or 'X'")
    if state.num_qubits != 1 or state.num_clbits != 0:
        raise ValueError("state must be a one-qubit circuit with no classical bits")

    circuit = state.copy()
    if basis == "X":
        circuit.h(0)
    circuit.measure_all()
    return circuit


def sift_positions(
    alice_bases: Sequence[str], bob_bases: Sequence[str]
) -> tuple[int, ...]:
    """Return the zero-based positions retained after public basis comparison."""
    if len(alice_bases) != len(bob_bases):
        raise ValueError("Alice and Bob must have the same number of bases")

    matches = []
    for index, (alice_basis, bob_basis) in enumerate(zip(alice_bases, bob_bases)):
        if alice_basis not in ("Z", "X") or bob_basis not in ("Z", "X"):
            raise ValueError("bases must be 'Z' or 'X'")
        if alice_basis == bob_basis:
            matches.append(index)
    return tuple(matches)


def simulate_bb84_round(
    num_qubits: int,
    *,
    seed: int | None = None,
    depolarizing_probability: float = 0.0,
    interception_probability: float = 0.0,
) -> BB84Round:
    """Simulate and sift BB84 bits with optional depolarization and intercept-resend.

    Both effects act before Bob measures. In isolation, depolarization gives
    expected matched-basis QBER of p / 2 and intercept-resend gives p / 4.
    """
    if type(num_qubits) is not int or num_qubits <= 0:
        raise ValueError("num_qubits must be a positive integer")
    if not 0.0 <= depolarizing_probability <= 1.0:
        raise ValueError("depolarizing_probability must be between 0 and 1")
    if not 0.0 <= interception_probability <= 1.0:
        raise ValueError("interception_probability must be between 0 and 1")

    random = Random(seed)
    alice_bits = tuple(random.randrange(2) for _ in range(num_qubits))
    alice_bases = tuple(random.choice(("Z", "X")) for _ in range(num_qubits))
    bob_bases = tuple(random.choice(("Z", "X")) for _ in range(num_qubits))
    channel = (
        depolarizing_error(depolarizing_probability, 1).to_instruction()
        if depolarizing_probability > 0
        else None
    )
    intercept_resend = None
    if interception_probability > 0:
        # Averaging over the unobserved X/Z measurement outcomes gives a
        # mixture of X and Z dephasing. Each basis is selected half the time.
        flip_weight = interception_probability / 4
        intercept_resend = pauli_error(
            [("I", 1 - 2 * flip_weight), ("X", flip_weight), ("Z", flip_weight)]
        ).to_instruction()
    circuits = []
    for bit, alice_basis, bob_basis in zip(alice_bits, alice_bases, bob_bases):
        state = prepare_bb84_state(bit, alice_basis)
        if intercept_resend is not None:
            state.append(intercept_resend, [0])
        if channel is not None:
            state.append(channel, [0])
        circuits.append(measure_bb84_state(state, bob_basis))

    simulator = AerSimulator()
    compiled = transpile(circuits, simulator, num_processes=1)
    result = simulator.run(
        compiled, shots=1, seed_simulator=random.randrange(2**32)
    ).result()
    if not result.success:
        raise RuntimeError(f"BB84 simulation failed: {result.status}")
    bob_bits = tuple(
        int(next(iter(result.get_counts(index)))) for index in range(num_qubits)
    )

    return BB84Round(
        alice_bits, bob_bits, alice_bases, bob_bases, sift_positions(alice_bases, bob_bases)
    )
