"""Bounded, synthetic dashboard workflows over the existing project APIs."""

import csv
import json
from dataclasses import dataclass, replace
from pathlib import Path
from secrets import randbits

from cryptography.exceptions import InvalidTag

from experiments.phase10_study import DEVELOPMENT, HELD_OUT, workload
from experiments.scheduling_study import POLICIES, Policy
from healthcare.encryption import decrypt_record, encrypt_record, key_from_bits
from healthcare.requests import HealthcareRequest, Priority
from key_management.deadline_generation import YieldObservation
from key_management.dynamic_reserve import DynamicReserveConfig
from key_management.pool import KeyPool
from qkd.pipeline import run_bb84_batch
from scheduling.fd_qks import QueuePolicy
from scheduling.simulation import ChannelCondition, GenerationPolicy, SimulationResult, simulate_requests

ROOT = Path(__file__).resolve().parents[1]
HELD_OUT_RESULTS = ROOT / "results" / "phase10" / "held-out"
DEFAULT_POLICY = "Stabilized FD-QKS v1"
MAX_QUBITS = 8192
MAX_BUDGET = 32768
WORKLOADS = {
    "Simultaneous arrivals": "simultaneous",
    "Temporary key scarcity": "temporary-scarcity",
    "Sustained overload": "overload",
    "Changing channel": "channel-shift",
    "Emergency burst": "emergency-burst",
    "Repeated outages": "repeated-outage",
    "Late emergencies": "late-emergencies",
}
LAB_POLICIES = {
    DEFAULT_POLICY: POLICIES["fd-qks"],
    "FCFS": POLICIES["fcfs"],
    "Static priority": POLICIES["static-priority"],
    "Earliest deadline first": POLICIES["edf"],
    "DDKA-inspired": POLICIES["ddka-inspired"],
    "APR-inspired": POLICIES["apr-inspired"],
    "Experimental v2 · deadline generation": Policy(generation=GenerationPolicy.DEADLINE_AWARE),
    "Research only · dynamic reserve": Policy(dynamic_reserve=DynamicReserveConfig()),
    "Research only · deadline-sensitive queue": Policy(queue=QueuePolicy.DEADLINE_SENSITIVE, ageing=None),
}
RECORDS = {
    "Synthetic triage note": {
        "id": "SIM-001", "department": "Emergency",
        "record": "Synthetic patient received a routine triage reassessment.",
    },
    "Synthetic imaging summary": {
        "id": "SIM-002", "department": "Imaging",
        "record": "Synthetic chest image reviewed. No follow-up requested in this scenario.",
    },
    "Synthetic discharge plan": {
        "id": "SIM-003", "department": "Discharge",
        "record": "Synthetic discharge plan includes a virtual follow-up in seven days.",
    },
}


def _bounded(value: int, low: int, high: int, label: str) -> None:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be a whole number between {low:,} and {high:,}.")


@dataclass(frozen=True)
class QuantumReport:
    qubits: int
    sifted: int
    sampled: int
    qber: float | None
    theoretical_qber: float
    parity_bits: int
    agreement: bool | None
    upper_bit_error_bound: float | None
    estimated_bits: int
    amplified_bits: int


def quantum_experiment(qubits: int, noise: float, interception: float, seed: int) -> QuantumReport:
    _bounded(qubits, 1, MAX_QUBITS, "Qubits")
    _bounded(seed, 0, 2**31 - 1, "Seed")
    batch = run_bb84_batch(
        qubits, seed=seed, depolarizing_probability=noise,
        interception_probability=interception, grouped=True,
    )
    # Two independent binary flips compose by their XOR probability.
    noise_error, intercept_error = noise / 2, interception / 4
    expected = noise_error + intercept_error - 2 * noise_error * intercept_error
    estimate = batch.finite_key
    return QuantumReport(
        qubits, batch.sifted_count, batch.sampled_count, batch.sampled_qber, expected,
        batch.disclosed_parity_bits, batch.agreement,
        estimate.remaining_bit_error_upper if estimate else None,
        estimate.output_length if estimate else 0, len(batch.amplified_bits),
    )


@dataclass(frozen=True)
class LiveRun:
    result: SimulationResult
    policy: str
    scenario: str
    seed: int
    budget: int
    initial_stock: int
    initial_reserve: int
    final_reserve: int


def load_calibration() -> tuple[YieldObservation, ...]:
    with (ROOT / "results/phase10/yield-calibration.csv").open(newline="", encoding="utf-8") as source:
        return tuple(YieldObservation(int(row["qubits"]), float(row["qber"]), int(row["usable_bits"]))
                     for row in csv.DictReader(source))


