#!/usr/bin/env python3
"""Independent raw-source audit of the frozen configuration-blocked check.

No import from the primary implementation or canonical processing code.  Fit
monotone knot heights by exhaustive contiguous equality-face enumeration,
rather than the primary increment/BVLS optimization.  Real-data execution is
deliberately gated on --run-real; --self-test does not read source data.
"""
from __future__ import annotations

import argparse
import bisect
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import zipfile

sys.dont_write_bytecode = True
import numpy as np

HERE = Path(__file__).resolve().parent
WORK = HERE.parents[1]
SOURCE = WORK / "R2E_REPRO_CLEAN_20260920/source_zips"
TRAIN = (4, 6, 7, 8)
TEST = (5, 9)
EXPECTED_PROTOCOL = "0e39248efe6e627280f7585cebec8ffdac2d545f9a47055a2e8673cf3ef68559"
EXPECTED_SOURCE = {
    4: (14766, "985f4452c04e495c6f07227d3ce238975d596caa5a9ea04f8e52fb08645e1d68"),
    5: (16243, "3318140e2de217cce5c407f862b238385f5872e46a11710ef8fed260cce22425"),
    6: (11069, "cbbf5b9846c2bd0945cebf6517f8a9b003f7d4b5aaf54c1de6bc8dc8de1a629b"),
    7: (15935, "19b88ec506a3e2407ca4bb40adeb8247d2467f4913b0a62de39afede45254a6b"),
    8: (9076, "1cbfdd865524224959a0d28836528c79dc7228e37e725e9e4be7b32f4ea799ef"),
    9: (14058, "050bd98e110121a9063e7c361f8a7cbbedad55fea6eed42c05e2e69a22ccbe2e"),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def plain(value):
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def read_native_runs():
    runs, custody = {}, []
    for path in sorted(SOURCE.glob("DGIG_WEBER_CORE_PRIMARY_*.zip")):
        with zipfile.ZipFile(path) as archive:
            for member in archive.namelist():
                if not member.endswith("/MeasurementData.CSV"):
                    continue
                run = int(Path(member).parent.name.split("_", 1)[0])
                assert run in EXPECTED_SOURCE and run not in runs
                raw = archive.read(member)
                digest = hashlib.sha256(raw).hexdigest()
                assert digest == EXPECTED_SOURCE[run][1]
                parsed = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig")), delimiter=";"))
                assert len(parsed) == EXPECTED_SOURCE[run][0]
                def column(name):
                    return np.array([float(row[name].replace(",", ".")) for row in parsed], float)
                t = column("Time since Start [min]")
                command = column("Heater_AO")
                x, y = column("TR404-085d"), column("TR404-108e")
                # Independent sequential run-length scan: earliest longest tie.
                best_start = best_stop = current_start = 0
                active = False
                for i, value in enumerate(command):
                    if value > 4.5 and not active:
                        current_start, active = i, True
                    if active and not value > 4.5:
                        if i-current_start > best_stop-best_start:
                            best_start, best_stop = current_start, i
                        active = False
                if active and len(command)-current_start > best_stop-best_start:
                    best_start, best_stop = current_start, len(command)
                assert best_stop > best_start and best_stop < len(command)
                trace = dict(run=run, t=t[best_start:best_stop],
                             x=x[best_start:best_stop], y=y[best_start:best_stop],
                             action=float(t[best_stop]), start_index=best_start,
                             action_index=best_stop)
                assert np.isfinite(trace["t"]).all() and np.all(np.diff(trace["t"]) > 0)
                for channel in ("x", "y"):
                    assert np.isfinite(trace[channel]).all()
                    assert np.all((trace[channel] >= 0) & (trace[channel] <= 550))
                assert trace["t"][-1] < trace["action"]
                assert ("D50" in member) == (run in TEST)
                runs[run] = trace
                custody.append(dict(run=run, member=member, rows=len(parsed),
                                    source_sha256=digest, archive=path.name,
                                    archive_sha256=sha(path), start_index=best_start,
                                    action_index=best_stop, preaction_samples=len(trace["t"])))
    assert tuple(sorted(runs)) == (4, 5, 6, 7, 8, 9)
    return runs, custody


def interpolation(value, coordinates, values):
    """Explicit piecewise interpolation with fixed endpoint clamp."""
    if value <= coordinates[0]:
        return float(values[0])
    if value >= coordinates[-1]:
        return float(values[-1])
    right = bisect.bisect_right(coordinates, value)
    left = right-1
    weight = (value-coordinates[left])/(coordinates[right]-coordinates[left])
    return float((1-weight)*values[left]+weight*values[right])


def knot_basis(x, knots):
    basis = np.zeros((len(x), len(knots)), float)
    for row, value in enumerate(x):
        if value <= knots[0]:
            basis[row, 0] = 1
        elif value >= knots[-1]:
            basis[row, -1] = 1
        else:
            right = bisect.bisect_right(knots, value)
            weight = (value-knots[right-1])/(knots[right]-knots[right-1])
            basis[row, right-1], basis[row, right] = 1-weight, weight
    return basis


def empirical_knots(x, weights, nominal):
    unique, inverse = np.unique(x, return_inverse=True)
    mass = np.bincount(inverse, weights=weights)
    cumulative = np.cumsum(mass)/mass.sum()
    cumulative[-1] = 1.0
    knots = [unique[0]]
    for j in range(1, nominal-1):
        knots.append(unique[bisect.bisect_left(cumulative, j/(nominal-1))])
    knots.append(unique[-1])
    result = np.unique(knots)
    assert len(result) >= 2
    return result


def fit_by_all_equality_faces(x, y, weights, knots):
    """Global monotone LS solution by all contiguous equality partitions.

    Every feasible optimum lies in a face joining adjacent equal knot heights;
    on its minimal face the unrestricted reduced least-squares optimum is
    feasible. Exhausting 2**(K-1) faces therefore includes the global optimum.
    """
    basis = knot_basis(x, knots)
    weighted = np.sqrt(weights)[:, None]*basis
    target = np.sqrt(weights)*y
    singular = np.linalg.svd(weighted, compute_uv=False)
    rank_tolerance = max(weighted.shape)*np.finfo(float).eps*singular[0]
    rank = int(np.sum(singular > rank_tolerance))
    assert rank == len(knots)
    best = None
    feasible = 0
    for cuts in range(1 << (len(knots)-1)):
        groups = [0]
        for edge in range(len(knots)-1):
            groups.append(groups[-1]+int(bool(cuts & (1 << edge))))
        reduction = np.zeros((len(knots), groups[-1]+1), float)
        reduction[np.arange(len(knots)), groups] = 1
        reduced = weighted@reduction
        heights, _, reduced_rank, _ = np.linalg.lstsq(reduced, target, rcond=None)
        assert reduced_rank == reduced.shape[1]
        if np.any(np.diff(heights) < -1e-10):
            continue
        feasible += 1
        full = reduction@heights
        loss = float(np.dot(weights, (basis@full-y)**2))
        if best is None or loss < best["loss"]:
            best = dict(y=full, loss=loss, equality_face_mask=cuts,
                        equality_groups=groups, unique_height_groups=len(heights))
    assert best is not None
    best.update(x=knots, rank=rank, rank_tolerance=float(rank_tolerance),
                partitions_examined=1 << (len(knots)-1), feasible_partitions=feasible)
    # Separate optimality diagnostic in increment coordinates, not used to fit.
    cumulative = np.tril(np.ones((len(knots), len(knots))))
    increment_design = weighted@cumulative
    theta = np.r_[best["y"][0], np.diff(best["y"])]
    grad = increment_design.T@(increment_design@theta-target)
    lower = np.r_[-np.inf, np.zeros(len(knots)-1)]
    projected = theta-np.maximum(theta-grad, lower)
    best["projected_kkt_residual"] = float(np.max(np.abs(projected)))
    assert best["projected_kkt_residual"] <= 1e-7
    assert np.min(np.diff(best["y"])) >= -1e-10
    return best


def gradients(t, values):
    """Manual lag interpolation; keep each interpolation sample footprint."""
    indices, values_out, lag_neighbors = [], [], []
    for current, timestamp in enumerate(t):
        if timestamp < t[0]+15:
            continue
        lag = timestamp-15
        left = max(0, bisect.bisect_right(t, lag)-1)
        right = min(left+1, len(t)-1)
        past = interpolation(lag, t, values)
        indices.append(current)
        values_out.append((values[current]-past)/15)
        lag_neighbors.append((left, right))
    assert len(indices) >= 2
    return np.array(indices, int), np.array(values_out, float), lag_neighbors


def transitions(tg, g):
    down, up = [], []
    for previous in range(len(g)-1):
        current = previous+1
        if (g[previous] >= 1 and g[current] < 1) or (g[previous] < 1 and g[current] >= 1):
            crossing = float(tg[previous]+(1-g[previous])*(tg[current]-tg[previous])/(g[current]-g[previous]))
            target = down if g[previous] >= 1 else up
            target.append((crossing, previous, current))
    return down, up


def independent_score(trace, model, nominal):
    t, x, y = trace["t"], trace["x"], trace["y"]
    identity = nominal == 0
    mapped = x.copy() if identity else np.array([interpolation(v, model["x"], model["y"]) for v in x])
    index, g, lag_neighbors = gradients(t, mapped)
    source_index, source_g, _ = gradients(t, y)
    assert np.array_equal(index, source_index)
    source_down, _ = transitions(t[index], source_g)
    assert source_down
    source_event = source_down[0][0]
    downs, ups = transitions(t[index], g)
    event = downs[0][0] if downs else None
    error = event-source_event if event is not None else None
    outside = (x < model["x"][0]) | (x > model["x"][-1])
    # Identity gets the same K5 range diagnostic, not a validity requirement.
    # Contiguous union includes every intervening sample and both lag neighbors.
    search_start = lag_neighbors[0][0]
    search_end = int(index[downs[0][2]]) if downs else len(t)-1
    search_values = x[search_start:search_end+1]
    search_support = not bool(np.any(outside[search_start:search_end+1]))
    full_support = not bool(np.any(outside))
    local = dict(event_15min_window_in_support=None,
                 event_window_candidate_min_C=None, event_window_candidate_max_C=None,
                 event_sample_footprint_min_C=None, event_sample_footprint_max_C=None,
                 event_footprint_start_sample_min=None, event_footprint_end_sample_min=None)
    if downs:
        local_start = lag_neighbors[downs[0][1]][0]
        local_end = int(index[downs[0][2]])
        local_support = not bool(np.any(outside[local_start:local_end+1]))
        footprint = x[local_start:local_end+1]
        nominal_window = [interpolation(event-15, t, x), interpolation(event, t, x)]
        nominal_window.extend(float(x[i]) for i, stamp in enumerate(t) if event-15 <= stamp <= event)
        local.update(event_15min_window_in_support=all(model["x"][0] <= v <= model["x"][-1] for v in nominal_window),
                     event_window_candidate_min_C=min(nominal_window), event_window_candidate_max_C=max(nominal_window),
                     event_sample_footprint_min_C=float(footprint.min()), event_sample_footprint_max_C=float(footprint.max()),
                     event_footprint_start_sample_min=float(t[local_start]), event_footprint_end_sample_min=float(t[local_end]))
    else:
        local_support = None
    window = ("within_window" if -5 <= error <= 0 else "outside_window") if event is not None else (
        "missed_source_deadline" if t[-1] >= source_event else "unresolved_censored")
    rmse = float(np.sqrt(np.mean((mapped-y)**2)))
    identity_rmse = float(np.sqrt(np.mean((x-y)**2)))
    row = dict(run=trace["run"], nominal_knots=nominal, n_samples=len(t),
               method="identity" if identity else "low_capacity_monotone",
               rmse_C=rmse, mae_C=float(np.mean(np.abs(mapped-y))),
               identity_rmse_C=identity_rmse, rmse_ratio_to_identity=rmse/identity_rmse,
               rmse_reduction_fraction=1-rmse/identity_rmse,
               material_improvement_50pct=rmse <= .5*identity_rmse,
               source_first_min=source_event, heater_start_min=float(t[0]),
               observation_horizon_min=float(t[-1]), recorded_action_min=trace["action"],
               event_status="observed" if event is not None else "right_censored",
               crossing_min=event, signed_error_vs_source_min=error,
               absolute_error_vs_source_min=abs(error) if error is not None else None,
               lead_vs_recorded_action_min=trace["action"]-event if event is not None else None,
               training_support_min_C=float(model["x"][0]),
               training_support_max_C=float(model["x"][-1]),
               samples_outside_training_support=int(outside.sum()),
               fraction_outside_training_support=float(outside.mean()),
               first_event_search_history_in_support=search_support,
               event_computation_inputs_all_in_support=local_support,
               entire_preaction_trace_in_support=full_support,
               one_sided_5_min_status=window,
               supported_one_sided_5_min_success=bool(window == "within_window" and search_support and local_support),
               upward_recrossings_after_first=sum(event < crossing for crossing, _, _ in ups) if event is not None else None,
               upward_recrossing_times_min=[crossing for crossing, _, _ in ups if event is not None and crossing > event],
               first_remains_below_through_horizon=bool(np.all(g[downs[0][2]:] < 1)) if downs else None,
               total_observed_downward_crossings=len(downs),
               mapped_gradient_at_horizon_K_per_min=float(g[-1]),
               search_history_start_sample_min=float(t[search_start]),
               search_history_end_sample_min=float(t[search_end]),
               search_history_candidate_min_C=float(search_values.min()),
               search_history_candidate_max_C=float(search_values.max()), **local)
    row["composite_pass"] = None if identity else bool(row["supported_one_sided_5_min_success"] and row["material_improvement_50pct"])
    full_g, full_source_g = np.full(len(t), np.nan), np.full(len(t), np.nan)
    full_g[index], full_source_g[index] = g, source_g
    samples = dict(time_min=t, candidate_C=x, source_C=y, predicted_C=mapped,
                   mapped_trailing15_gradient_K_per_min=full_g,
                   source_trailing15_gradient_K_per_min=full_source_g,
                   residual_C=mapped-y, outside_training_support=outside)
    return row, samples


def self_test():
    knots = np.array([0., 1., 2.])
    fit = fit_by_all_equality_faces(knots, np.array([2., 0., 3.]), np.ones(3)/3, knots)
    assert np.allclose(fit["y"], [1, 1, 3], rtol=0, atol=1e-12)
    assert fit["partitions_examined"] == 4
    assert interpolation(.5, knots, np.array([0., 2., 4.])) == 1
    assert interpolation(-2, knots, np.array([0., 2., 4.])) == 0
    assert interpolation(7, knots, np.array([0., 2., 4.])) == 4
    assert np.array_equal(empirical_knots(np.array([0., 0., 1., 2.]), np.array([.25, .25, .25, .25]), 5), [0, 1, 2])
    t = np.array([0., 5., 10., 15., 20., 25., 30.])
    idx, g, _ = gradients(t, t*2)
    assert np.all(g == 2) and np.array_equal(idx, [3, 4, 5, 6])
    down, up = transitions(np.array([0., 1., 2., 3.]), np.array([.5, 1.5, .5, 1.5]))
    assert down == [(1.5, 1, 2)] and len(up) == 2
    assert not transitions(np.array([0., 1.]), np.array([.5, .4]))[0]
    return dict(analytic_face_optimization=True, interpolation=True,
                duplicate_empirical_quantiles=True, lag_gradient=True,
                armed_first_crossing_and_recrossing=True)


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--run-real", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("outputs"),
                        help="Primary output directory to audit, absolute or relative to this script.")
    args = parser.parse_args()
    tests = self_test()
    if not args.run_real:
        print(json.dumps(dict(self_test=tests, real_data_read=False), indent=2))
        return
    assert sha(HERE/"PROTOCOL.md") == EXPECTED_PROTOCOL
    freeze = json.loads((HERE/"PROTOCOL_FREEZE.json").read_text(encoding="utf-8"))
    assert freeze["protocol_sha256"] == EXPECTED_PROTOCOL
    # No raw outcome computation before the primary fit-selection artifact exists.
    primary_output = args.output if args.output.is_absolute() else HERE/args.output
    primary_output = primary_output.resolve()
    assert primary_output.is_relative_to(HERE) and primary_output != HERE
    selection_file = primary_output/"prepared/selection_record.json"
    assert selection_file.exists(), "Primary frozen selection must exist before real-data audit."
    runs, custody = read_native_runs()
    x = np.concatenate([runs[r]["x"] for r in TRAIN])
    y = np.concatenate([runs[r]["y"] for r in TRAIN])
    weights = np.concatenate([np.full(len(runs[r]["x"]), 1/(len(TRAIN)*len(runs[r]["x"]))) for r in TRAIN])
    assert abs(weights.sum()-1) < 1e-12
    models = {}
    for nominal in (5, 7):
        knots = empirical_knots(x, weights, nominal)
        models[nominal] = fit_by_all_equality_faces(x, y, weights, knots)
    loss5, loss7 = models[5]["loss"], models[7]["loss"]
    tie = 1e-10*max(1, loss5, loss7)
    chosen = 5 if loss5 <= loss7+tie else 7
    rows, samples = [], {}
    for nominal, model in [(0, models[5]), *models.items()]:
        for run in TEST:
            row, sample = independent_score(runs[run], model, nominal)
            rows.append(row)
            samples[(nominal, run)] = sample
    comparisons = compare_primary(primary_output, models, chosen, rows, samples, custody, runs)
    output = HERE/"independent_audit_outputs"
    output.mkdir(exist_ok=True)
    write_csv(output/"independent_results.csv", rows)
    model_rows = [dict(nominal_knots=k, knot_index=i, candidate_knot_C=float(v), fitted_source_C=float(models[k]["y"][i]))
                  for k in models for i, v in enumerate(models[k]["x"])]
    write_csv(output/"independent_models.csv", model_rows)
    receipt = dict(created_utc=datetime.now(timezone.utc).isoformat(),
                   audit_script_sha256=sha(__file__), protocol_sha256=sha(HERE/"PROTOCOL.md"),
                   independent_implementation="stdlib CSV parser, sequential longest-on scan, explicit interpolation/event/support loops, exhaustive contiguous equality-face least squares",
                   training_runs=list(TRAIN), testing_runs=list(TEST), self_tests=tests,
                   primary_output_directory=str(primary_output),
                   primary_selection_sha256=sha(selection_file),
                   source_provenance=custody, selected_nominal_knots=chosen,
                   independent_models=plain(models), comparisons=comparisons,
                   primary_composite_pass=all(r["composite_pass"] for r in rows if r["nominal_knots"] == chosen),
                   output_sha256={p.name: sha(p) for p in output.glob("*.csv")},
                   passed=all(c["passed"] for c in comparisons))
    (output/"independent_audit.json").write_text(json.dumps(plain(receipt), indent=2, allow_nan=False), encoding="utf-8")
    assert receipt["passed"], "Independent audit mismatch; preserve evidence and diagnose."
    print(json.dumps(dict(passed=True, selected_nominal_knots=chosen,
                         checks=len(comparisons), real_data_read=True), indent=2))


