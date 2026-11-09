#!/usr/bin/env python3
"""Configuration-blocked, low-capacity follow-up; never modifies frozen work.

First run --self-test (synthetic data only). Real work has two separate commands:
  --prepare --protocol-sha256 SHA
  --evaluate --protocol-sha256 SHA --selection-sha256 SHA
Prepare verifies all raw inputs/boundaries but fits ONLY Tests 4,6,7,8. It writes
both maps and their training-loss selection before evaluation is possible. The
caller must independently inspect/freeze that selection's SHA before --evaluate.
Existing stage directories are never overwritten. No D50 outcome selects a map.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import platform
import sys
import zipfile

sys.dont_write_bytecode = True
import numpy as np
import pandas as pd
import scipy
from scipy.optimize import lsq_linear

HERE = Path(__file__).resolve().parent
WORK = HERE.parents[1]
REPO_ROOT = HERE.parents[2]
REPRO = WORK / "R2E_REPRO_CLEAN_20260920"
CANON = REPRO / "scripts/reproduce_weber_operational.py"
HELPER = WORK / "SCIENTIFIC_ADVANCE_20260927/MONOTONE_STATIC_CORRECTION/run_monotone_static.py"
PROTOCOL = HERE / "PROTOCOL.md"
TRAIN_RUNS = (4, 6, 7, 8)
TEST_RUNS = (5, 9)
ALL_RUNS = (4, 5, 6, 7, 8, 9)
K_VALUES = (5, 7)
SENSOR = "TR404-085d"
SOLVER_TOL = 1e-12
KKT_LIMIT = 1e-7
TIE_REL = 1e-10


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    return sha_bytes(Path(path).read_bytes())


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def dump_json(path, value):
    # Mode x is intentional: these records are immutable after creation.
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def write_csv(path, frame):
    with Path(path).open("x", encoding="utf-8", newline="") as handle:
        frame.to_csv(handle, index=False, float_format="%.17g")


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def code_hashes():
    return {"script_sha256": sha_file(__file__), "canonical_script_sha256": sha_file(CANON),
            "monotone_support_helper_sha256": sha_file(HELPER), "protocol_sha256": sha_file(PROTOCOL)}


def environment():
    return dict(python=sys.version, numpy=np.__version__, pandas=pd.__version__,
                scipy=scipy.__version__, platform=platform.platform())


def verify_protocol(expected):
    require(expected and len(expected) == 64, "Supply the independently frozen protocol SHA-256.")
    actual = sha_file(PROTOCOL)
    require(actual == expected.lower(), "Protocol differs from supplied frozen SHA-256; STOP.")
    return actual


def stage_directory(output, stage):
    output = output.resolve()
    require(output.is_relative_to(HERE) and output != HERE,
            "Outputs must be in a distinct descendant directory of this new experiment only.")
    destination = output / stage
    destination.mkdir(parents=True, exist_ok=False)
    return destination


def load_sources(canon):
    """Admission/boundaries only: deliberately no gradients, crossings or test losses."""
    archives = [REPRO / "source_zips" / f"DGIG_WEBER_CORE_PRIMARY_{suffix}.zip"
                for suffix in ("A_tests4_6", "B_tests7_9")]
    records, provenance = {}, []
    archive_hashes = {}
    for archive in archives:
        require(archive.is_file(), f"Missing official preserved source archive: {archive}")
        archive_hashes[archive.name] = sha_file(archive)
        with zipfile.ZipFile(archive) as zf:
            for member in sorted(zf.namelist()):
                if not member.endswith("MeasurementData.CSV"):
                    continue
                run = canon.test_number(Path(member))
                require(run in ALL_RUNS and run not in records, "Unexpected/duplicate native run.")
                raw = zf.read(member)
                expected_rows, expected_hash = canon.EXPECTED_SOURCE[run]
                require(sha_bytes(raw) == expected_hash, f"Native SHA mismatch: Test {run}")
                frame = canon.load_measurement(io.BytesIO(raw))
                require(len(frame) == expected_rows, f"Native row mismatch: Test {run}")
                start, action = canon.reconstruct_action(frame)
                all_t = frame["Time since Start [min]"].to_numpy(float)
                command = frame["Heater_AO"].to_numpy(float)
                t = all_t[start:action].copy()
                x = frame[SENSOR].to_numpy(float)[start:action].copy()
                y = frame[canon.SOURCE_SENSOR].to_numpy(float)[start:action].copy()
                require(len(t) > 1 and np.isfinite(t).all() and np.all(np.diff(t) > 0),
                        f"Invalid pre-action time: Test {run}")
                require(np.isfinite([x, y]).all() and np.min([x, y]) >= 0 and np.max([x, y]) <= 550,
                        f"Temperature admission failure: Test {run}")
                require(np.isfinite(all_t[action]) and t[-1] < all_t[action], "Invalid strict horizon.")
                require(np.isfinite(command[start:action + 1]).all(), "Nonfinite command boundary.")
                require(np.all(command[start:action] > canon.HEATER_ON_THRESHOLD_MA)
                        and command[action] <= canon.HEATER_ON_THRESHOLD_MA, "Invalid command boundary.")
                require(t[-1] >= t[0] + 15, "Insufficient recorded horizon for fixed operator.")
                records[run] = dict(run=run, t=t, x=x, y=y, start=float(t[0]), horizon=float(t[-1]),
                                    action=float(all_t[action]), start_index=start, action_index=action)
                provenance.append(dict(run=run, archive=archive.name, archive_sha256=archive_hashes[archive.name],
                                       source_member=member, rows=expected_rows, sha256=sha_bytes(raw),
                                       hash_and_rows_match=True, heater_start_index=start, first_off_index=action,
                                       strict_preaction_samples=len(t), heater_start_min=float(t[0]),
                                       observation_horizon_min=float(t[-1]), recorded_action_min=float(all_t[action]),
                                       temperature_admission_pass=True, boundary_pass=True))
    require(tuple(sorted(records)) == ALL_RUNS, "Exactly all six primary runs must be verified.")
    return records, pd.DataFrame(provenance).sort_values("run"), archive_hashes


def weighted_quantile_knots(x, w, requested_k):
    require(requested_k in K_VALUES, "Only prespecified K=5 and K=7 are allowed.")
    unique, inverse = np.unique(x, return_inverse=True)
    weights = np.bincount(inverse, weights=w)
    cumulative = np.cumsum(weights) / np.sum(weights)
    cumulative[-1] = 1.0
    qs = np.arange(1, requested_k - 1, dtype=float) / (requested_k - 1)
    inner = unique[np.searchsorted(cumulative, qs, side="left")]
    knots = np.unique(np.r_[unique[0], inner, unique[-1]])
    require(len(knots) >= 2, "Blocked fit: fewer than two distinct weighted quantile knots.")
    return knots


def hat_design(x, knots):
    """Endpoint clamping and ordinary linear interpolation, no polynomial extrapolation."""
    require(len(knots) >= 2 and np.all(np.diff(knots) > 0), "Invalid knots.")
    clipped = np.clip(np.asarray(x, dtype=float), knots[0], knots[-1])
    left = np.clip(np.searchsorted(knots, clipped, side="right") - 1, 0, len(knots) - 2)
    fraction = (clipped - knots[left]) / (knots[left + 1] - knots[left])
    design = np.zeros((len(clipped), len(knots)))
    rows = np.arange(len(clipped))
    design[rows, left] = 1 - fraction
    design[rows, left + 1] = fraction
    require(np.allclose(design.sum(axis=1), 1, rtol=0, atol=1e-14), "Invalid interpolation basis.")
    return design


def bounded_fit(x, y, w, knots):
    hat = hat_design(x, knots)
    cumulative = np.tril(np.ones((len(knots), len(knots))))
    design = hat @ cumulative
    weighted_a, weighted_b = np.sqrt(w)[:, None] * design, np.sqrt(w) * y
    singular_values = np.linalg.svd(weighted_a, compute_uv=False)
    rank = int(np.linalg.matrix_rank(weighted_a))
    rank_tolerance = float(max(weighted_a.shape) * np.finfo(weighted_a.dtype).eps * singular_values[0])
    require(rank == len(knots), "Blocked fit: rank-deficient weighted design.")
    lower = np.r_[-np.inf, np.zeros(len(knots) - 1)]
    result = lsq_linear(weighted_a, weighted_b, bounds=(lower, np.full(len(knots), np.inf)),
                        method="bvls", tol=SOLVER_TOL, max_iter=10000)
    z = result.x
    grad = weighted_a.T @ (weighted_a @ z - weighted_b)  # objective = half weighted MSE
    active = np.r_[False, z[1:] == 0]
    dual_residual = np.where(active, np.maximum(0, -grad), np.abs(grad))
    primal_residual = max(0., float(-np.min(z[1:])))
    complementarity = float(np.max(np.abs(z[1:] * grad[1:])))
    kkt_residual = float(np.max(np.abs(z - np.clip(z - grad, lower, np.inf))))
    require(result.success and result.status > 0, f"Blocked fit: BVLS failed: {result.message}")
    require(np.isfinite(z).all() and np.min(z[1:]) >= -1e-12 and kkt_residual <= KKT_LIMIT,
            f"Blocked fit: KKT residual {kkt_residual:.8g} exceeds {KKT_LIMIT}.")
    heights = cumulative @ z
    require(np.all(np.diff(heights) >= 0), "Blocked fit: nonmonotone output heights.")
    mse = float(np.sum(w * (hat @ heights - y) ** 2))
    fit_record = dict(solver="scipy.optimize.lsq_linear", method="dense BVLS", tol=SOLVER_TOL,
                      max_iter=10000, success=bool(result.success), status=int(result.status),
                      message=str(result.message), iterations=int(result.nit), rank=rank,
                      rank_svd_tolerance=rank_tolerance,
                      singular_values=singular_values.tolist(), optimality=float(result.optimality),
                      half_weighted_mse_cost=float(result.cost), equal_run_training_mse_C2=mse,
                      increments_with_unrestricted_intercept=z.tolist(), objective_gradient=grad.tolist(),
                      solver_active_mask=result.active_mask.tolist(), kkt_residual=kkt_residual,
                      kkt_stationarity_or_dual_residual=float(dual_residual.max()),
                      kkt_primal_residual=primal_residual, kkt_complementarity_residual=complementarity,
                      kkt_definition="max(abs(theta-clip(theta-gradient,lower,upper))); half-MSE objective",
                      minimum_height_increment_C=float(np.diff(heights).min()))
    return dict(x=knots, y=heights), fit_record


def choose_primary(losses):
    a, b = losses[5], losses[7]
    tied = abs(a - b) <= TIE_REL * max(1., a, b)
    return (5 if tied or a < b else 7), tied


def tiny_checks():
    x = np.array([0., 1., 2.])
    model, record = bounded_fit(x, np.array([2., 0., 4.]), np.ones(3) / 3, x)
    require(np.allclose(model["y"], [1, 1, 4], rtol=0, atol=1e-12), "Analytic constrained solution mismatch.")
    probe = np.array([-1., .5, 1.5, 3.])
    require(np.allclose(hat_design(probe, x) @ model["y"], [1, 1, 2.5, 4], rtol=0, atol=1e-12),
            "Interpolation/clamping tiny check failed.")
    q = weighted_quantile_knots(np.array([0., 0., 1., 2., 3.]), np.array([.125, .125, .25, .25, .25]), 5)
    require(np.array_equal(q, [0, 1, 2, 3]), "Empirical quantile duplicate/endpoints check failed.")
    require(choose_primary({5: 10., 7: 10. - 1e-10}) == (5, True), "Tie preference check failed.")
    require(choose_primary({5: 10., 7: 9.}) == (7, False), "Training loss selection check failed.")
    canon = load_module(CANON, "blocked_tiny_canonical")
    helper = load_module(HELPER, "blocked_tiny_support")
    require(helper.first_crossing(np.array([0., 1., 2.]), np.array([.9, .8, .7])) == (None, None),
            "Initially below threshold must not count as a crossing.")
    event, bracket = helper.first_crossing(np.array([0., 1., 2.]), np.array([2., 1., 0.]))
    require(event == 1. and bracket == 1, "Threshold crossing interpolation check failed.")
    t = np.arange(20., dtype=float)
    idx, grad = canon.gradient_series(t, 2 * t + 5, 0, len(t) - 1)
    require(np.array_equal(idx, np.arange(15, 20)) and np.all(grad == 2), "15-minute operator check failed.")
    t = np.arange(41., dtype=float)
    y = 2 * np.minimum(t, 20.)
    x = y + 2 * np.maximum(t - 30., 0.)
    synthetic = enrich_for_scoring(dict(run=0, t=t, x=x, y=y, start=0., horizon=40., action=41.), canon, helper)
    simple_model = dict(x=np.array([0., 100.]), y=np.array([0., 100.]))
    row, _ = score(synthetic, simple_model, "identity", canon, helper)
    require(row["crossing_min"] == 27.5 and row["upward_recrossings_after_first"] == 1
            and row["upward_recrossing_times_min"] == "[37.5]"
            and row["stays_below_through_recorded_horizon"] is False
            and row["supported_one_sided_5_min_success"] is True,
            "Synthetic first-event/recrossing/support distinction failed.")
    excluded_history_model = dict(x=np.array([1., 100.]), y=np.array([1., 100.]))
    support = helper.event_support(synthetic, excluded_history_model, 27.5, 12)
    require(support["first_event_search_history_in_support"] is False
            and support["event_computation_inputs_all_in_support"] is True,
            "Synthetic full-search versus event-local support distinction failed.")
    return dict(passed=True, synthetic_only=True, real_sources_loaded=False,
                analytic_constrained_fit=True, kkt_residual=record["kkt_residual"],
                quantiles_duplicates_and_clamping=True, training_selection_tie=True,
                first_crossing_and_gradient=True, recrossing_and_full_search_support=True)


def prepare(output, frozen_protocol_sha):
    verify_protocol(frozen_protocol_sha)
    checks = tiny_checks()
    destination = stage_directory(output, "prepared")
    try:
        canon = load_module(CANON, "blocked_prepare_canonical")
        runs, provenance, archives = load_sources(canon)
        training = [runs[r] for r in TRAIN_RUNS]
        x = np.concatenate([r["x"] for r in training])
        y = np.concatenate([r["y"] for r in training])
        w = np.concatenate([np.full(len(r["x"]), 1 / (4 * len(r["x"]))) for r in training])
        require(abs(w.sum() - 1) < 1e-12, "Training weights do not sum to one.")
        write_csv(destination / "source_provenance.csv", provenance)
        write_csv(destination / "training_run_weights.csv", pd.DataFrame([
            dict(training_run=r["run"], samples=len(r["x"]), sample_weight=1 / (4 * len(r["x"])),
                 total_run_weight=.25) for r in training]))
        write_csv(destination / "training_pairs_and_weights.csv", pd.concat([
            pd.DataFrame(dict(training_run=r["run"], time_min=r["t"], candidate_C=r["x"], source_C=r["y"],
                              weight=1 / (4 * len(r["x"])))) for r in training], ignore_index=True))
        losses, model_records = {}, []
        for k in K_VALUES:
            knots = weighted_quantile_knots(x, w, k)
            model, fit = bounded_fit(x, y, w, knots)
            fit.update(requested_k=k, effective_k=len(knots), reduced_knot_count=len(knots) < k,
                       training_runs=list(TRAIN_RUNS), held_out_runs=list(TEST_RUNS),
                       held_out_used_in_fit_or_knots=False)
            map_name, fit_name = f"K{k}_knots.csv", f"K{k}_fit_record.json"
            write_csv(destination / map_name, pd.DataFrame(dict(candidate_knot_C=model["x"], fitted_source_C=model["y"])))
            dump_json(destination / fit_name, fit)
            losses[k] = fit["equal_run_training_mse_C2"]
            model_records.append(dict(requested_k=k, effective_k=len(knots), equal_run_training_mse_C2=losses[k],
                                      model_file=map_name, model_sha256=sha_file(destination / map_name),
                                      fit_record_file=fit_name, fit_record_sha256=sha_file(destination / fit_name)))
        selected, tied = choose_primary(losses)
        payload = {p.name: sha_file(p) for p in sorted(destination.iterdir()) if p.is_file()}
        selection = dict(stage="training_selection_frozen_before_D50_evaluation", created_utc=utc_now(),
                         **code_hashes(), environment=environment(), source_archive_sha256=archives,
                         training_runs=list(TRAIN_RUNS), held_out_runs=list(TEST_RUNS), models=model_records,
                         primary_requested_k=selected, selection_rule="minimum equal-run training MSE; K5 on tie",
                         tie_relative_threshold=TIE_REL, tied=tied, payload_sha256=payload, tiny_checks=checks,
                         D50_outcomes_computed=False, test_values_used_for_model_or_selection=False,
                         campaign_previously_explored=True, prospective_preregistration=False,
                         external_validation=False)
        dump_json(destination / "selection_record.json", selection)
        print("PREPARE COMPLETE. No held-out outcome was computed.")
        print("Selection SHA-256:", sha_file(destination / "selection_record.json"))
        print("Independently freeze/check this record before issuing the separate --evaluate command.")
    except Exception as error:
        dump_json(destination / "BLOCKED.json", dict(stage="prepare", utc=utc_now(), error=str(error),
                                                     held_out_evaluation_performed=False, **code_hashes()))
        raise


def enrich_for_scoring(test, canon, helper):
    result = dict(test)
    idx, g = canon.gradient_series(test["t"], test["y"], 0, len(test["t"]) - 1)
    require(len(g) >= 2, "Fewer than two eligible gradients; source event cannot be bracketed.")
    source_event, _ = helper.first_crossing(test["t"][idx], g)
    require(source_event is not None, "Source first event absent in strict horizon; document blocked endpoint.")
    result.update(gradient_idx=idx, tg=test["t"][idx], source_g=g, source_first=source_event)
    return result


def score(test, model, method, canon, helper, primary=False):
    prediction = test["x"].copy() if method == "identity" else np.interp(test["x"], model["x"], model["y"])
    idx, gradient = canon.gradient_series(test["t"], prediction, 0, len(prediction) - 1)
    require(np.array_equal(idx, test["gradient_idx"]), "Gradient timestamps differ.")
    event, bracket = helper.first_crossing(test["tg"], gradient)
    support = helper.event_support(test, model, event, bracket)
    outside = ~helper.within_support(test["x"], model)
    error = None if event is None else float(event - test["source_first"])
    status = ("within_window" if -5 <= error <= 0 else "outside_window") if event is not None else (
        "missed_source_deadline" if test["horizon"] >= test["source_first"] else "unresolved_censored")
    upward = np.flatnonzero((gradient[:-1] < 1) & (gradient[1:] >= 1))
    if event is None:
        recrossings, stable = [], None
    else:
        upward = upward[upward > bracket]
        recrossings = [float(test["tg"][j] + (1 - gradient[j]) * (test["tg"][j + 1] - test["tg"][j]) /
                            (gradient[j + 1] - gradient[j])) for j in upward]
        stable = bool(np.all(gradient[bracket + 1:] < 1))
    residual = prediction - test["y"]
    row = dict(held_out_run=test["run"], method=method, primary_map=primary, n_samples=len(prediction),
               rmse_C=float(np.sqrt(np.mean(residual ** 2))), mae_C=float(np.mean(np.abs(residual))),
               training_support_min_C=float(model["x"][0]), training_support_max_C=float(model["x"][-1]),
               samples_outside_training_support=int(outside.sum()), fraction_outside_training_support=float(outside.mean()),
               full_preaction_trace_in_training_support=bool(not outside.any()),
               source_first_min=test["source_first"], heater_start_min=test["start"],
               observation_horizon_min=test["horizon"], recorded_action_min=test["action"],
               event_status="right_censored" if event is None else "observed", crossing_min=event,
               signed_error_vs_source_min=error, absolute_error_vs_source_min=None if error is None else abs(error),
               lead_vs_recorded_action_min=None if event is None else test["action"] - event,
               one_sided_5_min_status=status,
               supported_one_sided_5_min_success=bool(status == "within_window" and
                   support["first_event_search_history_in_support"] and support["event_computation_inputs_all_in_support"]),
               upward_recrossings_after_first=None if event is None else len(recrossings),
               upward_recrossing_times_min=json.dumps(recrossings),
               stays_below_through_recorded_horizon=stable,
               final_gradient_K_per_min=float(gradient[-1]),
               identity_support_is_only_training_range_diagnostic=method == "identity", **support)
    samples = pd.DataFrame(dict(held_out_run=test["run"], method=method, time_min=test["t"],
                                candidate_C=test["x"], source_C=test["y"], predicted_C=prediction,
                                residual_C=residual, outside_training_support=outside))
    samples["mapped_trailing15_gradient_K_per_min"] = np.nan
    samples.loc[idx, "mapped_trailing15_gradient_K_per_min"] = gradient
    samples["source_trailing15_gradient_K_per_min"] = np.nan
    samples.loc[idx, "source_trailing15_gradient_K_per_min"] = test["source_g"]
    return row, samples


def evaluate(output, frozen_protocol_sha, selection_sha):
    verify_protocol(frozen_protocol_sha)
    prepared = output.resolve() / "prepared"
    selection_path = prepared / "selection_record.json"
    require(selection_sha and sha_file(selection_path) == selection_sha.lower(),
            "Missing/mismatched independently frozen selection SHA-256; no held-out evaluation.")
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    require(selection["stage"] == "training_selection_frozen_before_D50_evaluation", "Wrong selection stage.")
    require(selection["training_runs"] == list(TRAIN_RUNS) and selection["held_out_runs"] == list(TEST_RUNS), "Split changed.")
    require(not selection["D50_outcomes_computed"], "Selection must precede outcome evaluation.")
    for key, value in code_hashes().items():
        require(selection[key] == value, f"Changed code/protocol dependency: {key}")
    for name, expected in selection["payload_sha256"].items():
        require(Path(name).name == name and sha_file(prepared / name) == expected, "Changed prepared artifact.")
    require([item["requested_k"] for item in selection["models"]] == list(K_VALUES), "Missing prespecified map.")
    losses = {item["requested_k"]: item["equal_run_training_mse_C2"] for item in selection["models"]}
    require(choose_primary(losses)[0] == selection["primary_requested_k"], "Invalid frozen primary selection.")
    destination = stage_directory(output, "evaluated")
    try:
        canon = load_module(CANON, "blocked_evaluate_canonical")
        helper = load_module(HELPER, "blocked_evaluate_support")
        runs, provenance, archives = load_sources(canon)
        require(archives == selection["source_archive_sha256"], "Source archive changed since training.")
        models = {}
        for item in selection["models"]:
            table = pd.read_csv(prepared / item["model_file"], float_precision="round_trip")
            models[item["requested_k"]] = dict(x=table.candidate_knot_C.to_numpy(), y=table.fitted_source_C.to_numpy())
        require(models[5]["x"][0] == models[7]["x"][0] and models[5]["x"][-1] == models[7]["x"][-1],
                "Prespecified maps must share the complete training support range.")
        rows, sample_tables = [], []
        for run in TEST_RUNS:
            test = enrich_for_scoring(runs[run], canon, helper)
            identity, samples = score(test, models[5], "identity", canon, helper)
            identity.update(rmse_ratio_vs_identity=1., rmse_reduction_fraction_vs_identity=0., material_50pct_rmse_reduction=False)
            rows.append(identity)
            sample_tables.append(samples)
            require(identity["rmse_C"] > 0, "Identity RMSE zero: prespecified relative criterion undefined.")
            for k in K_VALUES:
                row, samples = score(test, models[k], f"K{k}", canon, helper, k == selection["primary_requested_k"])
                ratio = row["rmse_C"] / identity["rmse_C"]
                row.update(rmse_ratio_vs_identity=ratio, rmse_reduction_fraction_vs_identity=1 - ratio,
                           material_50pct_rmse_reduction=bool(ratio <= .5))
                rows.append(row)
                sample_tables.append(samples)
        primary = [r for r in rows if r["primary_map"]]
        require(len(primary) == 2, "Exactly two D50 primary evaluation units are required.")
        summary = dict(primary_requested_k=selection["primary_requested_k"], run_units=2,
                       both_D50_supported_observed_first_events_inside_one_sided_window=all(
                           r["supported_one_sided_5_min_success"] for r in primary),
                       both_D50_at_least_50pct_RMSE_reduction=all(r["material_50pct_rmse_reduction"] for r in primary),
                       stronger_evidence_composite_pass=all(r["supported_one_sided_5_min_success"] and
                           r["material_50pct_rmse_reduction"] for r in primary),
                       both_D50_recorded_horizon_sustained=all(r["stays_below_through_recorded_horizon"] is True for r in primary),
                       campaign_selected_exploratory_internal_followup=True, external_validation=False,
                       prospective_test=False, recorded_action_is_not_source_event=True,
                       manuscript_integration_requires_separate_independent_review=True)
        write_csv(destination / "held_out_results.csv", pd.DataFrame(rows))
        write_csv(destination / "held_out_samples.csv", pd.concat(sample_tables, ignore_index=True))
        write_csv(destination / "source_provenance.csv", provenance)
        dump_json(destination / "criterion_summary.json", summary)
        payload = {p.name: sha_file(p) for p in sorted(destination.iterdir()) if p.is_file()}
        dump_json(destination / "evaluation_record.json", dict(created_utc=utc_now(), **code_hashes(),
                  environment=environment(), selection_sha256=selection_sha.lower(), selection_unchanged=True,
                  source_archive_sha256=archives, source_hash_and_boundary_checks=6, evaluated_runs=list(TEST_RUNS),
                  fit_performed_during_evaluation=False, payload_sha256=payload, frozen_manuscripts_written=False))
        require(sha_file(selection_path) == selection_sha.lower(), "Selection changed during evaluation.")
        print(json.dumps(summary, indent=2))
        print("Evaluation complete; manuscript remains frozen. Independent numerical review is still required.")
    except Exception as error:
        dump_json(destination / "BLOCKED.json", dict(stage="evaluate", utc=utc_now(), error=str(error), **code_hashes()))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--evaluate", action="store_true")
    parser.add_argument("--output", type=Path, default=HERE / "outputs")
    parser.add_argument("--protocol-sha256")
    parser.add_argument("--selection-sha256")
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(tiny_checks(), indent=2))
    elif args.prepare:
        prepare(args.output, args.protocol_sha256)
    else:
        evaluate(args.output, args.protocol_sha256, args.selection_sha256)


if __name__ == "__main__":
    main()
