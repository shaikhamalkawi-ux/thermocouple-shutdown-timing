"""Finite-table arithmetic checks, NOT raw-data scientific reproduction."""

from __future__ import annotations
import csv
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    with (ROOT / "results" / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def verify():
    primary = load("primary_same_level_r10.csv")
    blocked = load("d50_blocked_r10.csv")
    sensors = {"TR404-333a", "TR404-018b", "TR404-063c", "TR404-085d"}
    assert len(primary) == 24 and len(blocked) == 2
    assert {int(r["run"]) for r in primary} == set(range(4, 10))
    assert {r["sensor"] for r in primary} == sensors
    assert len({(r["run"], r["sensor"]) for r in primary}) == 24
    assert all(float(r["lead_vs_recorded_action_min_rounded"]) > 0 for r in primary)
    nearest = [r for r in primary if r["sensor"] == "TR404-085d"]
    leads = [float(r["lead_vs_recorded_action_min_rounded"]) for r in nearest]
    assert min(leads) == 23.59 and max(leads) == 31.12
    assert abs(median(leads) - 26.99) <= .02  # finite precision of published table
    for r in blocked:
        assert int(r["test"]) in (5, 9)
        raw, fitted = float(r["identity_rmse_C_rounded"]), float(r["mapped_rmse_C_rounded"])
        displayed = float(r["rmse_reduction_percent_rounded"])
        assert abs((1.0 - fitted / raw) * 100.0 - displayed) <= .02
        assert r["first_event_status"] == "right_censored"
        assert r["source_deadline_status"] == "missed"
        assert r["entire_search_history_in_training_support"] == "yes"
        assert float(r["final_mapped_gradient_K_min_minus_1"]) > 1
        assert float(r["strict_horizon_after_source_event_min"]) > 0
    assert {int(r["test"]) for r in blocked} == {5, 9}
    return (len(primary), len(blocked))


if __name__ == "__main__":
    a, b = verify()
    print(f"PASS: {a} rounded primary rows, {b} rounded blocked-test rows; ")
    print("table consistency only; no raw-source replication claimed")
