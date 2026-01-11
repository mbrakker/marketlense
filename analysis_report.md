# Code Analysis Outcome

## Key Findings

1. **Run context inconsistency (likely unintended)**
   - The CLI creates a run context and logs with it, but `run_ingest` creates a new run context internally, so the orchestrator logs do not correlate with the CLI run/task IDs.

2. **Redundant EOF checks in ingest (extra I/O)**
   - `check_pdf_eof` runs twice in a row; the second call happens even when the first check already indicates a valid EOF.

3. **Duplicate error logging on ingest failures**
   - The ingest exception handler emits two overlapping log events with nearly identical fields, inflating log volume without extra signal.

4. **Manual `AppSettings` to `IngestSettings` copy is repetitive**
   - The CLI constructs `IngestSettings` by copying every field from `AppSettings`, which is fragile if fields are added or renamed.

5. **Config loading logic is duplicated**
   - `load_settings` and `load_publish_settings` both define their own missing-value helpers and validation patterns, risking divergence over time.

## Applied Changes

- Reused the CLI run context inside `run_ingest` (orchestrator now accepts an optional `ctx`) so ingest logs share the CLI run/task IDs instead of starting a new run.
- Simplified PDF integrity checks: the EOF probe now re-runs only after a failed first check, avoiding the redundant second call on healthy PDFs.
- Consolidated ingest failure logging to a single structured `file_processing_error` event with full context instead of emitting overlapping entries.
- Added a shared `to_ingest_settings` adapter (and `ConfigResolver` helper) so `IngestSettings` construction reuses `AppSettings` without manual field-by-field copying.
- Unified missing-value resolution between `load_settings` and `load_publish_settings` via the shared resolver to keep validation paths consistent.
