#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

SOURCE_SENSOR = "TR404-108e"
CANDIDATES = ["TR404-333a", "TR404-018b", "TR404-063c", "TR404-085d"]
RADII_MM = {"TR404-333a": 0, "TR404-018b": 30, "TR404-063c": 60, "TR404-085d": 80, SOURCE_SENSOR: 95}
PRIMARY_RUNS = [4, 5, 6, 7, 8, 9]
ANCILLARY_RUNS = [1, 2, 3]
WINDOW_MIN = 15.0
GRADIENT_THRESHOLD = 1.0
HEATER_ON_THRESHOLD_MA = 4.5
VALID_T_MIN_C = 0.0
VALID_T_MAX_C = 550.0

EXPECTED_SOURCE = {
    1: (20235, "680e90905a75c2c4b554d8e7a900483b354bec8195ee8475dd8a4bded3f84a7d"),
    2: (20514, "9c2974b9ff2369b26cb9a69175b67cc1b5a4827d971e75a071a77408c332fe2d"),
    3: (24091, "21e8293da2a8faaf2a257d3baef393d8c0867152f991583875aa91bd6328e869"),
    4: (14766, "985f4452c04e495c6f07227d3ce238975d596caa5a9ea04f8e52fb08645e1d68"),
    5: (16243, "3318140e2de217cce5c407f862b238385f5872e46a11710ef8fed260cce22425"),
    6: (11069, "cbbf5b9846c2bd0945cebf6517f8a9b003f7d4b5aaf54c1de6bc8dc8de1a629b"),
    7: (15935, "19b88ec506a3e2407ca4bb40adeb8247d2467f4913b0a62de39afede45254a6b"),
    8: (9076, "1cbfdd865524224959a0d28836528c79dc7228e37e725e9e4be7b32f4ea799ef"),
    9: (14058, "050bd98e110121a9063e7c361f8a7cbbedad55fea6eed42c05e2e69a22ccbe2e"),
}


