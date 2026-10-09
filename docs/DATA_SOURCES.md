# Experimental data provenance and redistribution boundary

## Primary experimental source: Weber packed-bed thermal storage

- Experimental campaign: Weber et al., Version-2 packed-bed heating measurements.
- Official Mendeley Data DOI: https://doi.org/10.17632/3pp86gdvh4.2
- The original repository record is cited by the DGIG manuscript as CC BY 4.0.
- Primary rule-based heating experiments: Tests 4–9 (six runs).
- Ancillary fixed-duration experiments: Tests 1–3 (not used as shutdown-controller test cases).
- Source shutdown thermocouple: TR404-108e, nominal radial coordinate 95 mm, Level 4.
- Substitute candidates: TR404-333a (0 mm), TR404-018b (30 mm), TR404-063c (60 mm), TR404-085d (80 mm).
- Original rule: preceding 15-minute gradient below 1 K/min.
- Recorded heater-command proxy: first off sample following the longest sustained interval of `Heater_AO > 4.5 mA`.
- The historical supervisory derivative implementation has not been recovered. The paper's finite-difference analysis is **source-compatible**, not a byte-for-byte implementation replay.

### Input files

The original research archive includes nine `MeasurementData.CSV` files and source metadata/plotting scripts. Their full raw bytes are **not mirrored in this GitHub repository**. To reproduce the complete experiment, obtain the official dataset and separately verify the file hashes and row counts against the authors' archived reproducibility manifests.

## Mechanistic external dataset: KIT VESPA

- Dataset DOI: https://doi.org/10.35097/byayp53e2q6ns3z3
- License stated in the source package: CC BY-NC 4.0.
- 11 charge and 17 discharge raw files.
- The evaluated VESPA data do **not** establish an admitted native controller-rule-action shutdown chain. They support bounded spatial/thermal front-timing analysis, **not external operational shutdown validation**.
- No VESPA raw data are republished here. Consult the source license and original repository for authorized reuse.

## Restricted external data

Access-controlled third-party datasets and unpublished correspondence are **not** part of this repository. Public availability must not be inferred from metadata alone.
