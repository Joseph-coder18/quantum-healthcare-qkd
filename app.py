"""Local Streamlit console for the Quantum Healthcare QKD simulation."""

from dataclasses import asdict
from io import BytesIO

import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.logic import (
    DEFAULT_POLICY, HELD_OUT_RESULTS, LAB_POLICIES, MAX_BUDGET, MAX_QUBITS, RECORDS,
    ROOT, WORKLOADS, pool_events, quantum_experiment, simulate_workload, transfer_record,
)
from qkd.bb84 import measure_bb84_state, prepare_bb84_state
from scheduling.simulation import BatchStatus

st.set_page_config(page_title="Quantum Healthcare QKD", page_icon="⚛", layout="wide")

NAV = ("Overview", "Quantum Lab", "Key Management", "Healthcare Transfer",
       "Scheduler Lab", "Research Results")
PALETTE = ["#2b60a6", "#087c71", "#80579d", "#bf622d"]
INK = "#192c45"
PRIORITIES = ["emergency", "urgent", "routine", "administrative"]
FIGURES = ROOT / "report" / "consolidated" / "figures"
LABELS = {
    "fd-qks": "Stabilized v1", "combined-v2": "Experimental v2",
    "without-ageing": "Without ageing", "without-reserve": "Without reserve",
    "without-adaptive": "Fixed generation", "fcfs": "FCFS", "edf": "EDF",
    "static-priority": "Static priority", "apr-inspired": "APR-inspired",
    "ddka-inspired": "DDKA-inspired", "deadline-generation": "Deadline generation",
    "deadline-sensitive": "Deadline-sensitive queue", "dynamic-reserve": "Dynamic reserve",
    "combined-without-deadline-generation": "V2 without deadline generation",
}
SECURITY = (
    "Synthetic software simulation. Estimated key yield uses a finite-sample engineering model. "
    "It provides no composable QKD proof or production healthcare security."
)

st.html("""
<style>
  .stApp { background:#f4f7fb; }
  [data-testid="stHeader"] { background:rgba(244,247,251,.96); }
  [data-testid="stMainBlockContainer"] { max-width:1320px; padding:3.6rem 2.4rem 3rem; }
  .brand { display:flex; align-items:center; gap:12px; margin:0 0 16px; }
  .brand-icon { display:grid; place-items:center; background:#117a71; color:#fff;
      font-weight:750; font-size:14px; width:42px; height:36px; border-radius:9px; }
  .brand-text { color:#192c45; font-weight:750; font-size:18px; }
  .brand-meta { color:#536981; font-size:12px; margin-left:auto; }
  .hero { background:linear-gradient(116deg,#102844,#10465c); color:#fff;
      border-radius:18px; padding:38px 42px; margin:12px 0 24px; border:1px solid #174561; }
  .hero h1 { color:#fff; font-size:clamp(2rem,4.5vw,3.6rem); line-height:1.05;
      margin:0; padding:0; letter-spacing:-.045em; }
  .hero p { color:#e7f1fb; margin:16px 0 0; max-width:730px; font-size:17px; }
  .layers { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:8px 0 18px; }
  .layer { background:#fff; border:1px solid #dce5ef; border-top:3px solid #16847a;
      border-radius:12px; padding:16px; }
  .layer strong { color:#192c45; font-size:15px; }
  .layer p { color:#4e637a; font-size:13px; margin:6px 0 0; }
  [data-testid="stMetric"] { padding:12px 14px; background:#fff; border:1px solid #dce5ef;
      border-radius:10px; height:100%; }
  [data-testid="stMetricValue"] { font-size:clamp(1.25rem,2.4vw,2rem); }
  @media(max-width:760px) {
    [data-testid="stMainBlockContainer"] { padding:3.2rem 1rem 2rem; }
    .hero { padding:26px 22px; }
    .layers { grid-template-columns:repeat(2,minmax(0,1fr)); }
    .brand-meta { display:none; }
  }
  @media(max-width:420px) { .layers { grid-template-columns:1fr; } }
</style>
<div class="brand"><span class="brand-icon">QKD</span><span class="brand-text">Quantum Healthcare Lab</span>
<span class="brand-meta">Local research simulator · synthetic data</span></div>
""")


@st.cache_data
def csv_data(path):
    return pd.read_csv(path)


