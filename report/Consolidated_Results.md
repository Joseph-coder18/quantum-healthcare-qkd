# Consolidated Quantum Healthcare QKD Results

**Selected configuration** — stabilized FD-QKS v1, with the fixed 1,024-bit
emergency reserve and adaptive batch generation. The
[engineering baseline](Final_Engineering_Baseline.md) defines the exact
parameters. Deadline-aware generation, dynamic reserve and deadline-sensitive
ordering remain research policies.

## Reproduction and source inventory

From the repository root, with the pinned environment activated:

```sh
python -m experiments.final_figures
python -m experiments.final_figures --output-dir /tmp/qkd-figures-reproduction
diff -rq report/consolidated /tmp/qkd-figures-reproduction
```

The generator writes 220-DPI PNGs, scalable SVGs and derived CSV tables under
[report/consolidated](consolidated). The source experiment directories are read only.

| Figure | Source experiment and scope |
|---|---|
| [01 BB84 correctness and circuit](consolidated/figures/01_bb84_correctness_and_circuit.svg) | [Ideal BB84 CSV](../results/bb84_correctness.csv), three 4,096-qubit runs, seeds 42–44. The circuit is drawn directly from the repository's Alice and Bob functions. It depicts bit 1, X preparation and X measurement. |
| [02 Disturbance and QBER](consolidated/figures/02_channel_disturbance_and_qber.svg) | [Protocol sweep CSV](../results/bb84_channel_and_yield.csv), 39 labelled condition rows across three seeds. Dots show seed values and solid lines show means. Dashed lines show isolated expectations of interception/4 and depolarization/2. Reused settings across sweeps are the same batches. |
| [03 Noise and finite-sample yield](consolidated/figures/03_noise_and_finite_sample_yield.svg) | Same protocol CSV. Noise sweeps use 4,096-qubit batches. Size sweeps use 2% depolarization and 1,024, 2,048, 4,096 and 8,192 qubits. Estimated length and actual simulated output coincide in the plotted conditions. |
| [04 Pool and reserve](consolidated/figures/04_pool_and_reserve_trace.svg) | First held-out manifest job, staggered ties at seed 3000, stabilized v1. [Batch trace](../results/phase10/held-out/batches.csv), [request trace](../results/phase10/held-out/requests.csv) and [manifest](../results/phase10/held-out/manifest.json). Batch completions precede allocations at the same tick. |
| [05 Baselines and ablations](consolidated/figures/05_scheduler_baselines_and_ablations.svg) | [Held-out metrics CSV](../results/phase10/held-out/metrics.csv), 30 paired seeds, three distinct workload families, 14 policy labels and 1,260 runs. Each arm received 2,040 requests, including 387 emergencies. |
| [06 Misses and waits](consolidated/figures/06_deadline_misses_and_waits.svg) | Held-out metrics and request traces. Each missed request counts once in its original class. Empirical wait distributions cover delivered requests. |
| [07 Qubit cost and intervals](consolidated/figures/07_held_out_cost_and_confidence_intervals.svg) | Held-out metrics and [paired trace intervals](../results/phase10/held-out/paired_trace_intervals.csv). Points show experimental v2 minus stabilized v1. Bars are two-sided pointwise 95% Student t intervals on seed-paired differences. |
| [08 AES-GCM correctness and timing](consolidated/figures/08_aes_gcm_correctness_and_performance.svg) | [AES CSV](../results/encryption.csv), 30 trials each for 128, 1,024 and 16,384 bytes. Timings are medians of local calls and include Python overhead. |

The [derived tables](consolidated/tables) include the protocol sweeps, pool
events, held-out data and intervals, encryption trials summarized by payload
size, and separate development metrics for the baseline, each isolated
candidate and their development interaction. Original results for the nine
initial policies remain in [results/scheduling.csv](../results/scheduling.csv).
The full Phase 10 [technical audit](Phase10_Technical_Audit.md) covers the
frozen selection, negative findings and exact replay.

## Findings

- Ideal BB84 retained **6,031 of 12,288** positions with zero sifted
  disagreements. Full simulated interception gave **24.72% mean sampled
  QBER**, close to its 25% model expectation.
- At 4,096 qubits the mean amplified length fell from **562.7 bits** under
  ideal conditions to **316.3 bits** at 2% depolarization and **zero** at 8%.
  At 2% depolarization, increasing the batch to 8,192 raised the mean to
  **877.7 bits**. These are descriptive three-seed results.
- The stronger development baseline covered 30 seeds and five workload
  families. Stabilized v1 delivered **2,393/3,600**, including **515/515**
  emergencies. The dynamic reserve delivered more overall and lost 15
  emergency deliveries. In the isolated fixed-generation and fixed-reserve
  comparison, the deadline-sensitive queue redistributed service between
  classes with no pooled delivery gain.
- On held-out workloads, the frozen candidate delivered **1,297/2,040**
  versus **1,232/2,040** for stabilized v1, with **280,576 fewer started
  qubits**. The mean paired overall delivery gain was **3.19 percentage
  points (95% CI 1.63–4.75)**. Emergencies delivered fell from **311/387
  to 308/387**. The paired emergency difference was **−0.83 points
  (95% CI −2.54 to +0.89)**. The candidate remains experimental.
- **90/90** AES-GCM trials verified the original synthetic payload and
  rejected altered ciphertext. Timings describe local execution with
  no network latency.

## Definitions and limits

**Delivery rate** divides deadline-eligible completed deliveries by offered
requests, with class defined at arrival. **Waiting time** is simulated
completion time minus arrival for delivered requests. **Quantum cost per
delivery** divides summed started qubits by completed requests, while paired
cost intervals average per-seed differences. **Protected stock on hand**
is the lesser of reserve target and current balance. **Actual simulated
output** is accepted Toeplitz output before pool-capacity truncation.
**Estimated length** uses the finite-sample engineering model before an
agreement failure can suppress output. Intervals are pointwise, and the
three-family held-out result depends on the workload mix.

The experiment uses reproducible synthetic traces and simulated BB84.
The estimated key length is a model output and does not establish
composable secrecy. Local AES-GCM checks do not establish endpoint or
network security for a real healthcare deployment.
