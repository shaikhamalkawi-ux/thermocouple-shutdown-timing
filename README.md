# Thermocouple substitution and shutdown-event timing in packed-bed thermal storage

**Repository status: public methods-and-results preview; not a complete executable raw-data replication release, a journal-submitted manuscript, or a Zenodo deposit.**

This project studies whether moving a thermocouple from the source-designated shutdown location to another location preserves a threshold-defined heating-termination event. The relevant outcome is **first-event timing**, not temperature correlation or reconstruction error alone.

## Scientific setting

- **Source system:** Weber Version-2 packed-bed experiments (Tests 4–9), [Mendeley Data, DOI 10.17632/3pp86gdvh4.2](https://doi.org/10.17632/3pp86gdvh4.2).
- **Published control description:** trailing 15-minute temperature-gradient criterion below 1 K/min, using TR404-108e as the source.
- **Principal comparison:** four thermocouples nominally at the same axial level. The nearest 80-mm alternative reaches the unchanged criterion 23.59–31.12 minutes before the recorded commanded heater-off across six runs.
- **Temperature-versus-event check:** in an internal configuration-blocked analysis, a seven-knot monotone map lowers held-out D50 temperature RMSE by 94.96% and 96.03% in two runs, yet both first crossings are right-censored and both source deadlines are missed. These are two cases from one previously examined experimental apparatus, not external validation.
- **Separate mechanistic external check:** KIT VESPA data, [DOI 10.35097/byayp53e2q6ns3z3](https://doi.org/10.35097/byayp53e2q6ns3z3); **not an external operational controller-chain validation**.

## What is included

| Location | Content | Interpretation |
|---|---|---|
| [src/thermocouple_event.py](src/thermocouple_event.py) | Independent standard-library 15-minute finite-interval event helper | A transparent method implementation, **not** the original supervisory code or complete study pipeline |
| [tests/](tests/) | 12 synthetic checks | Tests of event-definition behavior, not raw-data replication |
| [results/primary_same_level_r10.csv](results/primary_same_level_r10.csv) | 24 manuscript-transcribed rounded rows | Source report values, not fresh recomputation |
| [results/d50_blocked_r10.csv](results/d50_blocked_r10.csv) | 2 manuscript-transcribed rounded D50 rows | Both are censored and miss the one-sided source deadline |
| [scripts/check_result_ledger.py](scripts/check_result_ledger.py) | Rounded-table arithmetic gate | Consistency, **not** independent science verification |
| [docs/](docs/) | Source provenance, R10 fingerprints, scope and limitations | Release boundaries and claim trace |

## Run the published repository checks

Python 3.11+ is sufficient; these checks have **no third-party Python dependencies**:

```bash
python -m unittest discover -s tests -v
python scripts/check_result_ledger.py
```

The public repository includes a GitHub Actions check with the same commands. Initial staging checks passed 12 synthetic tests and a 24+2 table-consistency gate; this must **not** be confused with the manuscript's separate 466/466 independently audited configuration-blocked numerical result checks.

## What is deliberately not uploaded

Raw Weber measurements, raw VESPA files (CC BY-NC 4.0), access-restricted third-party measurements, private correspondence, pre-submission author material, and unreviewed R10 manuscript/LaTeX production files are not published in this repository. Read [Reproducibility scope](docs/REPRODUCIBILITY_SCOPE.md) and [Data sources](docs/DATA_SOURCES.md).

## Citation and release status

The manuscript version remains an **author-review candidate**. There is currently **no tagged archival release, Zenodo DOI or approved code license**. Do not cite this repository as a complete reproduction archive, or infer prospective controller equivalence, safety, causal energy benefit, or generalization beyond the reported apparatus.