def saved(path):
    try:
        return csv_data(path)
    except (OSError, ValueError) as error:
        st.error(f"Saved results could not be loaded: {error}")
        return None


def chart(figure, *, height=375, percent=False):
    figure.update_layout(
        height=height, margin=dict(l=15, r=16, t=18, b=50),
        font=dict(color=INK, family="Arial, sans-serif"),
        paper_bgcolor="white", plot_bgcolor="white",
        legend=dict(orientation="h", y=-0.24, x=0),
        colorway=PALETTE,
    )
    figure.update_xaxes(gridcolor="#e6eef5", automargin=True)
    figure.update_yaxes(gridcolor="#e6eef5", automargin=True)
    if percent:
        figure.update_yaxes(tickformat=".0%")
    st.plotly_chart(figure, width="stretch", theme=None, config={"displaylogo": False})


def heading(title, introduction):
    st.title(title)
    st.write(introduction)


def metrics(items):
    for col, (label, value) in zip(st.columns(len(items)), items, strict=True):
        col.metric(label, value)


def ratio(numerator, denominator):
    return f"{numerator:,} / {denominator:,}"


def policy_label(name):
    return LABELS.get(name, name.replace("-", " ").capitalize())


def delivery_chart(data):
    display = data.assign(
        Policy=data.policy.map(policy_label),
        Group=data.priority.map({"all": "Overall", "emergency": "Emergency"}),
    )
    fig = px.bar(display, x="Policy", y="delivery_rate", color="Group", barmode="group",
                 labels={"delivery_rate": "Delivery rate"},
                 color_discrete_sequence=PALETTE, hover_data=["delivered", "offered"])
    fig.update_yaxes(range=[0, 1.05])
    chart(fig, percent=True)


def overview():
    st.html("""
    <section class="hero"><h1>Quantum keys for<br>time-critical care</h1>
    <p>Explore how a limited pool of simulated quantum keys affects encrypted delivery,
    especially when emergency requests compete with routine traffic.</p></section>
    """)
    data = saved(HELD_OUT_RESULTS / "metrics.csv")
    if data is not None:
        by = data[(data.scenario == "all-scenarios") & (data.policy == "fd-qks")].set_index("priority")
        st.subheader("Stabilized v1 on held-out workloads")
        metrics([
            ("Overall delivered", ratio(by.at["all", "delivered"], by.at["all", "offered"])),
            ("Emergency delivered", ratio(by.at["emergency", "delivered"], by.at["emergency", "offered"])),
            ("Started qubits", f"{by.at['all', 'qubits_started']:,.0f}"),
        ])
        st.caption("Historical experiment · 30 paired seeds across three held-out workload families.")
    st.subheader("Architecture")
    st.html("""
    <div class="layers" role="list">
      <div class="layer" role="listitem"><strong>BB84 simulation</strong><p>Aer prepares and measures qubits. Sifting and post-processing determine usable output.</p></div>
      <div class="layer" role="listitem"><strong>Key management</strong><p>A bounded FIFO pool stores generated bits and protects a reserve for emergencies.</p></div>
      <div class="layer" role="listitem"><strong>FD-QKS scheduling</strong><p>Deadlines, clinical priority and waiting time order requests competing for a key.</p></div>
      <div class="layer" role="listitem"><strong>Healthcare transfer</strong><p>Each delivered synthetic request uses a 256-bit allocation for a verified AES-GCM round trip.</p></div>
    </div>
    """)
    st.subheader("What the experiments show")
    st.write(
        "The project connects simulated BB84 yield to scheduling outcomes under a qubit budget. "
        "Deadline-aware generation helped when the channel recovered, and it missed more emergencies "
        "in the held-out study. Stabilized FD-QKS v1 remains the default under the emergency-protection rule."
    )
    st.info(SECURITY)


@st.cache_data
def circuit_image(bit, alice, bob):
    circuit = measure_bb84_state(prepare_bb84_state(bit, alice), bob)
    drawing = circuit.draw(output="mpl", style="bw", fold=-1)
    output = BytesIO()
    drawing.savefig(output, format="png", dpi=160, bbox_inches="tight")
    plt.close(drawing)
    return output.getvalue()


