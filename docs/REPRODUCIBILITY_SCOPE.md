# Reproducibility scope — repository preparation stage

**Current state: partial public verification materials; NOT a complete raw-source reproduction of DGIG R10.**

## Included

- `src/thermocouple_event.py`: a small independent, standard-library implementation of the paper's described trailing-gradient first-event *definition*. It handles finite-interval lag interpolation, explicit arming, strict pre-action censoring and descriptive one-sided event windows. It is **not** the original supervisory controller or the authors' entire calculation pipeline.
- `tests/test_thermocouple_event.py`: 12 **synthetic** unit tests of that standalone helper.
- `results/primary_same_level_r10.csv`: 24 paper-reported, **rounded** primary candidate/run values, transcribed from the R10 manuscript table.
- `results/d50_blocked_r10.csv`: two paper-reported, **rounded** D50 held-out results from the locked configuration-blocked R10 analysis.
- `scripts/check_result_ledger.py`: data-shape, sign, and arithmetic consistency checks of those rounded tables. This script **does not** reconstruct them from raw measurements.

## Excluded and not yet available from this repository

- Nine raw Weber input files and full source recovery audit.
- Full affine, causal, PAVA and 5-/7-knot mapping fit implementations, cross-validation predictions and independent numerical replay.
- Raw KIT VESPA data; restricted/external datasets.
- The R10 manuscript PDF, complete LaTeX production source and full supplementary reproducibility archive, which remain under author review.
- Zenodo DOI, tagged archival release, code-license decision and independent fresh-clone raw-source verification.

## Run checks

Use Python 3.11 or later. No third-party packages are required for the included checks:

```bash
python -m unittest discover -s tests -v
python scripts/check_result_ledger.py
```

The initial staging verification completed **12/12 synthetic unit tests** and the **24+2 rounded record consistency gate**. These are limited software/table checks, not replication of the journal results. The published-source scientific calculations were separately audited in the private research package; its 466/466 configuration-blocked checks are **not being rerun by this GitHub repository**.

Do not cite this GitHub project as a complete executable companion archive until the full input pipeline is admitted, released with appropriate permissions and verified from a fresh clone.

## R12 reviewer archive (prepared separately; not hosted on GitHub)

The DGIG R12 editorial/reproducibility closure (10 October 2026) prepared a separate, reviewer-facing ZIP named `DGIG_R12_Reviewer_Reproducibility.zip` (20,110,083 bytes; SHA-256 `ff0db085aaefbfb427b7f7957f14aba5889ed4f56885cc5fece9ff9b095d7ef1`). That ZIP contains the original compact CC BY 4.0 Weber source measurements for Tests 1–9, paper-relevant reproduction programs, recorded R9 numerical results, and the frozen D50 checkpoint with independent per-comparison audit. A clean-extraction replay of the original native source data passed 24/24 primary numerical assertions, and a separate clean-extraction D50 raw-source audit passed 466/466 checks. The full 8+7-stage R9 pipeline was *not* freshly completed in that session; historical receipts are included and labeled as such.

The reviewer ZIP **is not uploaded to or downloadable from this public GitHub repository**. It must be provided through the manuscript's approved supplementary-material or authorized reviewer-access channel, with a fresh integrity check. Until that submission step is completed, this repository remains a partial public methods preview, not a complete standalone replication deposit. No Zenodo DOI has been assigned.
