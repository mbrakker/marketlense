# Report Processing

> **Documentation type:** Current reference
> **Canonical topic:** Report processing workflow
> **Update trigger:** Ingest, extraction, analysis, rendering, or checkpoint changes.

## Canonical report workflow entrypoints

`src/orchestrators/ingest_orchestrator.py::run_ingest` controls batch ingest. It delegates individual files to `src/orchestrators/ingest_file_orchestrator.py::run_ingest_file`, which validates source material and invokes `src/orchestrators/report_pipeline_orchestrator.py::run_report_pipeline`.

The pipeline delegates stage sequencing to `src/orchestrators/report_generation_orchestrator.py::run_report_generation`; the analysis stage is entered through `src/orchestrators/report_analysis_orchestrator.py::run_report_analysis`. Queue workers use explicit `stop_after_stage` boundaries so `source_prepared`, `selection_complete`, `analysis_complete`, and `render_complete` are durable handoffs rather than implicit direct chaining. The workflow extracts and validates report text, prepares evidence and visual candidates, generates structured artifacts, validates output, and renders the publication package.

`resume_from_stage` supports `source_prepared`, `selection_complete`, `analysis_complete`, `render_complete`, and `latest_safe` when the applicable retained checkpoint passes validation.

Run a configured batch with `python -m src.cli ingest --limit 1`. Use `--rescan` only when the normal cursor should be bypassed. Queue operations and checkpoint recovery are documented in [asynchronous workflow queue](../architecture/asynchronous-workflow-queue.md). See [validation and regeneration](validation-and-regeneration.md), [artifact model](../architecture/data-and-artifact-model.md), and [configuration](../ops/configuration.md).