def sha256_file(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def extract_source_zips(source_zips: Path, dest: Path) -> None:
    for zp in sorted(source_zips.glob("DGIG_WEBER_CORE_*.zip")):
        with zipfile.ZipFile(zp, "r") as z:
            z.extractall(dest)


def load_measurement(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", decimal=",", low_memory=False)
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    return df


def test_number(path: Path) -> int:
    m = re.match(r"(\d+)_", path.parent.name)
    if not m:
        raise ValueError(f"Cannot infer test number from {path}")
    return int(m.group(1))


def longest_true_segment(mask: np.ndarray) -> tuple[int, int]:
    arr = np.asarray(mask, dtype=bool)
    starts = np.where(arr & np.r_[True, ~arr[:-1]])[0]
    ends = np.where(arr & np.r_[~arr[1:], True])[0] + 1
    if len(starts) == 0:
        raise ValueError("No heater-on segment found")
    lengths = ends - starts
    k = int(np.argmax(lengths))
    return int(starts[k]), int(ends[k])


def interp_at(t: np.ndarray, y: np.ndarray, tq: float) -> float:
    return float(np.interp(tq, t, y))


def finite_gradient(t: np.ndarray, y: np.ndarray, tq: float) -> float:
    return (interp_at(t, y, tq) - interp_at(t, y, tq - WINDOW_MIN)) / WINDOW_MIN


def gradient_series(t: np.ndarray, y: np.ndarray, start_i: int, action_i: int) -> tuple[np.ndarray, np.ndarray]:
    idx = np.arange(start_i, action_i + 1)
    valid = idx[t[idx] >= t[start_i] + WINDOW_MIN]
    past = np.interp(t[valid] - WINDOW_MIN, t, y)
    g = (y[valid] - past) / WINDOW_MIN
    return valid, g


def crossings(t: np.ndarray, y: np.ndarray, start_i: int, action_i: int) -> tuple[list[float], list[float]]:
    idx, g = gradient_series(t, y, start_i, action_i)
    tt = t[idx]
    downs: list[float] = []
    ups: list[float] = []
    for k in range(1, len(g)):
        g0, g1 = g[k - 1], g[k]
        if not (np.isfinite(g0) and np.isfinite(g1)) or g1 == g0:
            continue
        if g0 >= GRADIENT_THRESHOLD and g1 < GRADIENT_THRESHOLD:
            tc = tt[k - 1] + (GRADIENT_THRESHOLD - g0) * (tt[k] - tt[k - 1]) / (g1 - g0)
            downs.append(float(tc))
        elif g0 < GRADIENT_THRESHOLD and g1 >= GRADIENT_THRESHOLD:
            tc = tt[k - 1] + (GRADIENT_THRESHOLD - g0) * (tt[k] - tt[k - 1]) / (g1 - g0)
            ups.append(float(tc))
    return downs, ups


def first_crossing(t: np.ndarray, y: np.ndarray, start_i: int, action_i: int) -> float | None:
    downs, _ = crossings(t, y, start_i, action_i)
    return downs[0] if downs else None


def stable_crossing(t: np.ndarray, y: np.ndarray, start_i: int, action_i: int) -> float | None:
    downs, _ = crossings(t, y, start_i, action_i)
    if not downs:
        return None
    # Because the recorded-action gradient is below threshold for the admitted source/candidate cases,
    # the last downward crossing is the first crossing after which the criterion remains satisfied.
    return downs[-1]


def rolling_ols_slope(t: np.ndarray, y: np.ndarray, start_i: int, action_i: int) -> np.ndarray:
    out = np.full(len(t), np.nan)
    tt = t[start_i:action_i + 1]
    yy = y[start_i:action_i + 1]
    ct = np.r_[0.0, np.cumsum(tt)]
    cy = np.r_[0.0, np.cumsum(yy)]
    ctt = np.r_[0.0, np.cumsum(tt * tt)]
    cty = np.r_[0.0, np.cumsum(tt * yy)]
    left = 0
    for j in range(len(tt)):
        if tt[j] < tt[0] + WINDOW_MIN:
            continue
        while left < j and tt[left] < tt[j] - WINDOW_MIN:
            left += 1
        n = j - left + 1
        sx = ct[j + 1] - ct[left]
        sy = cy[j + 1] - cy[left]
        sxx = ctt[j + 1] - ctt[left]
        sxy = cty[j + 1] - cty[left]
        den = n * sxx - sx * sx
        if den != 0:
            out[start_i + j] = (n * sxy - sx * sy) / den
    return out


def series_crossing(t: np.ndarray, value: np.ndarray, start_i: int, action_i: int, threshold: float = 1.0) -> float | None:
    seen_ge = False
    for i in range(start_i, action_i + 1):
        v = value[i]
        if not np.isfinite(v):
            continue
        if v >= threshold:
            seen_ge = True
        elif seen_ge and v < threshold:
            j = i - 1
            while j >= start_i and not np.isfinite(value[j]):
                j -= 1
            if j < start_i or value[i] == value[j]:
                return float(t[i])
            return float(t[j] + (threshold - value[j]) * (t[i] - t[j]) / (value[i] - value[j]))
    return None


def clean_channel(y: np.ndarray, start_i: int, action_i: int) -> bool:
    z = y[start_i:action_i + 1]
    return bool(np.all(np.isfinite(z)) and np.min(z) >= VALID_T_MIN_C and np.max(z) <= VALID_T_MAX_C)


def verify_source_files(measurements: list[Path]) -> pd.DataFrame:
    rows = []
    for p in measurements:
        run = test_number(p)
        df = load_measurement(p)
        exp_rows, exp_hash = EXPECTED_SOURCE[run]
        obs_hash = sha256_file(p)
        rows.append({
            "run": run,
            "source_member": f"{p.parent.name}/MeasurementData.CSV",
            "rows_observed": len(df),
            "rows_expected": exp_rows,
            "row_match": len(df) == exp_rows,
            "sha256_observed": obs_hash,
            "sha256_expected": exp_hash,
            "hash_match": obs_hash == exp_hash,
        })
    return pd.DataFrame(rows).sort_values("run")


def reconstruct_action(df: pd.DataFrame, threshold_ma: float = HEATER_ON_THRESHOLD_MA) -> tuple[int, int]:
    start_i, end_exclusive = longest_true_segment(df["Heater_AO"].to_numpy(float) > threshold_ma)
    if end_exclusive >= len(df):
        raise ValueError("No off sample after longest sustained heater-on segment")
    return start_i, end_exclusive


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-zips", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="dgig_weber_r2e_") as td:
        extract_root = Path(td)
        extract_source_zips(args.source_zips, extract_root)
        measurement_files = sorted(extract_root.rglob("MeasurementData.CSV"), key=test_number)
        if len(measurement_files) != 9:
            raise RuntimeError(f"Expected 9 MeasurementData.CSV files, found {len(measurement_files)}")

        provenance = verify_source_files(measurement_files)
        provenance.to_csv(args.output / "source_file_provenance.csv", index=False)
        if not (provenance["hash_match"].all() and provenance["row_match"].all()):
            raise RuntimeError("Source hash/row verification failed")

        primary_rows = []
        stable_rows = []
        similarity_rows = []
        source_rows = []
        ols_rows = []
        action_sensitivity_rows = []
        ancillary_rows = []
        exploratory_rows = []

        cached: dict[int, tuple[pd.DataFrame, int, int]] = {}
        for p in measurement_files:
            run = test_number(p)
            df = load_measurement(p)
            start_i, action_i = reconstruct_action(df)
            cached[run] = (df, start_i, action_i)
            t = df["Time since Start [min]"].to_numpy(float)
            action_t = float(t[action_i])
            heating_duration = action_t - float(t[start_i])

            if run in PRIMARY_RUNS:
                source_y = df[SOURCE_SENSOR].to_numpy(float)
                source_first = first_crossing(t, source_y, start_i, action_i)
                source_stable = stable_crossing(t, source_y, start_i, action_i)
                source_grad_action = finite_gradient(t, source_y, action_t)
                source_down, source_up = crossings(t, source_y, start_i, action_i)
                source_rows.append({
                    "run": run,
                    "heater_start_min": t[start_i],
                    "recorded_commanded_shutoff_min": action_t,
                    "heating_duration_min": heating_duration,
                    "source_first_crossing_after_heater_on_min": source_first - t[start_i],
                    "source_first_lag_to_action_s": (action_t - source_first) * 60.0,
                    "source_stable_lag_to_action_s": (action_t - source_stable) * 60.0,
                    "source_gradient_at_action_K_per_min": source_grad_action,
                    "source_upward_recrossings": len(source_up),
                })

                # Heater-control command reconstruction sensitivity.
                for thr in np.linspace(4.01, 6.0, 200):
                    s2, a2 = reconstruct_action(df, float(thr))
                    action_sensitivity_rows.append({
                        "run": run,
                        "heater_on_threshold_mA": float(thr),
                        "same_start_sample": s2 == start_i,
                        "same_shutoff_sample": a2 == action_i,
                        "shutoff_time_min": float(t[a2]),
                    })

                # Source OLS diagnostic.
                source_ols = rolling_ols_slope(t, source_y, start_i, action_i)
                source_ols_cross = series_crossing(t, source_ols, start_i, action_i)
                ols_rows.append({
                    "run": run,
                    "sensor": SOURCE_SENSOR,
                    "radius_mm": 95,
                    "ols_crossing_min": source_ols_cross,
                    "ols_lead_vs_action_min": (action_t - source_ols_cross) if source_ols_cross is not None else np.nan,
                    "ols_slope_at_action_K_per_min": source_ols[action_i],
                    "crossed_before_action": source_ols_cross is not None and source_ols_cross < action_t,
                })

                for sensor in CANDIDATES:
                    y = df[sensor].to_numpy(float)
                    if not clean_channel(y, start_i, action_i):
                        raise RuntimeError(f"Primary channel invalid in run {run}: {sensor}")
                    c_first = first_crossing(t, y, start_i, action_i)
                    c_stable = stable_crossing(t, y, start_i, action_i)
                    downs, ups = crossings(t, y, start_i, action_i)
                    if c_first is None or c_stable is None:
                        raise RuntimeError(f"Primary candidate failed to cross: run {run}, {sensor}")
                    temp_deficit = interp_at(t, source_y, action_t) - interp_at(t, source_y, c_first)
                    src_grad_at_cand = finite_gradient(t, source_y, c_first)
                    lead_ref = source_first - c_first
                    lead_action = action_t - c_first
                    primary_rows.append({
                        "run": run,
                        "sensor": sensor,
                        "radius_mm": RADII_MM[sensor],
                        "candidate_first_crossing_after_heater_on_min": c_first - t[start_i],
                        "lead_vs_reference_min": lead_ref,
                        "lead_vs_action_min": lead_action,
                        "lead_fraction_of_heating_duration": lead_action / heating_duration,
                        "reference_temperature_deficit_C": temp_deficit,
                        "reference_gradient_at_candidate_trigger_K_per_min": src_grad_at_cand,
                        "candidate_trigger_before_reference": c_first < source_first,
                        "candidate_trigger_before_action": c_first < action_t,
                    })
                    stable_rows.append({
                        "run": run,
                        "sensor": sensor,
                        "radius_mm": RADII_MM[sensor],
                        "first_lead_vs_action_min": lead_action,
                        "stable_crossing_after_heater_on_min": c_stable - t[start_i],
                        "stable_lead_vs_action_min": action_t - c_stable,
                        "upward_recrossings_after_first": len(ups),
                    })

                    ref = source_y[start_i:action_i + 1]
                    cand = y[start_i:action_i + 1]
                    mask = np.isfinite(ref) & np.isfinite(cand)
                    rho = float(spearmanr(ref[mask], cand[mask]).statistic)
                    mae = float(np.mean(np.abs(cand[mask] - ref[mask])))
                    nmae = mae / float(np.max(ref[mask]) - np.min(ref[mask]))
                    similarity_rows.append({
                        "run": run,
                        "sensor": sensor,
                        "radius_mm": RADII_MM[sensor],
                        "spearman_rho": rho,
                        "mae_C": mae,
                        "nmae": nmae,
                    })

                    ols = rolling_ols_slope(t, y, start_i, action_i)
                    ols_cross = series_crossing(t, ols, start_i, action_i)
                    ols_rows.append({
                        "run": run,
                        "sensor": sensor,
                        "radius_mm": RADII_MM[sensor],
                        "ols_crossing_min": ols_cross,
                        "ols_lead_vs_action_min": (action_t - ols_cross) if ols_cross is not None else np.nan,
                        "ols_slope_at_action_K_per_min": ols[action_i],
                        "crossed_before_action": ols_cross is not None and ols_cross < action_t,
                    })

                # Exploratory in-bed lane.
                inbed = [c for c in df.columns if re.match(r"TR40[1-4]-", c)]
                for sensor in inbed:
                    y = df[sensor].to_numpy(float)
                    clean = clean_channel(y, start_i, action_i)
                    c_first = first_crossing(t, y, start_i, action_i) if clean else None
                    exploratory_rows.append({
                        "run": run,
                        "sensor": sensor,
                        "clean_through_heating": clean,
                        "triggered_before_action": bool(c_first is not None and c_first < action_t),
                        "lead_vs_reference_min": (source_first - c_first) if c_first is not None else np.nan,
                        "lead_vs_action_min": (action_t - c_first) if c_first is not None else np.nan,
                    })

            if run in ANCILLARY_RUNS:
                source_y = df[SOURCE_SENSOR].to_numpy(float)
                source_first = first_crossing(t, source_y, start_i, action_i)
                for sensor in CANDIDATES:
                    y = df[sensor].to_numpy(float)
                    c_first = first_crossing(t, y, start_i, action_i)
                    ancillary_rows.append({
                        "run": run,
                        "sensor": sensor,
                        "radius_mm": RADII_MM[sensor],
                        "lead_vs_reference_min": source_first - c_first,
                    })

        primary = pd.DataFrame(primary_rows).sort_values(["run", "radius_mm"])
        stable = pd.DataFrame(stable_rows).sort_values(["run", "radius_mm"])
        similarity = pd.DataFrame(similarity_rows).sort_values(["run", "radius_mm"])
        source_ref = pd.DataFrame(source_rows).sort_values("run")
        ols = pd.DataFrame(ols_rows).sort_values(["run", "radius_mm"])
        action_sens = pd.DataFrame(action_sensitivity_rows).sort_values(["run", "heater_on_threshold_mA"])
        ancillary = pd.DataFrame(ancillary_rows).sort_values(["run", "radius_mm"])
        exploratory = pd.DataFrame(exploratory_rows).sort_values(["run", "sensor"])

        primary.to_csv(args.output / "primary_same_level_results.csv", index=False)
        stable.to_csv(args.output / "stable_crossing_results.csv", index=False)
        similarity.to_csv(args.output / "trajectory_similarity.csv", index=False)
        source_ref.to_csv(args.output / "source_rule_reconstruction.csv", index=False)
        ols.to_csv(args.output / "ols_sensitivity.csv", index=False)
        action_sens.to_csv(args.output / "heater_command_threshold_sensitivity.csv", index=False)
        ancillary.to_csv(args.output / "ancillary_fixed_duration_results.csv", index=False)
        exploratory.to_csv(args.output / "exploratory_all_inbed_results.csv", index=False)

        # Scientific summaries used in R2E text and QA.
        r80p = primary[primary.sensor == "TR404-085d"].copy()
        r80s = stable[stable.sensor == "TR404-085d"].copy()
        r80sim = similarity[similarity.sensor == "TR404-085d"].copy()
        all_stable_candidates = stable.groupby("sensor").agg(
            stable_min=("stable_lead_vs_action_min", "min"),
            stable_max=("stable_lead_vs_action_min", "max"),
            stable_median=("stable_lead_vs_action_min", "median"),
            upward_recrossings=("upward_recrossings_after_first", "sum"),
            max_recrossings_per_run=("upward_recrossings_after_first", "max"),
        ).reset_index()
        all_stable_candidates.to_csv(args.output / "stable_crossing_sensor_summary.csv", index=False)

        candidate_summary = primary.groupby(["sensor", "radius_mm"]).agg(
            median_first_lead_vs_action_min=("lead_vs_action_min", "median"),
            min_first_lead_vs_action_min=("lead_vs_action_min", "min"),
            max_first_lead_vs_action_min=("lead_vs_action_min", "max"),
            median_source_temperature_deficit_C=("reference_temperature_deficit_C", "median"),
        ).reset_index().merge(
            similarity.groupby(["sensor", "radius_mm"]).agg(
                spearman_min=("spearman_rho", "min"),
                spearman_max=("spearman_rho", "max"),
                median_nmae=("nmae", "median"),
                median_mae_C=("mae_C", "median"),
            ).reset_index(), on=["sensor", "radius_mm"]
        ).merge(all_stable_candidates, on="sensor")
        candidate_summary.to_csv(args.output / "same_level_sensor_summary.csv", index=False)

        exploratory_summary = exploratory.groupby("sensor").agg(
            clean_runs=("clean_through_heating", "sum"),
            triggered_before_action=("triggered_before_action", "sum"),
        ).reset_index()
        med = exploratory[exploratory.triggered_before_action].groupby("sensor")["lead_vs_reference_min"].median().rename("median_lead_vs_reference_when_triggered_min")
        exploratory_summary = exploratory_summary.merge(med, on="sensor", how="left")
        exploratory_summary.to_csv(args.output / "exploratory_all_inbed_summary.csv", index=False)

        summary = {
            "scientific_baseline": "R2C locked; R2E is a presentation-focused revision with one direct normalization of locked timing values",
            "source_hash_matches": int(provenance.hash_match.sum()),
            "source_row_matches": int(provenance.row_match.sum()),
            "primary_candidate_run_count": int(len(primary)),
            "primary_first_crossings_early_vs_action": int(primary.candidate_trigger_before_action.sum()),
            "primary_first_crossings_early_vs_reference": int(primary.candidate_trigger_before_reference.sum()),
            "nearest_first_lead_vs_action_min": [float(r80p.lead_vs_action_min.min()), float(r80p.lead_vs_action_min.max())],
            "nearest_first_lead_vs_action_median_min": float(r80p.lead_vs_action_min.median()),
            "nearest_first_lead_fraction_of_heating_duration": [float(r80p.lead_fraction_of_heating_duration.min()), float(r80p.lead_fraction_of_heating_duration.max())],
            "nearest_first_lead_fraction_median": float(r80p.lead_fraction_of_heating_duration.median()),
            "nearest_stable_lead_vs_action_min": [float(r80s.stable_lead_vs_action_min.min()), float(r80s.stable_lead_vs_action_min.max())],
            "nearest_stable_lead_vs_action_median_min": float(r80s.stable_lead_vs_action_min.median()),
            "nearest_spearman": [float(r80sim.spearman_rho.min()), float(r80sim.spearman_rho.max())],
            "nearest_nmae": [float(r80sim.nmae.min()), float(r80sim.nmae.max())],
            "nearest_median_mae_C": float(r80sim.mae_C.median()),
            "nearest_source_temperature_deficit_C": [float(r80p.reference_temperature_deficit_C.min()), float(r80p.reference_temperature_deficit_C.max())],
            "nearest_source_gradient_at_trigger_K_per_min": [float(r80p.reference_gradient_at_candidate_trigger_K_per_min.min()), float(r80p.reference_gradient_at_candidate_trigger_K_per_min.max())],
            "candidate_upward_recrossings_total": int(stable.upward_recrossings_after_first.sum()),
            "max_candidate_recrossings_one_run": int(stable.upward_recrossings_after_first.max()),
            "source_first_lag_to_action_s": [float(source_ref.source_first_lag_to_action_s.min()), float(source_ref.source_first_lag_to_action_s.max())],
            "source_stable_lag_to_action_s": [float(source_ref.source_stable_lag_to_action_s.min()), float(source_ref.source_stable_lag_to_action_s.max())],
            "heater_threshold_sensitivity_all_same_shutoff": bool(action_sens.same_shutoff_sample.all()),
            "nearest_ols_lead_vs_action_min": [
                float(ols[(ols.sensor == "TR404-085d")].ols_lead_vs_action_min.min()),
                float(ols[(ols.sensor == "TR404-085d")].ols_lead_vs_action_min.max()),
            ],
        }
        (args.output / "r2e_scientific_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

        # Fail-closed headline assertions against the locked manuscript ranges.
        checks = [
            ("9/9 source SHA-256 match", summary["source_hash_matches"] == 9),
            ("9/9 source row counts match", summary["source_row_matches"] == 9),
            ("24 primary candidate/run rows", summary["primary_candidate_run_count"] == 24),
            ("24/24 first crossings early vs action", summary["primary_first_crossings_early_vs_action"] == 24),
            ("24/24 first crossings early vs source", summary["primary_first_crossings_early_vs_reference"] == 24),
            ("r80 first lead min 23.587", abs(summary["nearest_first_lead_vs_action_min"][0] - 23.5870378894) < 2e-4),
            ("r80 first lead max 31.119", abs(summary["nearest_first_lead_vs_action_min"][1] - 31.1188338717) < 2e-4),
            ("r80 stable lead min 23.106", abs(summary["nearest_stable_lead_vs_action_min"][0] - 23.1060145767) < 2e-4),
            ("r80 stable lead max 30.401", abs(summary["nearest_stable_lead_vs_action_min"][1] - 30.4012960026) < 2e-4),
            ("r80 Spearman min 0.99988", abs(summary["nearest_spearman"][0] - 0.9998824934) < 2e-9),
            ("r80 Spearman max 0.99999", abs(summary["nearest_spearman"][1] - 0.9999896807) < 2e-9),
            ("r80 NMAE min 0.13586", abs(summary["nearest_nmae"][0] - 0.1358608857) < 2e-8),
            ("r80 NMAE max 0.15457", abs(summary["nearest_nmae"][1] - 0.1545698523) < 2e-8),
            ("r80 source deficit min 26.291 C", abs(summary["nearest_source_temperature_deficit_C"][0] - 26.2907259) < 2e-4),
            ("r80 source deficit max 34.901 C", abs(summary["nearest_source_temperature_deficit_C"][1] - 34.9011483) < 2e-4),
            ("r80 source gradient min 1.6197", abs(summary["nearest_source_gradient_at_trigger_K_per_min"][0] - 1.6197404101) < 2e-5),
            ("r80 source gradient max 1.7706", abs(summary["nearest_source_gradient_at_trigger_K_per_min"][1] - 1.7706009692) < 2e-5),
            ("47 upward recrossings", summary["candidate_upward_recrossings_total"] == 47),
            ("max 10 recrossings one candidate/run", summary["max_candidate_recrossings_one_run"] == 10),
            ("heater command threshold sensitivity unchanged", summary["heater_threshold_sensitivity_all_same_shutoff"]),
            ("source first/action maximum lag about 162.1 s", abs(summary["source_first_lag_to_action_s"][1] - 162.10031697) < 2e-3),
            ("source stable/action maximum lag about 86.5 s", abs(summary["source_stable_lag_to_action_s"][1] - 86.49543727) < 2e-3),
            ("r80 OLS lead min about 23.2 min", 23.15 < summary["nearest_ols_lead_vs_action_min"][0] < 23.25),
            ("r80 OLS lead max about 31.9 min", 31.84 < summary["nearest_ols_lead_vs_action_min"][1] < 31.95),
        ]
        check_df = pd.DataFrame([{"check": name, "pass": bool(ok)} for name, ok in checks])
        check_df.to_csv(args.output / "r2e_reproduction_assertions.csv", index=False)
        if not check_df["pass"].all():
            failed = check_df.loc[~check_df["pass"], "check"].tolist()
            raise RuntimeError("R2E reproduction assertions failed: " + "; ".join(failed))

        # A compact Test-4 trace for the main figure / graphical abstract.
        df4, s4, a4 = cached[4]
        t4 = df4["Time since Start [min]"].to_numpy(float)
        trace = pd.DataFrame({
            "time_after_heater_on_min": t4[s4:a4 + 1] - t4[s4],
            SOURCE_SENSOR: df4[SOURCE_SENSOR].to_numpy(float)[s4:a4 + 1],
            "TR404-085d": df4["TR404-085d"].to_numpy(float)[s4:a4 + 1],
        })
        trace.to_csv(args.output / "test4_nearest_candidate_trace.csv", index=False)

        print(json.dumps(summary, indent=2))
        print(f"PASS: {len(checks)}/{len(checks)} R2E reproduction assertions")


if __name__ == "__main__":
    main()
