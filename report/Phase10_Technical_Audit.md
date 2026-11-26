# FD-QKS Phase 10 Technical Audit

**Branch:** `fd-qks-v2`
**Scope:** Algorithm development and held-out evaluation for the quantum healthcare simulation. The separate academic report and Streamlit dashboard are outside Phase 10.

## Reproducible history

The original v1 implementation and its four original result CSVs are preserved at `539a909` (`fd-qks-v1-baseline`), and stabilized v1 remains at `f91ee74` on `main`. The analysis uses synthetic requests and local Aer simulation.

| Commit | Contribution |
|---|---|
| `3d73161` | Grouped Aer pipeline validation and preassigned workload families |
| `f96d934` | Thirty-seed stabilized-v1 development baseline |
| `269d464` | Dynamic reserve and causal request accounting |
| `d9ab025` | Isolated reserve results |
| `8be98c0` | Deadline generation, deadline-sensitive queue and calibration data |
| `7fff1f2` | Isolated results, legacy comparison and independent ledger verifier |

On the three original scarcity seeds (42–44), the original-mode stabilized replay matched every shared field in the saved `539a909` FD-QKS rows. Both delivered 69/108 overall and 7/7 emergencies. The original simulator's interface did not support changing channels or nonempty initial stock. Its direct comparison is limited to a workload both versions support. The stabilized v1 policy is the matched reference for the new workload families. See [legacy bridge](../results/phase10/legacy-scarcity-bridge/manifest.json) and [original scheduling results](../results/scheduling.csv).

## Design and methodology

- **Development:** Seeds 2000–2029, each paired across every policy on five families. The families include simultaneous contention, temporary key scarcity, sustained overload, changing conditions with interception, and emergency bursts.
- **Held out:** Seeds 3000–3029 on three separate families with staggered conflicts, repeated channel deterioration and late emergency bursts. Configuration choices use development evidence only.
- **Calibration:** Seeds 1000–1011, independent of workload seeds. The calibration contains 336 target batches from four sizes and seven channel regimes, each conditioned on a separate 4,096-qubit probe's measured QBER. The grouped Aer comparison has its own separate seeds.
- **Fair pairing:** Policies share exact requests, initial synthetic stock, channel transitions, generation rate and qubit cap for each workload seed. The channel at batch launch is held for the batch's duration. Case selection can change when qubits are submitted, so a pair can encounter different channel conditions even with the same schedule. Batch randomness is shared when the batch position, size and channel coincide.
- **Statistics:** Pointwise two-sided 95% Student t intervals on paired seed differences. Across-scenario intervals first pool the relevant observations within each seed, then average the 30 seed-level contrasts. Pooled counts and the mean paired percentages can differ, especially where class sizes vary by seed. The intervals do not adjust for multiple comparisons. Served-only waiting percentiles must be read with miss counts. Administrative and routine deadline expiry is used as a starvation indicator and can also reflect absolute resource shortage.
- **Safety model:** The accepted yield is a finite-sample engineering estimate. It uses a pre-reconciliation bit-error bound as a phase-error proxy. These experiments do not establish composable secrecy or production-grade healthcare security. Disturbance is a simulator input; it does not infer an adversary's presence or knowledge. AES-GCM is an in-process synthetic round trip.

Each study folder contains a manifest with exact workloads and policies, the summary CSV, per-request and per-batch traces, and paired intervals. Trace metrics add waiting percentiles, low-priority expiry, reserve use, final unused stock, started and completed qubits, and per-delivery quantum cost. The verifier independently checks request identity, deadlines, reserve compliance, non-overlapping FIFO allocation IDs, qubit budgets, rejection and conservation.

## Candidate algorithms

### Dynamic reserve

Set the target to `clip(256 × ceil(pending emergency requests + recent emergency arrival rate × replenishment time + 1), 256, 1536)`. The recent rate is the count over eight ticks divided by eight. Replenishment time uses the remaining time of an in-flight batch or a nominal fixed-batch duration when idle. The reserve rises immediately and releases after three consecutive ticks below current protection. Only the original emergency class can spend protected bits. The security acceptance rules are unchanged.

### Deadline-aware generation

