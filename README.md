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
