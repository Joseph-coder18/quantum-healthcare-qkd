"""Verify that Qiskit Aer can transpile, simulate, and measure a qubit."""

from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator


def test_aer_superposition() -> None:
    circuit = QuantumCircuit(1, 1)
    circuit.h(0)
    circuit.measure(0, 0)

    simulator = AerSimulator()
    compiled = transpile(circuit, simulator)
    shots = 1000
    result = simulator.run(compiled, shots=shots, seed_simulator=42).result()
    counts = result.get_counts()

    print(circuit.draw(output="text"))
    print(counts)

    assert result.success, result.status
    assert set(counts) == {"0", "1"}, counts
    assert sum(counts.values()) == shots, counts
    assert all(400 <= count <= 600 for count in counts.values()), counts


if __name__ == "__main__":
    test_aer_superposition()
