# DGIG | Thermocouple first-crossing and shutdown-event timing

**Public repository for research code, derived result ledgers, and reproducibility documentation only.** The working manuscript, its PDF supplement, and journal-preparation source files are **not hosted in the current public branch**. The research has not been accepted or submitted to a journal, and no journal/software DOI or general code-reuse license has been assigned.

## Scientific question and bounded evidence

The study asks whether improving temperature reconstruction or moving a thermocouple preserves the first time a threshold-defined heating-termination criterion is satisfied. The question concerns **recorded-trace event timing**, not controller installation or proven safe sensor replacement.

- Original measurements: Weber et al., [Mendeley Data Version 2](https://doi.org/10.17632/3pp86gdvh4.2), Tests 4–9 for the six source-controlled heating runs; original source CSV bytes are not mirrored here.
- Original reported rule: trailing 15-minute temperature-gradient criterion below 1 K/min, applied to source sensor TR404-108e.
- Candidate comparison: the nearest alternative, TR404-085d at 80 mm radial position, first satisfies the reconstructed criterion 23.59–31.12 min before the **logged command** in the six recorded heating runs.
- Internal D50 stress check: a seven-knot temperature-fitted map decreases temperature RMSE by 94.96% and 96.03% in Tests 5 and 9, respectively, but neither mapped first crossing is observed by the chosen **reconstructed source-event deadline** within the short available horizons. Event times thereafter are unknown.
- None of these outcomes records an actual alternative-sensor-controlled heater shutdown. Six runs on one apparatus—not 24 independent experimental units—underlie the physical comparison.

The historical supervisory derivative routine was not recovered; the publicly inspectable finite-interval event rule is *source-compatible*, **not byte-identical PLC code**. Independent ice-storage/PCM-TES logs support only diagnostic distinctions among temperatures, threshold predicates, process flags and actuator states, not transferable replacement-controller validation.

## Event-lead certificate source-only release (November 2026)

The [joint threshold and raw-error early-event certificate](reproducibility/2026-11-event-lead/README.md) includes two full source-data replay programs, 24 dependent-case result summaries and 1,200-case numerical verification fingerprints. Its lead bounds are conditional on a hypothetical raw-sample error box, a retrospectively varied threshold, and an unchanged logged command and source-compatible 15-minute rule—not demonstrated sensor tolerances or actual replacement-controlled shutdowns. No working manuscript PDF or original Weber data is redistributed.

## Public files

| Path | Contents and role |
| --- | --- |
| [`reproducibility/2026-11/`](reproducibility/2026-11/README.md) | Source-only Weber first-crossing and D50 archives, supporting mathematical modules, instructions and explicit replay limitations |
| [`reproducibility/2026-11/scripts/`](reproducibility/2026-11/scripts/) | Readable key Python scripts |
| [`src/`](src/) and [`tests/`](tests/) | Standalone event helper and 12 synthetic tests, **not** the historical PLC program |
| [`results/`](results/) | 24 primary and 2 D50 manuscript-transcribed rounded result rows; not raw measurements |
| [`scripts/check_result_ledger.py`](scripts/check_result_ledger.py) | Rounded-ledger arithmetic/format consistency tests, not raw-data replication |
| [`docs/`](docs/) | Provenance, inference boundaries and precise reproducibility scope |

To reconstruct the primary analysis, obtain the **unmodified nine** `MeasurementData.CSV` inputs from [Weber V2](https://doi.org/10.17632/3pp86gdvh4.2), then follow the instructions and hash admission checks in [the source-only archive README](reproducibility/2026-11/README.md).

To run the basic standard-library tests (Python 3.11+):

```bash
python -m unittest discover -s tests -v
python scripts/check_result_ledger.py
```

These tests check definitions and transcribed ledger arithmetic. A **separate** private fresh-source audit previously reported 24/24 primary comparisons and 466/466 D50 numerical checks. Neither count should be presented as a fresh clone/run of this public repository alone. The historical R13-dependent sensitivity module is not yet independently replayable.

## Provenance, use and citation

The research-code snapshot is pinned at [commit `4b16d30aabe5c549cc27073ad8c7102d94d70ecf`](https://github.com/shaikhamalkawi-ux/thermocouple-shutdown-timing/tree/4b16d30aabe5c549cc27073ad8c7102d94d70ecf/reproducibility/2026-11); for current documentation use the latest branch commit SHA. Cite the original [Weber data DOI](https://doi.org/10.17632/3pp86gdvh4.2) and [Weber data article](https://doi.org/10.1016/j.dib.2025.111743) when using their measurements. The [2026 corrigendum](https://doi.org/10.1016/j.dib.2026.113089) adds a contributor acknowledgement; it does not supply a new controller algorithm or altered measurements.

**No license is granted by visibility alone.** Authorship, contributor permissions, and software redistribution rights remain to be resolved. Original Weber/VESPA raw measurements, restricted NIST/PCM source materials, private correspondence and article-preparation drafts are excluded. Do not infer population-level validity, safety, physical energy savings, or prospective controller equivalence from the public calculations.

See [reproducibility scope](docs/REPRODUCIBILITY_SCOPE.md), [data sources](docs/DATA_SOURCES.md), [license status](reproducibility/2026-11/LICENSE_STATUS.md) and [citation/version](reproducibility/2026-11/CITATION_AND_VERSION.md).