def compare_primary(primary_output, models, chosen, rows, samples, custody, runs):
    """Read-only comparisons against the explicitly documented primary schema."""
    prepared, evaluated = primary_output/"prepared", primary_output/"evaluated"
    with (evaluated/"held_out_results.csv").open(newline="", encoding="utf-8-sig") as stream:
        actual_rows = list(csv.DictReader(stream))
    assert len(actual_rows) == 6
    selection = json.loads((prepared/"selection_record.json").read_text(encoding="utf-8"))
    evaluation = json.loads((evaluated/"evaluation_record.json").read_text(encoding="utf-8"))
    summary = json.loads((evaluated/"criterion_summary.json").read_text(encoding="utf-8"))
    checks = []
    def check(label, actual, expected, tolerance=1e-7):
        if isinstance(expected, (bool, np.bool_)):
            observed = actual if isinstance(actual, bool) else str(actual).lower() == "true"
            passed, delta = observed == bool(expected), None
        elif expected is None:
            passed, delta = actual is None or str(actual) in ("", "nan", "None"), None
        elif isinstance(expected, str):
            passed, delta = str(actual) == expected, None
        elif isinstance(expected, list):
            observed = json.loads(actual) if isinstance(actual, str) else actual
            delta = max((abs(a-b) for a, b in zip(observed, expected)), default=0.0)
            passed = len(observed) == len(expected) and delta <= tolerance
        else:
            delta = abs(float(actual)-float(expected))
            passed = math.isfinite(delta) and delta <= tolerance
        checks.append(dict(check=label, passed=bool(passed), absolute_difference=delta, tolerance=tolerance))
    check("selection_primary_K", selection["primary_requested_k"], chosen, 0)
    check("selection_training_split", selection["training_runs"], list(TRAIN), 0)
    check("selection_test_split", selection["held_out_runs"], list(TEST), 0)
    check("protocol_hash", selection["protocol_sha256"], EXPECTED_PROTOCOL)
    check("selection_frozen_before_evaluation", evaluation["selection_sha256"], sha(prepared/"selection_record.json"))
    check("evaluation_did_not_fit", evaluation["fit_performed_during_evaluation"], False)
    for folder, record in ((prepared, selection), (evaluated, evaluation)):
        for filename, expected in record["payload_sha256"].items():
            check(f"manifest:{folder.name}/{filename}", sha(folder/filename), expected)
    for k, independent in models.items():
        with (prepared/f"K{k}_knots.csv").open(newline="", encoding="utf-8-sig") as stream:
            knots = list(csv.DictReader(stream))
        check(f"K{k}:actual_knot_count", len(knots), len(independent["x"]), 0)
        assert len(knots) == len(independent["x"])
        for i, row in enumerate(knots):
            check(f"K{k}:x[{i}]", row["candidate_knot_C"], independent["x"][i], 1e-10)
            check(f"K{k}:y[{i}]", row["fitted_source_C"], independent["y"][i], 1e-6)
        metadata = next(item for item in selection["models"] if item["requested_k"] == k)
        check(f"K{k}:training_mse", metadata["equal_run_training_mse_C2"], independent["loss"], 1e-7)
        fit = json.loads((prepared/f"K{k}_fit_record.json").read_text(encoding="utf-8"))
        check(f"K{k}:solver_success", fit["success"], True)
        check(f"K{k}:solver_KKT_limit", fit["kkt_residual"] <= 1e-7, True)
        check(f"K{k}:solver_rank", fit["rank"], len(independent["x"]), 0)
    aliases = dict(rmse_ratio_to_identity="rmse_ratio_vs_identity",
                   rmse_reduction_fraction="rmse_reduction_fraction_vs_identity",
                   material_improvement_50pct="material_50pct_rmse_reduction",
                   entire_preaction_trace_in_support="full_preaction_trace_in_training_support",
                   first_remains_below_through_horizon="stays_below_through_recorded_horizon",
                   mapped_gradient_at_horizon_K_per_min="final_gradient_K_per_min")
    ignored = {"run", "nominal_knots", "method", "identity_rmse_C", "total_observed_downward_crossings", "composite_pass"}
    for independent in rows:
        run, k = independent["run"], independent["nominal_knots"]
        method = f"K{k}" if k else "identity"
        actual = next(row for row in actual_rows if int(row["held_out_run"]) == run and row["method"] == method)
        for field, expected in independent.items():
            if field in ignored:
                continue
            target = aliases.get(field, field)
            assert target in actual, f"Uncompared independent metric: {field}"
            check(f"{method}/Test{run}:{field}", actual[target], expected, 1e-5 if "min" in field else 1e-7)
        check(f"{method}/Test{run}:primary_map", actual["primary_map"], k == chosen)
    with (evaluated/"source_provenance.csv").open(newline="", encoding="utf-8-sig") as stream:
        source_rows = list(csv.DictReader(stream))
    source_aliases = dict(member="source_member", source_sha256="sha256", start_index="heater_start_index",
                          action_index="first_off_index", preaction_samples="strict_preaction_samples")
    for independent in custody:
        actual = next(row for row in source_rows if int(row["run"]) == independent["run"])
        for field, expected in independent.items():
            check(f"source{independent['run']}:{field}", actual[source_aliases.get(field, field)], expected, 0)
    # Verify the primary exported training data/weights contain exactly the four runs.
    with (prepared/"training_pairs_and_weights.csv").open(newline="", encoding="utf-8-sig") as stream:
        training_rows = list(csv.DictReader(stream))
    assert {int(row["training_run"]) for row in training_rows} == set(TRAIN)
    for run in TRAIN:
        subset = [row for row in training_rows if int(row["training_run"]) == run]
        check(f"training{run}:row_count", len(subset), len(runs[run]["t"]), 0)
        for column, expected in (("time_min", runs[run]["t"]), ("candidate_C", runs[run]["x"]),
                                 ("source_C", runs[run]["y"]), ("weight", np.full(len(subset), 1/(4*len(subset))))):
            delta = float(np.max(np.abs(np.array([float(row[column]) for row in subset])-expected)))
            check(f"training{run}:{column}_maxdiff", delta, 0, 1e-10)
    with (evaluated/"held_out_samples.csv").open(newline="", encoding="utf-8-sig") as stream:
        sample_rows = list(csv.DictReader(stream))
    for (k, run), independent in samples.items():
        method = f"K{k}" if k else "identity"
        actual = [row for row in sample_rows if int(row["held_out_run"]) == run and row["method"] == method]
        check(f"samples/{method}/{run}:count", len(actual), len(independent["time_min"]), 0)
        for field, expected in independent.items():
            if expected.dtype == bool:
                observed = np.array([row[field].lower() == "true" for row in actual])
                check(f"samples/{method}/{run}:{field}", np.array_equal(observed, expected), True)
            else:
                observed = np.array([float(row[field]) if row[field] else np.nan for row in actual])
                check(f"samples/{method}/{run}:{field}_NaN_pattern", np.array_equal(np.isnan(observed), np.isnan(expected)), True)
                delta = float(np.nanmax(np.abs(observed-expected)))
                check(f"samples/{method}/{run}:{field}_maxdiff", delta, 0, 1e-6 if field in ("predicted_C", "residual_C") else 1e-8)
    primary = [row for row in rows if row["nominal_knots"] == chosen]
    for field, expected in (
        ("primary_requested_k", chosen),
        ("both_D50_supported_observed_first_events_inside_one_sided_window", all(row["supported_one_sided_5_min_success"] for row in primary)),
        ("both_D50_at_least_50pct_RMSE_reduction", all(row["material_improvement_50pct"] for row in primary)),
        ("stronger_evidence_composite_pass", all(row["composite_pass"] for row in primary)),
        ("both_D50_recorded_horizon_sustained", all(row["first_remains_below_through_horizon"] is True for row in primary)),
    ):
        check("summary:"+field, summary[field], expected, 0)
    return checks


if __name__ == "__main__":
    main()