def quantum_lab():
    heading("Quantum Lab", "Run BB84 with Qiskit Aer and inspect the path from transmitted qubits to usable bits.")
    with st.form("quantum_form"):
        a, b, c, d = st.columns(4)
        qubits = a.number_input("Transmitted qubits", 1, MAX_QUBITS, 4096, step=256,
                                help="Bounded for interactive use. Small batches can produce zero usable bits.")
        noise = b.slider("Depolarization (%)", 0, 100, 0)
        intercept = c.slider("Interception (%)", 0, 100, 0)
        seed = d.number_input("Seed", 0, 2**31 - 1, 42, help="Repeat the same simulated experiment.")
        submitted = st.form_submit_button("Run BB84", type="primary")
    if submitted:
        st.session_state.pop("quantum_live", None)
        try:
            with st.spinner("Simulating and post-processing the BB84 batch…"):
                st.session_state["quantum_live"] = quantum_experiment(qubits, noise / 100, intercept / 100, seed), seed
        except (ValueError, RuntimeError) as error:
            st.error(str(error))
    if "quantum_live" in st.session_state:
        run, run_seed = st.session_state["quantum_live"]
        st.subheader("Live batch")
        st.caption(f"Seed {run_seed:,} · {run.qubits:,} transmissions · grouped Aer")
        metrics([
            ("Basis matches", ratio(run.sifted, run.qubits)),
            ("Sampled QBER", f"{run.qber:.2%}" if run.qber is not None else "Unavailable"),
            ("Estimated length", f"{run.estimated_bits:,} bits"),
            ("Amplified output", f"{run.amplified_bits:,} bits"),
        ])
        agreement = {True: "Agreed", False: "Mismatch", None: "Unavailable"}[run.agreement]
        upper = f"{run.upper_bit_error_bound:.2%}" if run.upper_bit_error_bound is not None else "Unavailable"
        st.write(
            f"Disclosed sample **{run.sampled:,} bits** · Parity disclosure **{run.parity_bits:,} bits** · "
            f"Reconciliation **{agreement}** · Undisclosed bit-error bound **{upper}**"
        )
        st.caption(f"Theoretical matched-basis QBER for these simulated channels: {run.theoretical_qber:.2%}. "
                   "The sampled QBER is a separate measured result.")
        if not run.amplified_bits:
            st.warning("This batch produced no usable key material. Check the sample size, disturbance, and reconciliation result.")
    st.subheader("Single-transmission circuit")
    a, b, c = st.columns(3)
    bit = a.radio("Alice's bit", [0, 1], index=1, horizontal=True)
    alice = b.radio("Alice's basis", ["Z", "X"], index=1, horizontal=True)
    bob = c.radio("Bob's basis", ["Z", "X"], index=1, horizontal=True)
    st.image(circuit_image(bit, alice, bob), width=510, alt=f"Qiskit circuit for bit {bit}, {alice} preparation and {bob} measurement.")
    st.caption("This circuit shows state preparation and measurement. The run applies disturbance in the simulated channel.")
    with st.expander("Attack model and security", expanded=False):
        st.write(
            "Intercept-resend is represented by the averaged channel for a random X or Z measurement. "
            "The model tracks disturbance at Bob’s receiver. The finite-sample calculation uses an undisclosed "
            "bit-error bound as a proxy for phase errors, then accounts for parity disclosure and a fixed penalty. "
            "Reconciled strings must agree before Toeplitz amplification can emit output."
        )
        st.write(SECURITY)


def launch_scenario(policy, scenario, seed, budget, *, noise=0, interception=0, channel=True, cutoff=None):
    st.session_state.pop("scheduler_live", None)
    try:
        with st.spinner("Simulating the synthetic workload…"):
            st.session_state["scheduler_live"] = simulate_workload(
                scenario, policy, seed, budget, noise=noise, interception=interception,
                use_workload_channel=channel, cutoff=cutoff,
            )
    except (ValueError, RuntimeError, OSError) as error:
        st.error(str(error))


def run_caption(run):
    st.caption(f"Live simulation · {run.policy} · {run.scenario.replace('-', ' ')} · seed {run.seed:,}")


