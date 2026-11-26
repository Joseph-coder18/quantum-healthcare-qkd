# Final FD-QKS Engineering Baseline

The final project uses **stabilized FD-QKS v1**. The `final-project` branch starts from
Phase 10 commit `19d3bda`, which already contains original v1
(`539a909`, tag `fd-qks-v1-baseline`) and stabilized v1 (`f91ee74`).
The `main` and `fd-qks-v2` research branches remain available at their
pre-integration commits.

| Layer | Selected behavior |
|---|---|
| Quantum simulation | Uniform BB84 bit and basis draws, Aer measurement, matching-basis sifting. Depolarization and averaged random-basis intercept-resend are optional simulated disturbances. |
| Post-processing | Disclose a random sample of 25% of sifted positions by default, rounded up while leaving an undisclosed bit. Use shuffled parity passes of 8, 16, 32 and 64 bits, exact simulator-side agreement and binary Toeplitz hashing. |
| Estimated yield | Invert the hypergeometric lower tail at 0.01 to bound the undisclosed pre-reconciliation bit-error rate. Use it as a phase-error proxy, subtract the disclosed parity bits and illustrative 128-bit penalty, and clamp the estimated length to zero. |
| Key pool | 8,192 bits, FIFO allocation, 1,024-bit fixed emergency reserve, 256 bits per delivered request. A workload may specify synthetic initial stock. |
| Scheduler | Emergency precedence. Ordinary requests gain one priority level per 10 seconds waited up to urgent. Then sort by earliest deadline, arrival and identifier. Whole-second dispatch includes the exact deadline. |
| Replenishment | One generation batch in flight, 2,048/6,144-bit watermarks and reserve-aware pending demand. Yield starts at 0.12 usable bits per qubit and uses an exponential moving average with latest-batch weight 0.5. Default batches are requested in 1,024-qubit increments from 1,024 through 8,192, subject to the remaining budget, at 4,096 qubits per simulated second. |
| Transfer | Allocate 256 bits, use a 12-byte random nonce for AES-256-GCM, authenticate the request identifier as associated data and verify an in-process decrypt. |

Only completed batches that pass the simulator's agreement and yield checks
can deposit bits. Started qubits remain charged on cancellation or an
observation cutoff. Ordinary allocations must leave the reserve intact.

## Experimental alternatives

Deadline-aware generation remains an explicitly labeled research option.
It improved pooled held-out delivery and reduced qubit use, with three more
emergency misses than stabilized v1 and a higher served waiting-time p90.
The dynamic reserve sacrificed emergency delivery. The deadline-sensitive
queue redirected service across classes and exceeded the development
interaction's urgent-delivery loss tolerance. See the
[Phase 10 audit](Phase10_Technical_Audit.md) and
[frozen selection](../results/phase10/held-out-selection.json).

## Security and interpretation

The finite-sample calculation estimates usable bits for a software model.
It uses a classical error-rate proxy and a reproducible simulation RNG.
The classical QKD exchange and separate endpoint authentication are absent.
The demonstration uses synthetic records and local encryption and decryption.
It establishes neither a composable QKD proof nor production healthcare readiness.