Use the last completed batch's sampled QBER as a quality signal, with a 1% prior at cold start. Bin cutoffs are 0.5%, 1.5%, 3% and 5%; the nearest populated bin is used if the current one is absent, with ties toward higher QBER. Calibrated means and empirical one-key probabilities are indexed by batch size and quality bin. At a dispatch tick, size candidates must fit the remaining qubit budget and be able to finish before at least one arrived pending deadline. Rank by anticipated additional emergency deliveries, additional total deliveries, earlier completion and then lower qubit cost.

Regular candidates must predict 256 usable bits on average and at least a 50% empirical probability of one key. When previous observations indicate poor yield, a feasible large recovery probe can refresh the signal after a six-second spacing from the preceding launch. The controller receives arrived requests, current pool state, rate and budget. It cannot read the future channel schedule or the true interception parameter. The trace records predicted usable output, sampled QBER, finite-key estimated output and actual usable output as separate fields. Prediction uses a proxy that can lag after a channel transition.

### Deadline-sensitive queue

Emergency precedence remains absolute. Ordinary requests score by `original class + 2 × elapsed deadline fraction + 0.25 × min(1, wait/20)`. An exact zero-slack request is fully elapsed and eligible at its deadline. Deadline, arrival and request identifier break ties. Original emergency classification governs reserve access regardless of ordinary score.

## Development evidence

The 30-seed stabilized baseline has 1,350 runs across five workload families and nine policies. Stabilized FD-QKS delivered 2,393/3,600 overall and 515/515 emergencies. The isolated comparisons below each keep the other rules fixed.

| Candidate | Pooled development outcome | Paired 95% evidence |
|---|---|---|
| Dynamic reserve vs fixed reserve | 2,690 vs 2,393 overall; 500 vs 515 emergency deliveries | Overall +8.25 pp [7.78, 8.72]; emergency −2.61 pp [−4.16, −1.06] |
| Deadline generation vs adaptive | 2,389 vs 2,393 overall; 515/515 emergencies in both arms; 4,317,184 vs 4,669,440 started qubits | Overall −0.11 pp [−1.19, 0.97]; started qubits per delivery −143.1 [−171.7, −114.5]; low-priority expiry +4.07 pp [1.87, 6.26] |
| Deadline-sensitive queue vs original ageing, with the same fixed generation and reserve | 2,393/3,600 overall and 515/515 emergencies in both arms | Administrative delivery +1.89 pp [0.78, 2.99]; urgent delivery −1.02 pp [−1.73, −0.31]; overall +0.00 pp [0.00, 0.00] |

The fixed and adaptive arms in the isolated generation study had identical pooled outcomes and qubit use. EDF under the controlled queue comparison delivered 2,406/3,600 and all 515 emergencies, versus 2,393 and all 515 for original ageing. The queue candidate improved one part of the class distribution, with an accompanying urgent-service loss. The dynamic reserve candidate used unchanged qubit budget in aggregate and improved overall delivery, with lower emergency availability. It was excluded from the development interaction candidate.

[Baseline metrics](../results/phase10/stabilized-baseline/metrics.csv) · [Reserve intervals](../results/phase10/reserve-development/paired_trace_intervals.csv) · [Generation intervals](../results/phase10/generation-development/paired_trace_intervals.csv) · [Queue intervals](../results/phase10/queue-development/paired_trace_intervals.csv)

## Grouped Aer execution

Each equivalent circuit shares a compiled template, with separately sampled shots mapped back to the original transmission positions. Existing commands default to the original engine. The Phase 10 comparisons opt in to grouping for every arm. The pilot used four paired seeds at 1,024, 4,096 and 8,192 qubits under ideal, low-noise, mixed disturbance and interception conditions. Both modes produced identical ideal post-processing output and zero usable bits in the particular mixed and intercept conditions. At 2% depolarization, the means were 306.0 versus 316.5 usable bits at 4,096 qubits and 800.5 versus 870.25 bits at 8,192 (original versus grouped). Interception still produced approximately the expected sampled disturbance. The pilot compares distributions and actual output; stochastic trajectories can differ between modes.

[Grouped validation data](../results/phase10/grouped-yield-validation.csv) · [Calibration observations](../results/phase10/yield-calibration.csv)

