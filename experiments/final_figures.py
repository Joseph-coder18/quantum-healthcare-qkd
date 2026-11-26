"""Generate Phase 11 figures and tables from the committed simulation results."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from qkd.bb84 import measure_bb84_state, prepare_bb84_state

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
HELD = RESULTS / "phase10" / "held-out"
INK, BLUE, TEAL, AMBER = "#16263b", "#285a98", "#168079", "#a24f24"
LABELS = {
    "fd-qks": "Stabilized v1", "combined-v2": "Experimental v2",
    "fcfs": "FCFS", "static-priority": "Static priority", "edf": "EDF",
    "ddka-inspired": "DDKA-inspired", "apr-inspired": "APR-inspired",
    "without-ageing": "Without ageing", "without-reserve": "Without reserve",
    "without-adaptive": "Fixed generation", "dynamic-reserve": "Dynamic reserve",
    "deadline-sensitive": "Deadline-sensitive queue",
}
BASELINES = ("fd-qks", "fcfs", "static-priority", "edf", "ddka-inspired", "apr-inspired")
ABLATIONS = ("fd-qks", "without-ageing", "without-reserve", "without-adaptive")
CLASSES = ("emergency", "urgent", "routine", "administrative")

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "text.color": INK,
    "axes.labelcolor": INK, "axes.edgecolor": "#93a6b8", "axes.spines.top": False,
    "axes.spines.right": False, "axes.titleweight": "bold", "grid.alpha": 0.24,
    "figure.facecolor": "white", "svg.hashsalt": "quantum-healthcare-qkd",
})


def save(fig, target: Path, name: str) -> None:
    fig.savefig(target / f"{name}.png", dpi=220, bbox_inches="tight",
                metadata={"Software": "quantum-healthcare-qkd"})
    vector = target / f"{name}.svg"
    fig.savefig(vector, bbox_inches="tight", metadata={"Date": None})
    vector.write_text(
        "\n".join(line.rstrip() for line in vector.read_text(encoding="utf-8").splitlines()) + "\n",
        encoding="utf-8",
    )
    plt.close(fig)


def label_panel(ax, title: str, *, axis: str = "y") -> None:
    ax.set_title(title, loc="left", pad=13)
    ax.grid(axis=axis)
    ax.set_axisbelow(True)


def mean_line(ax, frame, x, y, *, x_scale=1, y_scale=1, color=BLUE, label=None, style="o-"):
    grouped = frame.groupby(x, sort=True)[y]
    x_values = grouped.mean().index.to_numpy() * x_scale
    ax.plot(x_values, grouped.mean().to_numpy() * y_scale, style, color=color, label=label)
    for value, points in grouped:
        ax.scatter(np.full(len(points), value * x_scale), points * y_scale,
                   color=color, alpha=0.38, s=18, zorder=4)
    return x_values


def quantum_figures(target: Path, tables: Path) -> None:
    correctness = pd.read_csv(RESULTS / "bb84_correctness.csv")
    correctness["sifted_fraction"] = correctness.sifted / correctness.qubits
    correctness.to_csv(tables / "bb84_correctness.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), layout="constrained",
                             gridspec_kw={"width_ratios": [1, 1.4]})
    ax = axes[0]
    bar = ax.bar(correctness.seed.astype(str), 100 * correctness.sifted_fraction, color=BLUE)
    ax.bar_label(bar, fmt="%.1f%%", padding=3)
    ax.axhline(50, ls="--", color=AMBER, label="Expected basis match")
    ax.set(xlabel="Simulation seed", ylabel="Sifted share (%)", ylim=(0, 64))
    label_panel(ax, "Ideal-channel sifting")
    ax.legend(loc="upper right", frameon=False, fontsize=8)
    ax.text(0.02, 0.06, f"{correctness.sifted_errors.sum():,} sifted disagreements",
            transform=ax.transAxes, color="white",
            bbox={"facecolor": BLUE, "edgecolor": "none", "pad": 3})
    circuit = measure_bb84_state(prepare_bb84_state(1, "X"), "X")
    circuit.draw(output="mpl", ax=axes[1], style="bw", fold=-1)
    axes[1].set_title("BB84 circuit · Alice sends 1 in X; Bob measures in X", loc="left", fontsize=10)
    save(fig, target, "01_bb84_correctness_and_circuit")

    study = pd.read_csv(RESULTS / "bb84_channel_and_yield.csv")
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.1), layout="constrained")
    for ax, kind, x, slope, label in (
        (axes[0], "interception", "interception", 0.25, "Interception probability (%)"),
        (axes[1], "noise", "depolarization", 0.5, "Depolarization (%)"),
    ):
        values = mean_line(ax, study[study.experiment == kind], x, "sampled_qber",
                           x_scale=100, y_scale=100, label="Measured mean")
        ax.plot(values, values * slope, "--", color=AMBER, label="Isolated model expectation")
        ax.set(xlabel=label, ylabel="Sampled QBER (%)")
        label_panel(ax, "Intercept-resend disturbance" if kind == "interception" else "Channel noise")
        ax.legend(frameon=False, fontsize=8)
    save(fig, target, "02_channel_disturbance_and_qber")

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.1), layout="constrained")
    for ax, kind, x, scale, title, label in (
        (axes[0], "noise", "depolarization", 100, "Noise and key output", "Depolarization (%)"),
        (axes[1], "finite_key", "qubits", 1, "Finite-sample batch-size effect", "Transmitted qubits"),
    ):
        rows = study[study.experiment == kind]
        mean_line(ax, rows, x, "amplified_bits", x_scale=scale, color=TEAL, label="Actual simulated output")
        mean_line(ax, rows, x, "estimated_bits", x_scale=scale, color=AMBER,
                  label="Estimated length", style="x--")
        ax.set(xlabel=label, ylabel="Bits per batch")
        label_panel(ax, title)
        ax.legend(frameon=False, fontsize=8)
    save(fig, target, "03_noise_and_finite_sample_yield")
    study.groupby(["experiment", "depolarization", "interception", "qubits"], as_index=False).agg(
        seeds=("seed", "nunique"), mean_qber=("sampled_qber", "mean"),
        mean_estimated_bits=("estimated_bits", "mean"), mean_amplified_bits=("amplified_bits", "mean"),
        batches_in_agreement=("agreement", "sum"),
    ).to_csv(tables / "protocol_sweeps.csv", index=False)


def rate_plot(ax, frame, policies, title: str) -> None:
    table = frame.pivot(index="policy", columns="priority", values="delivery_rate").loc[list(policies)]
    index = np.arange(len(table))
    ax.barh(index + 0.16, 100 * table["all"], 0.29, color=BLUE, label="All requests")
    ax.barh(index - 0.16, 100 * table["emergency"], 0.29, color=TEAL, label="Emergency")
    ax.set(yticks=index, yticklabels=[LABELS[name] for name in table.index],
           xlabel="Delivery rate (%)", xlim=(0, 105))
    ax.invert_yaxis()
    label_panel(ax, title, axis="x")


def pool_figure(target: Path, tables: Path, batches, requests) -> None:
    manifest = json.loads((HELD / "manifest.json").read_text())
    job = manifest["workloads"][0]
    identity = (job["scenario"], job["seed"])
    p = requests[(requests.scenario == identity[0]) & (requests.seed == identity[1]) & (requests.policy == "fd-qks")]
    b = batches[(batches.scenario == identity[0]) & (batches.seed == identity[1]) & (batches.policy == "fd-qks")]
    events = [(0, -1, "Initial stock", job["initial_pool_bits"], manifest["policies"]["fd-qks"]["reserve"])]
    events.extend((row.completed_at, 0, "Generation completed", row.pool_after, row.reserve_bits)
                  for row in b.itertuples() if row.status == "completed")
    events.extend((row.allocation_time, row.allocation_id + 1, "Delivery allocation", row.pool_after, row.reserve_bits)
                  for row in p.itertuples() if pd.notna(row.allocation_id))
    trace = pd.DataFrame(sorted(events), columns=["seconds", "order", "event", "pool_bits", "reserve_bits"])
    trace.to_csv(tables / "key_pool_example.csv", index=False)
    fig, ax = plt.subplots(figsize=(10.5, 4.1), layout="constrained")
    ax.step(trace.seconds, trace.pool_bits, where="post", color=BLUE, lw=2, label="Pool stock")
    ax.step(trace.seconds, trace.reserve_bits, where="post", color=AMBER, ls="--", label="Reserve target")
    ax.fill_between(trace.seconds, np.minimum(trace.pool_bits, trace.reserve_bits), step="post",
                    color=AMBER, alpha=0.16, label="Protected stock on hand")
    for name, color, marker in (("Generation completed", TEAL, "^"), ("Delivery allocation", BLUE, ".")):
        selected = trace[trace.event == name]
        ax.scatter(selected.seconds, selected.pool_bits, color=color, marker=marker, label=name, zorder=4)
    label_panel(ax, f"Stabilized v1 key pool · {identity[0]}, seed {identity[1]}")
    ax.set(xlabel="Simulation time (s)", ylabel="Key material (bits)")
    ax.legend(frameon=False, ncols=2, fontsize=8)
    save(fig, target, "04_pool_and_reserve_trace")


def scheduling_figures(target: Path, tables: Path) -> None:
    metrics = pd.read_csv(HELD / "metrics.csv")
    requests = pd.read_csv(HELD / "requests.csv")
    batches = pd.read_csv(HELD / "batches.csv")
    intervals = pd.read_csv(HELD / "paired_trace_intervals.csv")
    metrics.to_csv(tables / "held_out_metrics.csv", index=False)
    intervals[intervals.policy == "combined-v2"].to_csv(tables / "held_out_v2_paired_intervals.csv", index=False)
    for name in ("stabilized-baseline", "reserve-development", "generation-development",
                 "queue-development", "combined-development"):
        pd.read_csv(RESULTS / "phase10" / name / "metrics.csv").to_csv(
            tables / f"{name}_metrics.csv", index=False)
    pool_figure(target, tables, batches, requests)

    pooled = metrics[metrics.scenario == "all-scenarios"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), layout="constrained")
    rate_plot(axes[0], pooled, BASELINES, "Held-out scheduler baselines")
    rate_plot(axes[1], pooled, ABLATIONS, "Stabilized v1 ablations")
    axes[0].legend(loc="lower right", frameon=False, fontsize=8)
    save(fig, target, "05_scheduler_baselines_and_ablations")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.3), layout="constrained")
    chosen = ("fd-qks", "combined-v2")
    classes = pooled[pooled.priority.isin(CLASSES)].pivot(
        index="priority", columns="policy", values="deadline_missed").loc[list(CLASSES)]
    index = np.arange(len(classes))
    for i, (policy, color) in enumerate(zip(chosen, (BLUE, TEAL), strict=True)):
        axes[0].bar(index + 0.34 * (i - 0.5), classes[policy], 0.31, color=color, label=LABELS[policy])
        served = requests[(requests.policy == policy) & requests.completion_time.notna()]
        waits = (served.completion_time - served.arrival).sort_values().to_numpy()
        axes[1].step(waits, 100 * np.arange(1, len(waits) + 1) / len(waits), where="post",
                     color=color, label=LABELS[policy])
    axes[0].set(xticks=index, xticklabels=[label.title() for label in CLASSES], ylabel="Missed requests")
    axes[1].set(xlabel="Waiting time of delivered requests (s)", ylabel="Cumulative share (%)")
    label_panel(axes[0], "Held-out deadline misses by class")
    label_panel(axes[1], "Held-out waiting-time distribution")
    for ax in axes:
        ax.legend(frameon=False, fontsize=8)
    save(fig, target, "06_deadline_misses_and_waits")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout="constrained")
    costs = pooled[(pooled.priority == "all") & pooled.policy.isin((*BASELINES, "combined-v2"))]
    costs = costs.sort_values("started_qubits_per_delivery", ascending=False)
    axes[0].barh(costs.policy.map(LABELS), costs.started_qubits_per_delivery,
                 color=[TEAL if name == "combined-v2" else BLUE for name in costs.policy])
    axes[0].set_xlabel("Started qubits per delivery")
    label_panel(axes[0], "Held-out quantum resource cost", axis="x")
    effects = intervals[(intervals.policy == "combined-v2") & (intervals.metric == "delivery_rate")
                        & intervals.priority.isin(["all", "emergency"])].sort_values(["scenario", "priority"])
    for i, row in enumerate(effects.itertuples()):
        delta, low, high = 100 * np.array([row.mean_delta, row.lower_95, row.upper_95])
        axes[1].errorbar(delta, i, xerr=[[delta - low], [high - delta]], fmt="o",
                         color=TEAL if row.priority == "emergency" else BLUE, capsize=3)
    axes[1].set(yticks=range(len(effects)), yticklabels=[
        f"{row.scenario.replace('-', ' ').title()} · {row.priority}" for row in effects.itertuples()
    ], xlabel="v2 minus v1 delivery (percentage points)")
    axes[1].axvline(0, ls="--", color=AMBER)
    axes[1].invert_yaxis()
    label_panel(axes[1], "Paired 95% confidence intervals", axis="x")
    save(fig, target, "07_held_out_cost_and_confidence_intervals")


def encryption_figure(target: Path, tables: Path) -> None:
    trials = pd.read_csv(RESULTS / "encryption.csv")
    summary = trials.groupby("payload_bytes", as_index=False).agg(
        trials=("trial", "count"), verified=("round_trip_correct", "sum"),
        tamper_rejected=("tamper_rejected", "sum"),
        median_encrypt_ns=("encrypt_ns", "median"), median_decrypt_ns=("decrypt_ns", "median"),
    )
    summary.to_csv(tables / "aes_gcm_summary.csv", index=False)
    fig, ax = plt.subplots(figsize=(8, 4.2), layout="constrained")
    ax.plot(summary.payload_bytes, summary.median_encrypt_ns / 1000, "o-", color=BLUE, label="Encrypt")
    ax.plot(summary.payload_bytes, summary.median_decrypt_ns / 1000, "o-", color=TEAL, label="Decrypt")
    ax.set(xscale="log", xlabel="Synthetic payload (bytes)", ylabel="Median wall time (μs)")
    ax.set_xticks(summary.payload_bytes, [f"{size:,}" for size in summary.payload_bytes])
    ax.text(0.03, 0.94, f"{summary.verified.sum()}/{len(trials)} round trips verified · "
            f"{summary.tamper_rejected.sum()}/{len(trials)} tampering trials rejected",
            transform=ax.transAxes, va="top", fontsize=9)
    label_panel(ax, "Local AES-256-GCM benchmark")
    ax.legend(frameon=False, loc="lower right")
    save(fig, target, "08_aes_gcm_correctness_and_performance")


def generate(destination: Path) -> None:
    figures, tables = destination / "figures", destination / "tables"
    figures.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)
    quantum_figures(figures, tables)
    scheduling_figures(figures, tables)
    encryption_figure(figures, tables)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "report" / "consolidated")
    generate(parser.parse_args().output_dir)


if __name__ == "__main__":
    main()
