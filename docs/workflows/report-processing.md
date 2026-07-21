# Report Processing

> **Documentation type:** Current reference
> **Canonical topic:** Report processing workflow
> **Update trigger:** Ingest, extraction, analysis, rendering, or checkpoint changes.

## Canonical report workflow entrypoints

`src/orchestrators/ingest_orchestrator.py::run_ingest` controls batch ingest. It delegates individual files to `src/orchestrators/ingest_file_orchestrator.py::run_ingest_file`, which validates source material and invokes `src/orchestrators/report_pipeline_orchestrator.py::run_report_pipeline`.

The pipeline delegates stage sequencing to `src/orchestrators/report_generation_orchestrator.py::run_report_generation`; the analysis stage is entered through `src/orchestrators/report_analysis_orchestrator.py::run_report_analysis`. Queue workers use explicit `stop_after_stage` boundaries so `source_prepared`, `selection_complete`, `analysis_complete`, and `render_complete` are durable handoffs rather than implicit direct chaining. The workflow extracts and validates report text, prepares evidence and visual candidates, generates structured artifacts, validates output, and renders the publication package. At analysis and render completion, independently verified prompt-family materialisations preserve family-level provenance; an enforced prompt-only repair reuses the retained source and unaffected families, then revalidates and rerenders locally.

`resume_from_stage` supports `source_prepared`, `selection_complete`, `analysis_complete`, `render_complete`, and `latest_safe` when the applicable retained checkpoint passes validation.

A render-only resume reuses report-card assets only when the complete validated
report-card manifest is also retained. If that manifest is missing, the renderer
regenerates the deterministic cover set and manifest before the package can
reach the blocking publication boundary; it never reports a package as ready
with orphaned card assets.

`ingest --force-report-cards` resumes from the validated analysis checkpoint,
not `latest_safe`, only when an existing rendered package has a missing or
invalid card manifest. It rebuilds that render/card package and avoids a second
analysis or model-generation pass. New files follow the normal pipeline and
therefore never request a nonexistent checkpoint.

The same render outcome fails closed when report-card publisher, region, or
period metadata fails public-metadata governance. Such a package remains a
render error with the typed reason and cannot be mistaken for a publication
candidate.

`region` and `covered_period` are optional card labels: known missing-value
tokens are deterministically omitted before manifest validation, while a
placeholder publisher or extraction leakage remains a blocking error. This
prevents internal labels from reaching WordPress without inventing metadata.
The report-card contract permits those omitted optional labels and renders an
unknown geography rather than manufacturing a period or location.

Run a configured batch with `python -m src.cli ingest --attempt-limit 1`. An
attempt limit counts selected reports, including failures; it never continues
selecting replacements to meet a success count. `--limit` remains a deprecated
alias with the same attempt-limit meaning. Release and reliability validation
use `--cohort-size N --cohort-manifest <path>`: files first pass deterministic
admission (source identity, supported type, active-quarantine, PDF structure,
and usable-source-content checks), then the exact admitted IDs are atomically
persisted before report-generation work begins. The ordered candidate pool
continues only while this pre-manifest admission has fewer than `N` accepted
sources; a rejected candidate is not silently included. After the manifest is
written, no failure can trigger a replacement. Re-running with only
`--cohort-manifest <path>` replays the same immutable members without a Drive
reselection. A malformed manifest, duplicate member, size mismatch, rejected
admission candidate cannot enter the cohort, and an insufficient eligible
population fails closed.
`--success-target N` is the only explicit mode allowed to select later
candidates after a failure; it is prohibited for release/reliability rates.
Publish a fixed cohort with the same `--cohort-manifest <path>` passed to
`publish-wp`. This closes each cohort member with a typed WordPress outcome:
a verified write or authenticated idempotent readback becomes
`published_verified`; an unattempted or unverified member is `blocked`.
Use `--rescan` only when the normal cursor should be bypassed. Queue operations and checkpoint recovery are
documented in [asynchronous workflow queue](../architecture/asynchronous-workflow-queue.md).
See [validation and regeneration](validation-and-regeneration.md), [artifact
model](../architecture/data-and-artifact-model.md), and
[configuration](../ops/configuration.md).
