# Quantum Healthcare QKD

Software simulation of quantum key distribution and key scheduling for healthcare data transmission.

## Local setup

From the project directory, create and activate a Python 3.12 virtual environment and install the recorded dependencies.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python test_setup.py
```

## Verified setup

The local run used Python 3.12.3, pip 26.3, Qiskit 2.6.2, and Qiskit Aer 0.18.4. The Aer simulator measured a single qubit after a Hadamard gate. With 1,000 shots and simulator seed 42, the test passed with 514 zeros and 486 ones. Pytest reported one passing test, and pip found no dependency conflicts.

## Reproduce the studies

Run these from the project root with the environment activated.

```sh
python -m pytest -q
python -m experiments.protocol_study --output-dir results/protocol-rerun
python -m experiments.scheduling_study --output-dir results/scheduler-rerun
```

The original implementation and the four original CSVs are preserved in the
`fd-qks-v1-baseline` tag. Each command above requires a new output directory.

To isolate queue ordering, hold the emergency reserve at 1,024 bits and
use the same fixed-size generation policy for each queue rule:

```sh
python -m experiments.scheduling_study --controlled --scenarios scarcity \
  --seeds 42 43 44 --output-dir results/scarcity-controlled
python -m experiments.scheduling_study --replay results/scarcity-controlled/manifest.json \
  --output-dir results/scarcity-replay
python -m experiments.aer_grouping --output results/aer-grouping.csv
```

The protocol study writes separate CSVs for ideal BB84 correctness, channel
disturbance and finite-key yield, and AES-GCM timing and verification. The
scheduling study defaults to five synthetic workloads, three seeds, and nine
policy configurations. `scheduling.csv` has one row per class and one `all`
row per run. Count pool and qubit columns once per run using the `all` row.
`requests.csv` and `batches.csv` hold individual outcomes and stock changes.
The manifest records exact synthetic arrivals and deadlines, policies,
replenishment settings, seeds, package versions, and source and lockfile
checksums. Queue choices can change pool stock and therefore generation
timing even with the same generation rule.

`paired_intervals.csv` reports candidate minus FD-QKS differences within
each scenario. Intervals are pointwise two-sided 95% Student t intervals on
the mean paired seed difference. Delivery differences use the seed's
delivery rate for each class and skip seeds with no offered requests in
that class. The resource metric uses started qubits. With only one pair,
the interval bounds are blank. The three default seeds are appropriate for
smoke verification and provide limited evidence for policy comparisons.

The scheduler charges qubit budget when a batch starts and deposits its
output after the simulated generation delay. Expired requests count as
deadline misses, and waiting-time statistics describe delivered requests.
The DDKA- and APR-inspired variants model demand-based generation and
application priority in a shared-pool setting.

The simulator accepts arrival times and deadlines in whole seconds, including
integer-valued floats. It rejects fractional windows before dispatch. Requests
can be delivered at their deadline. The default run ends when every request
has an outcome. An optional integer observation cutoff exposes unfinished
batches and marks requests whose deadlines have yet to pass as observation-ended.

Started qubits remain charged when a batch is cancelled because the request
queue is resolved, or when an observation cutoff leaves the batch unfinished.
Only completed batches can deposit bits. Request traces record dispatch
decisions and stock changes. Batch traces record status, seed, timing, QBER,
estimated output, and admitted stock. Traces contain no raw keys or payloads.
Grouped Aer execution uses independent shots for equivalent circuits and
maps individual shot results back to their original positions. The
benchmark compares this opt-in path against the original. The original
execution remains the default for studies and reproducing v1 results.

All healthcare payloads are synthetic. The finite-key output measures usable
key material under the simulation's engineering assumptions.

## Phase 10 research experiments

The development split uses seeds 2000–2029 across five synthetic workload
families. The held-out split uses seeds 3000–3029 and three different workload
families. Keep held-out data separate from configuration selection. Each
workload in the manifest gives all policies the same requests, timing,
synthetic initial stock, channel transitions and qubit budget. A BB84 batch
experiences the simulated channel present at launch for its full duration.

```sh
python -m experiments.grouped_yield_validation --output results/grouped-yield-rerun.csv
python -m experiments.phase10_study --split development --grouped --output-dir results/phase10-dev-rerun
```

The grouping pilot compared four paired seeds at 1,024, 4,096 and 8,192
qubits under ideal, low-noise, mixed disturbance and interception conditions.
Both modes produced identical ideal yields and zero usable bits in the tested
mixed and interception conditions. Under 2% depolarization, mean usable
output was 306.0 versus 316.5 bits at 4,096 qubits and 800.5 versus 870.25
at 8,192 qubits (original versus grouped). The pilot supports exploratory
grouped comparisons with the same execution mode for all paired policies.
Four seeds leave uncertainty about the size of any distribution differences.
The original mode remains the default for existing experiment commands.

The isolated reserve experiment uses the stabilized FD-QKS scheduler and
adaptive generation in both arms. The candidate computes
`256 × ceil(pending emergencies + recent arrivals/8 × estimated seconds + 1)`,
clamps it to 256–1,536 bits and updates before dispatch. The arrival rate
uses the last eight ticks, including the current one. Estimated seconds
come from an in-flight batch's remaining time or nominal fixed-batch
duration when idle. Protection rises immediately and releases after three
consecutive ticks below the current reserve. Only original emergency
requests can spend protected bits. The trace records the effective reserve
and protected bits consumed at allocation.

```sh
python -m experiments.phase10_study --split development --grouped \
  --comparison reserve --output-dir results/phase10-reserve-rerun
```