A follow-up added 12 paired seeds (105–116) at 2% depolarization. Across 16 paired seeds, grouped minus original mean usable yield was **+4.7 bits** at 4,096 qubits (95% CI **−27.6 to +37.0**) and **+20.8 bits** at 8,192 (95% CI **−26.6 to +68.2**). Both yielded zero at 1,024. Differences in mean QBER were +0.20 percentage points [−0.34, 0.74], −0.13 [−0.39, 0.13] and −0.10 [−0.27, 0.07], respectively. Median observed runtimes were 0.87/0.21, 3.17/0.22 and 6.28/0.24 seconds (original/grouped); concurrent development jobs mean timing ratios are descriptive. No equivalence margin was tested. Both paths remain available for independent verification. [Additional low-noise validation](../results/phase10/grouped-low-noise-extension.csv)

## Combined development trial and frozen choice

The combined development trial contained 2,250 runs (54,000 request and 9,161 batch traces). The exploratory queue-plus-generation combination delivered **2,403/3,600** and **515/515** emergencies. It started 4,335,616 qubits. Relative to stabilized v1, its mean paired overall delivery difference was **+0.28 pp [−0.82, +1.37]** and started qubits per delivery fell **145.9 [117.7, 174.2]**. Relative to deadline generation alone, the queue lowered low-priority expiry **1.54 pp [0.62, 2.46]** and lowered urgent delivery **1.35 pp [0.51, 2.19]**.

The selection rule was committed as `0ca33a7` before the interaction results were read. Generation passed the emergency, resource and overall delivery criteria. The additional queue exceeded the one-point urgent-delivery loss tolerance. The freeze commit `68e2ca7` therefore advanced **deadline generation with stabilized FD-QKS ageing and the fixed 1,024-bit reserve**. The dynamic reserve was excluded because it lost emergency deliveries. The held-out run includes the three isolated candidates, the selected configuration, and its removal ablation. Because only one component survived selection, its isolated policy matches the selected version, and removing it matches stabilized v1. Neither duplicate is independent evidence.

[Selection rule](../results/phase10/selection-rule.txt) · [Frozen selection](../results/phase10/held-out-selection.json) · [Interaction data](../results/phase10/combined-development/metrics.csv) · [Intervals versus generation alone](../results/phase10/combined-development/paired_vs_deadline-generation.csv)

## Held-out outcomes

The frozen study completed **1,260 runs**, covering 30 paired seeds, three new workload families and 14 labels. The independent verifier checked **28,560 request traces and 5,276 batch traces**. A separate replay of seed 3000 across all three families reproduced all **210 summary, 952 request and 181 batch rows** exactly. The manifest matched the committed selection and all six hashed development evidence files. **All 85 automated tests passed.**

| Policy | Delivered / 2,040 | Emergency delivered / 387 | Started qubits¹ | Started qubits per delivery |
|---|---:|---:|---:|---:|
| Stabilized FD-QKS v1 | 1,232 | 311 | 2,949,120 | 2,394 |
| Selected v2 / isolated deadline generation | 1,297 | 308 | 2,668,544 | 2,057 |
| FCFS | 1,327 | 188 | 2,949,120 | 2,222 |
| Static priority | 1,327 | 211 | 2,949,120 | 2,222 |
| EDF | 1,327 | 210 | 2,949,120 | 2,222 |
| DDKA-inspired | 1,170 | 119 | 2,511,872 | 2,147 |
| APR-inspired | 1,231 | 311 | 2,949,120 | 2,396 |
| Isolated dynamic reserve | 1,308 | 262 | 2,949,120 | 2,255 |
| Isolated deadline-sensitive queue | 1,232 | 311 | 2,949,120 | 2,394 |
| Selected v2 without deadline generation | 1,232 | 311 | 2,949,120 | 2,394 |
| v1 without ageing | 1,232 | 311 | 2,949,120 | 2,394 |
| v1 without reserve | 1,327 | 211 | 2,949,120 | 2,222 |
| v1 without adaptive generation | 1,232 | 311 | 2,949,120 | 2,394 |