def key_management():
    heading("Key Management", "Follow the available balance, protected reserve and generation ledger.")
    with st.form("pool_form"):
        a, b, c = st.columns(3)
        scenario = a.selectbox("Pool demonstration", list(WORKLOADS), index=0)
        budget = b.number_input("Pool qubit budget", 0, MAX_BUDGET, 16384, step=1024)
        cutoff = c.number_input("Observation cutoff (s, 0 for full run)", 0, 35, 0,
                                help="An early cutoff can leave a charged batch unfinished.")
        submitted = st.form_submit_button("Run pool demonstration", type="primary")
    if submitted:
        launch_scenario(DEFAULT_POLICY, WORKLOADS[scenario], 42, budget, cutoff=cutoff or None)
    run = st.session_state.get("scheduler_live")
    if run is None:
        st.info("Run the demonstration or run a workload in Scheduler Lab to see its live key pool.")
        return
    run_caption(run)
    result = run.result
    available = result.remaining_bits
    metrics([
        ("Pool balance", f"{available:,} bits"),
        ("Ordinary AES keys available", f"{max(0, available - run.final_reserve) // 256:,}"),
        ("AES keys including reserve", f"{available // 256:,}"),
        ("Qubit budget used", ratio(result.qubits_started, run.budget)),
    ])
    st.subheader("Occupancy and protected stock")
    events = pd.DataFrame(pool_events(run))
    fig = go.Figure()
    fig.add_scatter(x=events.seconds, y=events.protected_bits, name="Protected bits on hand",
                    fill="tozeroy", line=dict(color="#e2a449", shape="hv"))
    fig.add_scatter(x=events.seconds, y=events.pool_bits, name="Pool balance", mode="lines+markers",
                    text=events.event, line=dict(color=PALETTE[0], shape="hv"),
                    hovertemplate="%{text}<br>%{x}s · %{y} bits<extra></extra>")
    fig.add_scatter(x=events.seconds, y=events.reserve_bits, name="Reserve target at events",
                    line=dict(color=PALETTE[1], dash="dot", shape="hv"))
    fig.update_layout(xaxis_title="Simulation time (s)", yaxis_title="Key material (bits)")
    chart(fig)
    st.subheader("Generation ledger")
    metrics([(status.value.capitalize(), f"{result.qubits_for(status):,} qubits") for status in BatchStatus])
    st.caption("All starts charge the budget. Completed accepted batches can add stock. "
               "The chart shows reserve snapshots at recorded events.")
    if result.batches:
        batches = pd.DataFrame(asdict(batch) for batch in result.batches)
        st.dataframe(batches[["batch_id", "status", "qubits", "started_at", "scheduled_completion",
                              "completed_at", "cancelled_at", "sampled_qber", "estimated_bits",
                              "output_bits", "admitted_bits", "rejection_reason"]], hide_index=True)
    else:
        st.info("No generation batches started in this observation.")
    with st.expander("Allocation and generation events"):
        st.dataframe(events.drop(columns="protected_bits"), hide_index=True)


def healthcare_transfer():
    heading("Healthcare Transfer", "Allocate simulated BB84 output to an in-process AES-256-GCM transfer.")
    with st.form("healthcare_form"):
        a, b = st.columns([2, 1])
        record = a.selectbox("Synthetic medical record", list(RECORDS))
        noise = b.slider("Transfer depolarization (%)", 0, 100, 0,
                         help="At high disturbance the lab may refuse the transfer due to insufficient output.")
        tamper = st.checkbox("Demonstrate authentication failure on a modified copy", value=True)
        submitted = st.form_submit_button("Encrypt and verify", type="primary")
    if submitted:
        st.session_state.pop("transfer_live", None)
        try:
            with st.spinner("Generating a simulated key and verifying the transfer…"):
                st.session_state["transfer_live"] = transfer_record(
                    record, demonstrate_tampering=tamper, noise=noise / 100,
                ), record
        except (ValueError, RuntimeError) as error:
            st.error(str(error))
    if "transfer_live" in st.session_state:
        transfer, used_record = st.session_state["transfer_live"]
        st.caption(f"Live transfer · {used_record}")
        if transfer.verified:
            st.success("Decryption verified the original synthetic record.")
            metrics([("Usable BB84 output", f"{transfer.usable_bits:,} bits"),
                     ("Allocated AES key", "256 bits"),
                     ("Ciphertext and tag", f"{len(transfer.ciphertext_hex) // 2:,} bytes")])
            a, b = st.columns(2)
            with a:
                st.subheader("Ciphertext and tag")
                st.code(transfer.ciphertext_hex, language=None, wrap_lines=True)
                st.caption(f"Public nonce: {transfer.nonce_hex}")
            with b:
                st.subheader("Verified plaintext")
                st.code(transfer.plaintext_json, language="json", wrap_lines=True)
            if transfer.modified_rejected is True:
                st.success("The modified ciphertext was rejected by AES-GCM (authentication failed).")
            elif transfer.modified_rejected is False:
                st.error("The modified ciphertext was unexpectedly accepted.")
        else:
            st.warning(f"Transfer stopped with {transfer.usable_bits} usable bits. AES-256-GCM requires a complete 256-bit allocation.")
    st.caption(SECURITY)


