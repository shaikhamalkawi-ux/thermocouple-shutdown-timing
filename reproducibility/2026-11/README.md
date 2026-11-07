# DGIG Weber V2 source-only reproducibility bundle — public research snapshot (8 Nov 2026)

The source code and derived tables in this bundle accompany the **author-unassigned working manuscript** "Temperature Error Reduction Does Not Guarantee First-Crossing Fidelity in Packed-Bed Thermal Storage". The work has not been submitted or accepted; no journal article DOI exists. This snapshot contains **no original measurement CSVs**. All files have been checked for raw source-data exclusion. This is not the historical supervisory controller software and does not implement an actual replacement-controlled shutdown.

## Get the experimental source
Download **Weber et al. Mendeley Data Version 2**, DOI https://doi.org/10.17632/3pp86gdvh4.2 (CC BY 4.0), and extract the original nine `MeasurementData.CSV` files without alteration. Please also cite Weber et al., *Data in Brief* 61 (2025), 111743, DOI https://doi.org/10.1016/j.dib.2025.111743.

## Primary replay and D50
1. Create a Python 3.11+ environment and install NumPy, pandas, SciPy and matplotlib (`pip install -r requirements.txt`).
2. From this bundle's `primary_D50_code/` directory, run:

```sh
python prepare_from_weber_v2.py --upstream /PATH/TO/UNMODIFIED/WEBER_V2 --output /PATH/TO/NEW_WORKTREE
python /PATH/TO/NEW_WORKTREE/primary/reproduce_weber_operational.py --source-zips /PATH/TO/NEW_WORKTREE/primary/source_zips --output /PATH/TO/NEW_PRIMARY_RESULTS
python verify_primary_outputs.py --results /PATH/TO/NEW_PRIMARY_RESULTS
```

3. The blocked D50 protocol and scripts are retained under `primary_D50_code/d50/.../BLOCKED_LOW_CAPACITY_20260927/`. Follow `primary_D50_code/README.md`. An earlier separate fresh run (EP7) passed 466/466 source comparisons; that receipt is provenance, not an assertion that every command has been rerun in the current environment.

## Additional supporting analyses
- `modules/event_contract/`: event-objective and training-only comparison; full original-package eight-stage replay PASS, data-hydrated all-in-one run previously timed out at plotting.
- `modules/exact_certificates/`: frozen seven-knot exact rational dual and 21,980-row witness PASS; optional solver numerical byte parity differed only at floating-point residual, not exact certificate.
- `modules/raw_error/`: 14/14 exact checks of mathematical error-box statements and six counterexamples PASS; this does **not** model physical thermocouple noise.
- `modules/gradient_sensitivity/`: historical diagnostic script preserved; **not independently replayable** without legacy R13 archive. Do not claim a complete fresh reproduction of this module.

The compact original Weber ZIP containers are reconstructed locally by `hydrate_frozen_weber.py` using nine SHA-256-admitted CSVs and frozen container metadata; they are not distributed here. The hash guard rejects changed source bytes. This archive excludes NIST/PCM restricted source material, upstream Weber scripts/spreadsheets, private correspondence and authorship forms.

## Scientific and rights boundaries
Only six Weber physical runs constitute the primary experimental units. The 24 candidate/run comparisons are dependent. Test 5 and Test 9 D50 outcomes are exploratory; no mapped first crossing was observed through the two pre-action horizons, which extend 1.435 and 0.146 minutes past the respective reconstructed source deadlines. This is a missed selected deadline, not a measured duration of a later event, physical sensor interchangeability, energy savings or closed-loop validation.

**Public viewing ≠ an open-source license.** No permission to sublicense/redistribute project-developed code has yet been jointly established for the unresolved final author/contributor roster. A separate permissive software license will be added only after copyright-holder approval. Until then this code may be read and run for scholarly verification, but users should request permission before copying into new redistribution projects. See `LICENSE_STATUS.md`. We do not claim a Zenodo DOI or publisher acceptance.