def simulate_workload(
    scenario: str, policy_name: str, seed: int, budget: int, *,
    noise: float, interception: float, use_workload_channel: bool, cutoff: int | None = None,
) -> LiveRun:
    if scenario not in {*DEVELOPMENT, *HELD_OUT}:
        raise ValueError("Choose a supported synthetic workload.")
    if policy_name not in LAB_POLICIES:
        raise ValueError("Choose a supported scheduling policy.")
    _bounded(seed, 0, 2**31 - 1, "Seed")
    _bounded(budget, 0, MAX_BUDGET, "Qubit budget")
    policy = LAB_POLICIES[policy_name]
    job = workload(scenario, seed)
    requests = tuple(HealthcareRequest(
        row["request_id"], row["arrival_time"], row["deadline"], Priority[row["priority"]],
        row["required_key_bits"], b"Synthetic dashboard request",
    ) for row in job["requests"])
    channel = (
        tuple(ChannelCondition(**item) for item in job["channel_schedule"])
        if use_workload_channel else (ChannelCondition(0, noise, interception),)
    )

    def grouped_runner(num_qubits: int, **kwargs):
        return run_bb84_batch(num_qubits, grouped=True, **kwargs)

    result = simulate_requests(
        requests, seed=seed, qubit_budget=budget, reserve_bits=policy.reserve,
        ageing_interval=policy.ageing, queue_policy=policy.queue, generation_policy=policy.generation,
        initial_pool_bits=job["initial_pool_bits"], dynamic_reserve=policy.dynamic_reserve,
        yield_calibration=load_calibration() if policy.generation == GenerationPolicy.DEADLINE_AWARE else (),
        channel_schedule=channel, end_time=cutoff, batch_runner=grouped_runner,
    )
    last_trace = max(result.requests, key=lambda trace: trace.outcome_at or 0, default=None)
    last_reserve = last_trace.reserve_bits if last_trace is not None else policy.reserve
    return LiveRun(result, policy_name, scenario, seed, budget, job["initial_pool_bits"],
                   policy.reserve, last_reserve)


def pool_events(run: LiveRun) -> list[dict]:
    """Order initial, completion, and post-allocation pool observations."""
    result = run.result
    events = [(0, -1, "Initial stock", run.initial_stock, run.initial_reserve)]
    events.extend((batch.completed_at, 0, "Batch completed", batch.pool_after, batch.reserve_bits)
                  for batch in result.batches if batch.completed_at is not None)
    events.extend((trace.allocation_time, trace.allocation_id + 1, "Request allocated",
                   trace.pool_after, trace.reserve_bits)
                  for trace in result.requests if trace.allocation_id is not None)
    end = max((trace.outcome_at or 0 for trace in result.requests), default=0)
    events.append((end, float("inf"), "Observation ends", result.remaining_bits, run.final_reserve))
    return [
        {"seconds": time, "event": event, "pool_bits": bits, "reserve_bits": reserve,
         "protected_bits": min(bits, reserve)}
        for time, _, event, bits, reserve in sorted(events)
    ]


@dataclass(frozen=True)
class TransferReport:
    usable_bits: int
    verified: bool
    modified_rejected: bool | None = None
    ciphertext_hex: str | None = None
    nonce_hex: str | None = None
    plaintext_json: str | None = None


def transfer_record(record_name: str, *, demonstrate_tampering: bool, noise: float = 0.0) -> TransferReport:
    if record_name not in RECORDS:
        raise ValueError("Choose an example synthetic record.")
    record = RECORDS[record_name]
    payload = json.dumps(record, indent=2).encode()
    batch = run_bb84_batch(4096, seed=randbits(32), depolarizing_probability=noise, grouped=True)
    pool = KeyPool(8192)
    usable = pool.replenish(batch.amplified_bits)
    allocated = pool.allocate(256)
    if allocated is None:
        return TransferReport(usable, verified=False)
    key = key_from_bits(allocated)
    encrypted = encrypt_record(payload, key, record["id"])
    recovered = decrypt_record(encrypted, key)
    rejected = None
    if demonstrate_tampering:
        altered = bytes([encrypted.ciphertext[0] ^ 1]) + encrypted.ciphertext[1:]
        try:
            decrypt_record(replace(encrypted, ciphertext=altered), key)
        except InvalidTag:
            rejected = True
        else:
            rejected = False
    # Keep all raw/derived key material inside this call, outside UI state.
    return TransferReport(usable, recovered == payload, rejected, encrypted.ciphertext.hex(),
                          encrypted.nonce.hex(), recovered.decode())