¹ Started and completed qubit counts matched for every arm in this run. Reserve and generation can differ across the full policy table. The isolated development studies are the controlled tests of individual mechanisms.

| Class | Offered | Stabilized v1 misses | Selected v2 misses | v1 → v2 served wait p50/p90 |
|---|---:|---:|---:|---|
| Emergency | 387 | 76 | 79 | 0/0 → 0/0 s |
| Urgent | 612 | 236 | 178 | 0/3 → 2/6 s |
| Routine | 643 | 289 | 267 | 0/2 → 2/5 s |
| Administrative | 398 | 207 | 219 | 0/2 → 2/6 s |
| All | 2,040 | 808 | 743 | 0/2 → 2/4.4 s |

Administrative and routine expiry combined fell from **47.65% to 46.69%** (mean paired difference **−0.97 pp [−3.53, +1.60]**). Final unused stock fell from **102,789 to 75,389 bits**. Emergency draws of protected stock increased from **37,486 to 39,920 bits**. Protected bits used measures the fall in protected stock at each emergency allocation; it is summed across runs and includes repeated reserve refills.

The selected candidate gained **3.19 pp overall delivery [1.63, 4.75]** and saved **333 started qubits per delivery [277, 389]**, using per-seed paired means. Emergency delivery changed by **−0.83 pp [−2.54, +0.89]**. The interval includes both loss and gain, and it does not establish emergency non-inferiority. The pooled result was three additional emergency misses. Served wait p90 increased by a paired mean of **2.60 s [2.13, 3.07]**. Urgent delivery increased **9.36 pp [6.58, 12.14]**, routine delivery increased **3.88 pp [0.50, 7.26]**, and administrative delivery changed by **−3.58 pp [−7.69, +0.54]**.

| Held-out family | v1 overall | v2 overall | Paired overall difference [95% CI] | v1 → v2 emergency delivery |
|---|---:|---:|---|---|
| Staggered contention | 538/540 | 505/540 | −6.11 pp [−7.95, −4.28] | 90/90 → 90/90 |
| Repeated outage | 178/660 | 354/660 | +26.67 pp [22.92, 30.42] | 54/54 → 54/54 |
| Late emergencies | 516/840 | 438/840 | −9.29 pp [−11.49, −7.08] | 167/243 → 164/243 |

The pooled benefit was driven by the repeated-outage family. Its large recovery probes yielded at least one key in 55 of 57 cases. In the late-emergency family, only 2 of 12 such probes yielded one key. This is consistent with recovery being useful when the channel improves and costly when deterioration persists. Prediction errors are available in the batch trace, alongside observed QBER, finite-key predicted length and actual usable output. These probe outcomes do not isolate the causal contribution of probes from the rest of the generation policy.

[Held-out manifest](../results/phase10/held-out/manifest.json) · [Metrics by policy, class and family](../results/phase10/held-out/metrics.csv) · [Paired intervals versus v1](../results/phase10/held-out/paired_trace_intervals.csv) · [Paired intervals versus selected v2](../results/phase10/held-out/paired_vs_combined-v2.csv)

## Recommendation and limits

**Keep stabilized v1 as the default FD-QKS configuration.** The held-out candidate failed the frozen no-observed-emergency-loss rule, lengthened waits for served requests, and had opposite delivery effects across workload families. Preserve deadline-aware generation as an experimental energy and recovery policy. Use independent future workloads to test a guarded hybrid with proactive reserve refill and a recovery trigger driven by recent observable samples. Define the emergency non-inferiority margin and absolute deadline/wait tolerances before collecting that evidence. The current held-out set should remain a record of this evaluation.

The dynamic reserve and deadline-sensitive queue both remain research candidates. The reserve's throughput benefit accompanied an emergency penalty in both splits. The queue changed class allocation, and its development interaction carried an urgent-service loss above the allowed tolerance. Equal aggregate outcomes in several arms are a property of these workloads and parameters. None establishes policy equivalence.

The synthetic family mix, one-second dispatch, 30 independent seeds, shared pool, phase-error proxy and lack of independent deployment evidence limit generalization. The model's strongest grounded claims concern the observed simulation trade-offs. It does not establish production security or universal v2 superiority.
