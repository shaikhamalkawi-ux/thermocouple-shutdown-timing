# DGIG Event-Lead Certificate | Source-only analytical snapshot

**Research code and derived result summaries only.** No manuscript, accepted-article PDF, raw measurements, author metadata, or general-purpose software reuse license is included here. The numerical experiment is a *conditional recorded-trace sensitivity analysis*, not a tested controller or a physical sensor-uncertainty budget.

## Scope and result

The fixed 15-minute source-compatible finite-interval gradient rule is replayed on the six original Weber V2 source-controlled heating records (Tests 4-9), with four alternative same-height thermocouples per run: **24 dependent comparisons from one apparatus**. A retrospective threshold half-width of `0.010 K/min` about the nominal `1 K/min` and a hypothetical absolute sample-error box of `1.0 K` give **24/24 sufficient certificates** for a candidate first crossing **more than 16.11 minutes before the unchanged recorded heater-off command**. A `1.5 K` box retains **24/24 with more than 11.56 minutes**. At `1.6 K`, **23/24** are certified and the remainder is **NOT_CERTIFIED**, not a demonstrated reversal. Neither the parameter bounds nor their combinations were inferred from thermometer uncertainty calibrations.

The **historical supervisory controller software is unavailable**; the finite-interval source-compatible replay is not an exact PLC implementation. No physical substitution-controlled shutdown was performed, and no energy saving/safety result is claimed. Reference source: [Weber Mendeley Data V2](https://doi.org/10.17632/3pp86gdvh4.2), and its [Data in Brief article](https://doi.org/10.1016/j.dib.2025.111743).

## Source files

- `lead_certificate.py`: full primary algorithm, source hash admission, 1,200-case grid and five derived CSV outputs.
- `independent_decimal_audit.py`: a second independent source-decimal parser and exhaustive conditional check of all 1,200 cases and radii.
- `nominal_24.csv`, `joint_radii_24.csv`, `summary_grid.csv`, `nearest_focus.csv`: derived result summaries; original raw measurements are **not** redistributed.
- `QA_main.json`, `QA_independent_decimal.json`: code-generated verification receipts.
- `OUTPUT_FINGERPRINTS.json`: SHA-256 of all four hosted derived CSVs **and of the full generated 1,200-row grid** (`joint_lead_grid_24.csv`). The large 1,200-row output is produced locally by the script, not stored here as a static file.
- `test_certificate_guard.py`: portable synthetic + output-scope checks. No Weber raw data needed for this test.

## Reproduce from upstream data (Python 3.11+, standard library)

Obtain the two original Weber V2 archives with the unchanged Tests 4-6 and Tests 7-9 `MeasurementData.CSV` inputs from the upstream dataset. Do not rename or modify original CSV contents inside their archives. The code validates six SHA-256 input hashes and row counts.

```bash
python lead_certificate.py --source-zips /path/to/primary_A_tests4_6.zip /path/to/primary_B_tests7_9.zip --out output
python independent_decimal_audit.py --source-zips /path/to/primary_A_tests4_6.zip /path/to/primary_B_tests7_9.zip --result-dir output
python -m unittest -v test_certificate_guard.py
```

Inspect `output/QA_main.json`, `output/QA_independent_decimal.json`, and compare the SHA-256 of `output/joint_lead_grid_24.csv` with `OUTPUT_FINGERPRINTS.json`. An exact threshold-box certificate is a theorem about **sampled signals under an assumed perturbation set** and a **fixed action timestamp**. It does not establish robustness under arbitrary temperature-sensor drift, timestamp error, anti-aliasing, latency, actuator dynamics, thermocouple accuracy specifications or actual controller operation.

## Release, attribution, and rights

Public visibility does **not** imply permission to copy, adapt or redistribute this code beyond rights granted by law. The software reuse license and final author approvals are unresolved. This code must not be interpreted as a released manuscript, publisher-approved result or peer-reviewed validation. The earlier [Weber source-only analytical snapshot](../2026-11/README.md) remains unchanged and is distinct from this supplemental conditional event-lead module.
