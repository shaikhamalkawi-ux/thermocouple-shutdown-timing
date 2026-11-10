# Reproducibility scope | DGIG November 2026 public source-only release

This repository is a **research-code and derived-results deposit**, not the manuscript/PDF host, historical supervisory controller implementation, complete hardware validation, or an open-source license grant. The source-only archives and directly readable scripts are in [`reproducibility/2026-11/`](../reproducibility/2026-11/README.md). No author-review manuscript or Supplement PDF is present in the current public branch.

## Available materials and their limits

| File family | What can be inspected or checked | What cannot be inferred |
| --- | --- | --- |
| [`src/`](../src/) and [`tests/`](../tests/) | Independent event helper, 12 synthetic contract checks | Original 2017/2025 supervisory-controller code or new measured shutdowns |
| [`results/`](../results/) and [ledger checker](../scripts/check_result_ledger.py) | 24+2 rounded result values transcribed from earlier research reports | Independent calculations from source measurements |
| [Primary/D50 source-only archive](../reproducibility/2026-11/DGIG_Weber_SourceOnly_Primary_D50_v1.zip) | Source SHA-256 admission, primary event replay, blocked D50 replay/verification code | Reproduction before obtaining original Weber V2 data |
| [Full-methods source-only archive](../reproducibility/2026-11/DGIG_Weber_SourceOnly_FullMethods_v1.zip) | Event-contract, exact rational witness, illustrative raw-error modules and bounded audit materials | Complete historical R13 gradient-sensitivity rerun or physical sensor-error robustness |
| [Readable major Python scripts](../reproducibility/2026-11/scripts/) | Transparent source methodology without opening ZIPs | Permission to sublicense/repackage the code or claimed external operational validation |

## Supplemental event-lead source-only module

The [joint threshold--raw-error module](../reproducibility/2026-11-event-lead/README.md) includes two independently checkable Python replays and derived summaries; the raw data and journal PDFs are not hosted. Its strict pre-action separation check is explicit and its perturbation box has no calibrated physical-uncertainty interpretation. This module does not supersede or modify the earlier Weber/D50 source-only replay or historical controller limitations.

## Input admission and scientific boundaries

Obtain the **nine unchanged** upstream `MeasurementData.CSV` files from Weber [Mendeley Data Version 2](https://doi.org/10.17632/3pp86gdvh4.2). Their bytes are not redistributed on this repository. Follow the hash check and commands in the [November reproducibility instructions](../reproducibility/2026-11/README.md). The 15-minute finite-interval gradient is *source-compatible*, not byte-for-byte historical PLC code.

Prior separately performed clean-extraction audits reported 24/24 primary and 466/466 D50 comparisons; these are historical receipts, not tests freshly performed by cloning the public repository. The historical R13 gradient-sensitivity module is **HOLD** pending its legacy dependency archive; optional floating-point solver byte equality is also not claimed. The 2026 Weber data-article [corrigendum](https://doi.org/10.1016/j.dib.2026.113089) is an acknowledgement amendment, not a new input dataset.

The six Weber tests come from **one experimental apparatus**. Twenty-four candidate/run results are dependent comparisons. D50 Tests 5 and 9 have no mapped first crossing observed before their strict pre-action recording horizons; these end only 1.435 and 0.146 minutes after the respective source deadlines. Accordingly the one-sided deadlines are missed, but no later-event duration is measured. The physical controller was not rewired. No result establishes energy savings, safety, prospective sensor interchangeability, or causal controller response.

KIT VESPA and separately audited NIST/PCM logs are diagnostic external context with different predicates and incomplete historical controller-action mapping, not Weber-type replacement validation; see [data provenance](DATA_SOURCES.md).

## Copyright and public-draft status

The current branch contains code, derived results and documentation **only**; the author-unassigned working manuscript and focused supplement are maintained privately for review. Deleting draft files from the current branch does not automatically erase any previously published Git history, caches, forks or copies. No DOI, formal article acceptance, final author list or general-purpose redistribution license has been established. See [license status](../reproducibility/2026-11/LICENSE_STATUS.md) and [citation record](../reproducibility/2026-11/CITATION_AND_VERSION.md).
