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
python -m experiments.protocol_study
python -m experiments.scheduling_study
```

The protocol study writes separate CSVs for ideal BB84 correctness, channel
disturbance and finite-key yield, and AES-GCM timing and verification. The
scheduling study writes comparisons for five synthetic workloads, three
seeds, and nine policy configurations. Its CSV includes one row for all
requests and one row per priority class in each run. Qubit and pool columns
describe the whole run and should be counted once using the `all` row.

The scheduler charges qubit budget when a batch starts and deposits its
output after the simulated generation delay. Expired requests count as
deadline misses, and waiting-time statistics describe delivered requests.
The DDKA- and APR-inspired variants model demand-based generation and
application priority in a shared-pool setting.

All healthcare payloads are synthetic. The finite-key output measures usable
key material under the simulation's engineering assumptions.
