# Phase 11 and 12 Technical Audit

**Completion date** — 26 November 2026
**Delivery branch** — `final-project`

Stabilized FD-QKS v1 remains the default. This iteration preserves the earlier
algorithms, experiment data and negative findings. It consolidates the evidence
and adds a local, six-section dashboard.

## Repository and reproducibility

| Reference | Evidence |
|---|---|
| `fd-qks-v1-baseline` at `539a909` | Original v1 and four original result CSVs |
| `main` at `f91ee74` | Stabilized v1 and its verification pilot |
| `fd-qks-v2` at `19d3bda` | Completed research, held-out results and negative findings |
| `9a78a10` | Selected [engineering baseline](Final_Engineering_Baseline.md), parameter choices and security assumptions |
| `1c19577` | Eight programmatic figures in PNG and SVG, eleven CSV tables, and a [consolidated results summary](Consolidated_Results.md) |
| `3e88f7f` | Six-section Streamlit dashboard, simulator wiring and four dashboard tests |

The final verification commit adds this audit, reviewed screenshots, and small
chart and study-label refinements. Existing Git references and research assets
are retained. Git comparisons against the research branch verified that the
entire original `results/` tree is unchanged. The supplied Word template,
research document, existing Word draft and existing archive stay local
and untracked.

The figure generator `python -m experiments.final_figures` uses saved CSVs
and the actual Qiskit circuit builder. Generating the outputs a second time
into a separate directory reproduced every file byte-for-byte in the local
environment. See [figures](consolidated/figures) and [tables](consolidated/tables).

## Verification

- **89 automated tests passed in 16.14 seconds.** The suite includes the
  four new dashboard tests and the Phase 10 protocol and scheduling tests.
  `pip check` found no broken requirements.
- **All six sections were exercised in a browser** against Streamlit on
  `127.0.0.1:8501`. The mobile overview at 390 CSS pixels rendered within
  the scroll container, with a 380-pixel content width and no horizontal overflow.
- The downloaded held-out metrics CSV matched its repository source byte-for-byte.
- Negative-path tests cover insufficient BB84 output, an unfinished charged
  batch after a cutoff, and blocked transfer without a complete 256-bit key.

| Section | Browser evidence |
|---|---|
| Overview | Historical v1 figures showed 1,232 of 2,040 total deliveries and 311 of 387 emergency deliveries. [Desktop](dashboard-screenshots/01-overview.jpg) · [Mobile](dashboard-screenshots/07-mobile-overview.jpg) |
| Quantum Lab | Default seed 42, 4,096 transmitted qubits, 2,060 matching bases, 515 sampled bits, 0.00% sampled QBER, agreement, 730 parity disclosures and 565 amplified bits. [Live batch](dashboard-screenshots/02-quantum-lab.jpg) · [Qiskit circuit](dashboard-screenshots/08-bb84-circuit.jpg) |
| Key Management | The Scheduler Lab's run appeared in the shared session. It finished with 899 bits, three whole keys including protected stock, zero ordinary keys and 16,384 completed qubits. The ledger distinguishes completed, cancelled and unfinished generation. [Pool chart](dashboard-screenshots/03-key-management.jpg) |
| Healthcare Transfer | A demonstrated synthetic record received a fresh simulated key allocation. The original decrypted correctly, and AES-GCM rejected a modified ciphertext copy. Only ciphertext, nonce, synthetic plaintext and public counts reached the view. [Live transfer](dashboard-screenshots/04-healthcare-transfer.jpg) |
| Scheduler Lab | Default simultaneous-arrival run at seed 42 delivered 13 of 18 requests, including all three emergencies. Five requests missed their deadlines. The chart and table show arrival, deadline, allocation and outcome. [Live scheduling](dashboard-screenshots/05-scheduler-lab.jpg) |
| Research Results | Held-out and development study controls show saved delivery rates, ablations, uncertainty and file downloads. [Policy chart](dashboard-screenshots/06-research-results.jpg) · [Paired intervals](dashboard-screenshots/09-paired-confidence-intervals.jpg) |

## Consolidated findings

Ideal BB84 retained **6,031 of 12,288** positions with zero sifted errors.
Full simulated interception gave **24.72%** mean sampled QBER. At 2%
depolarization the mean amplified output rose from **zero bits at 1,024
qubits** to **877.7 at 8,192**, across three seeds. The AES benchmark verified
**90 of 90** local round trips and rejected altered ciphertext in all 90.

The held-out study's experimental candidate delivered **65 more requests**
and used **280,576 fewer started qubits**, with **three additional emergency
misses**. Its paired mean overall gain was **3.19 percentage points**
(95% CI **1.63 to 4.75**). Its paired emergency difference was **−0.83 points**
(95% CI **−2.54 to +0.89**). It failed the frozen no-observed-emergency-loss
rule, so stabilized v1 remains the selected default. The dynamic reserve
also missed more emergencies, and the deadline-sensitive queue exceeded its
urgent-service trade-off tolerance during development.

## Remaining limits and submission work

The app uses local grouped Aer and whole-second synthetic workloads.
The pool graph samples state at events, so it does not reconstruct
every intervening dynamic-reserve update. The live controls cap a single
batch at 8,192 qubits and a scheduler run at 32,768. Browser results apply
to the local Streamlit build and the tested desktop and mobile viewport.
There is no networked hospital deployment. QBER is a bit-error observation;
the finite-sample yield uses a phase-error proxy and establishes no
composable secrecy. The transfer is an in-process AES-GCM exercise on
synthetic records.

Remaining submission work is to review and update the academic Word draft
with the selected v1 configuration, figures, held-out trade-offs, citations,
and approved team details. Presentation slides and viva preparation also
remain separate. This iteration leaves the Word draft untouched.