def scheduler_lab():
    heading("Scheduler Lab", "Compare scheduling rules under the same synthetic request and qubit constraints.")
    with st.form("scheduler_form"):
        a, b, c, d = st.columns([1.35, 1.2, 0.75, 0.85])
        policy = a.selectbox("Scheduling policy", list(LAB_POLICIES))
        scenario = b.selectbox("Synthetic workload", list(WORKLOADS))
        seed = c.number_input("Workload seed", 0, 2**31 - 1, 42)
        budget = d.number_input("Run qubit budget", 0, MAX_BUDGET, 16384, step=1024)
        a, b, c = st.columns(3)
        channel = a.selectbox("Channel model", ["Use workload conditions", "Use constant settings"])
        noise = b.slider("Run depolarization (%)", 0, 100, 0, help="Used with constant settings.")
        interception = c.slider("Run interception (%)", 0, 100, 0, help="Used with constant settings.")
        submitted = st.form_submit_button("Run scheduler", type="primary")
    if submitted:
        launch_scenario(policy, WORKLOADS[scenario], seed, budget, noise=noise / 100,
                        interception=interception / 100, channel=channel == "Use workload conditions")
    run = st.session_state.get("scheduler_live")
    if run is None:
        st.info("Select a workload and run the scheduler to see allocations and deadline misses.")
        return
    run_caption(run)
    result = run.result
    requests = pd.DataFrame(asdict(trace) for trace in result.requests)
    emergency = requests[requests.priority == "emergency"]
    metrics([
        ("Overall delivered", ratio(len(result.delivered), len(requests))),
        ("Emergency delivered", ratio(int(emergency.completion_time.notna().sum()), len(emergency)) if len(emergency) else "None offered"),
        ("Deadline misses", f"{len(result.missed):,}"),
        ("Unresolved", f"{len(result.unresolved):,}"),
    ])
    requests["outcome"] = requests.reason.fillna("delivered").str.replace("_", " ").str.title()
    requests["wait_s"] = pd.to_numeric(requests.completion_time) - requests.arrival
    st.subheader("Request timing")
    fig = go.Figure()
    x, y = [], []
    for row in requests.itertuples():
        x.extend((row.arrival, row.deadline, None))
        y.extend((row.request_id, row.request_id, None))
    fig.add_scatter(x=x, y=y, mode="lines", name="Arrival to deadline", line=dict(color="#9aaec3"),
                    hoverinfo="skip")
    for state, color, symbol, field in (
        ("Delivered", PALETTE[1], "circle", "completion_time"),
        ("Deadline Missed", "#b84a35", "x", "deadline"),
        ("Observation Ended", "#8b6b3b", "diamond", "outcome_at"),
    ):
        subset = requests[requests.outcome == state]
        if len(subset):
            fig.add_scatter(x=subset[field], y=subset.request_id, mode="markers", name=state,
                            marker=dict(color=color, symbol=symbol, size=9), text=subset.priority,
                            hovertemplate="%{y} · %{text}<br>%{x}s<extra></extra>")
    fig.update_layout(xaxis_title="Simulation time (s)", yaxis_title="Synthetic request")
    chart(fig, height=470)
    st.dataframe(requests[["request_id", "priority", "effective_priority", "arrival", "deadline",
                           "allocation_time", "wait_s", "outcome"]], hide_index=True)
    st.caption("Switch to Key Management to inspect this run’s reserve and generation accounting.")


