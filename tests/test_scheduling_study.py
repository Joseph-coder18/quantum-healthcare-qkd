import csv
import json

import pytest

from experiments.scheduling_study import build_manifest, paired_intervals, run_study
from qkd.finite_key import FiniteKeyEstimate
from qkd.pipeline import BB84Batch


def test_paired_intervals_use_seed_level_differences_and_exclude_empty_classes():
    rows = []
    for seed, candidate in enumerate((3, 4, 5)):
        for policy, delivered in (("fd-qks", 4), ("fcfs", candidate)):
            rows.append({
                "scenario": "scarcity", "seed": seed, "policy": policy,
                "priority": "all", "offered": 5, "delivered": delivered, "qubits_started": 4096,
            })
            rows.append({
                "scenario": "scarcity", "seed": seed, "policy": policy,
                "priority": "emergency", "offered": 0, "delivered": 0,
            })

    delivery, qubits = paired_intervals(rows)

    assert delivery["paired_seeds"] == 3
    assert delivery["mean_delta"] == 0
    assert delivery["lower_95"] == pytest.approx(-0.4968275)
    assert delivery["upper_95"] == pytest.approx(0.4968275)
    assert qubits["lower_95"] == qubits["upper_95"] == 0


def test_controlled_study_round_trips_manifest_and_trace_outputs(tmp_path):
    manifest = build_manifest([42, 43], ["scarcity"], controlled=True)
    assert len({(policy["reserve"], policy["generation"])
                for policy in manifest["policies"].values()}) == 1

    def batch(qubits, **kwargs):
        usable = qubits // 4
        return BB84Batch(512, 128, 0, 0, True, FiniteKeyEstimate(0, usable), (0,) * usable)

    original = tmp_path / "original"
    run_study(original, manifest, runner=batch)
    replay = tmp_path / "replay"
    run_study(replay, json.loads((original / "manifest.json").read_text()), runner=batch)

    for filename in ("scheduling.csv", "requests.csv", "batches.csv", "paired_intervals.csv"):
        assert (original / filename).read_bytes() == (replay / filename).read_bytes()
    with (original / "scheduling.csv").open(newline="") as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == 40
    with (original / "batches.csv").open(newline="") as source:
        reader = csv.DictReader(source)
        batch_rows = list(reader)
        assert len(reader.fieldnames) == len(set(reader.fieldnames))
    assert {row["seed"] for row in batch_rows} == {"42", "43"}
    assert all(int(row["batch_seed"]) != int(row["seed"]) for row in batch_rows)
    for row in rows:
        assert int(row["qubits_started"]) == sum(
            int(row[f"qubits_{status}"]) for status in ("completed", "cancelled", "unfinished")
        )
    with pytest.raises(FileExistsError):
        run_study(original, manifest, runner=batch)