def research_results():
    heading("Research Results", "Explore saved measurements with policy comparisons, uncertainty, and source downloads.")
    study = st.selectbox("Saved study", ["Held-out evaluation", "Development baseline", "Reserve ablation",
                                        "Generation ablation", "Queue comparison", "Combined development"])
    folder_name = {
        "Held-out evaluation": "held-out", "Development baseline": "stabilized-baseline",
        "Reserve ablation": "reserve-development", "Generation ablation": "generation-development",
        "Queue comparison": "queue-development", "Combined development": "combined-development",
    }[study]
    folder = ROOT / "results" / "phase10" / folder_name
    data = saved(folder / "metrics.csv")
    intervals = saved(folder / "paired_trace_intervals.csv")
    if data is None or intervals is None:
        return
    st.caption("Historical experiment · Phase 10 · 30 paired seeds per workload family")
    scenario = st.selectbox("Workload family", sorted(data.scenario.unique()), format_func=lambda item: item.replace("-", " ").title())
    subset = data[data.scenario == scenario]
    choices = sorted(subset.policy.unique())
    preferred = ["fd-qks", "combined-v2", "apr-inspired", "fcfs"] if study == "Held-out evaluation" else choices
    selected = st.multiselect("Policies to compare", choices, [item for item in preferred if item in choices],
                              format_func=policy_label)
    comparison = subset[subset.policy.isin(selected) & subset.priority.isin(["all", "emergency"])]
    if comparison.empty:
        st.info("Select at least one policy.")
    else:
        st.subheader("Emergency and overall delivery")
        delivery_chart(comparison)
        table = comparison.copy()
        table["policy"] = table.policy.map(policy_label)
        st.dataframe(table[["policy", "priority", "offered", "delivered", "deadline_missed",
                            "served_wait_p90", "started_qubits_per_delivery"]], hide_index=True)
    st.subheader("Paired 95% confidence intervals")
    results = intervals[(intervals.scenario == scenario) & (intervals.metric == "delivery_rate")
                        & intervals.priority.isin(["all", "emergency"]) & intervals.policy.isin(selected)].copy()
    if results.empty:
        st.info("Select a comparison policy to see its paired difference versus stabilized v1.")
    else:
        results["label"] = results.policy.map(policy_label) + " · " + results.priority
        fig = go.Figure(go.Scatter(
            x=100 * results.mean_delta, y=results.label, mode="markers",
            marker=dict(color=PALETTE[0], size=9),
            error_x=dict(type="data", symmetric=False,
                         array=100 * (results.upper_95 - results.mean_delta).fillna(0),
                         arrayminus=100 * (results.mean_delta - results.lower_95).fillna(0)),
            customdata=results.paired_seeds,
            hovertemplate="%{y}<br>%{x:.2f} pp · %{customdata} paired seeds<extra></extra>",
        ))
        fig.add_vline(x=0, line_dash="dash", line_color="#b88040")
        fig.update_layout(xaxis_title="Delivery difference versus stabilized v1 (percentage points)")
        chart(fig, height=max(275, 30 * len(results) + 100))
    st.info("Stabilized v1 remains the default. Experimental v2 used fewer qubits and delivered more overall "
            "in the held-out set, with three additional emergency misses and a higher served waiting-time p90.")
    st.subheader("Download source data")
    a, b, c = st.columns(3)
    for col, filename, label in zip((a, b, c), ("metrics.csv", "paired_trace_intervals.csv", "manifest.json"),
                                    ("Download metrics CSV", "Download intervals CSV", "Download manifest"),
                                    strict=True):
        path = folder / filename
        if path.is_file():
            col.download_button(label, path.read_bytes(), file_name=f"{folder_name}-{filename}",
                                mime="text/csv" if filename.endswith(".csv") else "application/json")
    with st.expander("Protocol and encryption figures"):
        for path in sorted(FIGURES.glob("*.png")):
            st.image(str(path), width="stretch")


section = st.segmented_control("Dashboard section", NAV, default=NAV[0], required=True,
                               label_visibility="collapsed", width="stretch", wrap=True,
                               key="section")
{
    "Overview": overview,
    "Quantum Lab": quantum_lab,
    "Key Management": key_management,
    "Healthcare Transfer": healthcare_transfer,
    "Scheduler Lab": scheduler_lab,
    "Research Results": research_results,
}[section]()
