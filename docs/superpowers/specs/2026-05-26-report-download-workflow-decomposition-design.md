# Report Download Workflow Decomposition Design

## Goal

Reduce the mixed-responsibility concentration in
`src/orchestrators/_report_download_orchestrator/workflow.py` without changing
report acquisition behavior, model cost, service call ownership, retry
decisions, persistence semantics, or public entrypoints.

## Scope

`src/orchestrators/report_download_orchestrator.py` remains the public facade.
`run_report_download(...)` remains the private workflow coordinator exposed
from `src/orchestrators/_report_download_orchestrator/workflow.py`.

The change extracts existing orchestration capability families inside the
same private bounded context:

```text
src/orchestrators/_report_download_orchestrator/
  workflow.py
  dependencies.py
  route_planner.py
  candidate_readiness.py
  failure_forensics.py
  promotions.py
  persistence.py
  drive_archive.py
```

No new external system boundary, deployable unit, public workflow, prompt,
contract version, configuration field, or retry policy is introduced.

## Boundary Design

### Workflow Coordinator: `workflow.py`

`workflow.py` retains `run_report_download(...)`. It logs workflow start and
completion, resolves route memory and planning, executes route attempts in the
existing order, applies the existing retry/fallback decisions, invokes focused
post-acquisition capabilities, and returns `ReportDownloadOrchestratorResult`.

### Dependencies: `dependencies.py`

This module owns the existing `ReportDownloadDependencies` dataclass and its
default dependency construction. `workflow.py` re-exports that class so the
existing public facade and tests retain their imports.

### Candidate Readiness: `candidate_readiness.py`

This module owns candidate URL/title screening and typed early rejection
before browser/model spend:

- readiness scoring and signal evaluation
- mixed-content hub detection
- source-page surface identity comparison
- readiness log events and typed rejection errors

It does not perform downloads, persistence, or retries.

### Failure Forensics: `failure_forensics.py`

This module owns existing failed-attempt evidence packaging:

- terminal-evidence reconstruction from typed error context
- safe/bounded forensic metadata conversion
- local forensic artifact copy/write behavior
- forensic-pack persistence and propagation into error context

It does not choose whether a route attempt is retried.

### Promotions: `promotions.py`

This module owns post-success browser-route promotion decisions:

- route playbook promotion eligibility and invocation
- private-API promotion candidate observation and promotion
- promotion event logging

It preserves the existing best-effort behavior and does not add browser or
provider calls.

### Persistence: `persistence.py`

This module owns idempotent post-acquisition state recording:

- idempotency lookup and outcome recording helpers
- route record construction/checksum and route-history recording
- downloaded report-source persistence and report-value score recording
- identity-field update persistence and restoration

It receives the acquired result from the coordinator and returns the same
record/update values needed for final result construction.

### Drive Archive: `drive_archive.py`

This module owns optional successful-artifact archival:

- local terminal artifact selection and MIME resolution
- publisher Drive folder resolution
- duplicate detection, upload, and upload idempotency
- required versus best-effort archive failure handling

It does not run unless the existing settings enable Drive upload.

## Data And Control Flow

1. The public facade calls `workflow.run_report_download(...)`.
2. The coordinator logs workflow start and invokes `candidate_readiness.py`
   before any acquisition spend.
3. The coordinator reads route memory, requests the existing route plan, and
   performs attempts with unchanged fallback and retry decisions.
4. Failed route attempts invoke `failure_forensics.py` through the existing
   bounded failure path.
5. After acquisition succeeds, `persistence.py` records route/source/value
   and identity outcomes with unchanged idempotency semantics.
6. `promotions.py` evaluates existing optional promotion work.
7. `drive_archive.py` archives terminal artifacts only when existing settings
   enable that optional side effect.
8. The coordinator emits the existing completion event and returns the same
   result contract.

## Compatibility Constraints

- `src/orchestrators/report_download_orchestrator.py` exports remain unchanged.
- Existing tests may continue importing `ReportDownloadDependencies` through
  the public facade.
- `route_planner.py`, external services, generators, contracts, settings, and
  logger/event names retain their existing observable behavior.
- Retry policy, fallback ordering, typed `AppError` outcomes, idempotency
  keys/checksums, stored records, and Drive archive decisions remain stable.

## Quality, Speed, And Cost Controls

This is a movement-only decomposition. It does not alter:

- browser-download prompts, provider/model settings, or model call count
- route plan construction, attempt ordering, or retry/backoff calculation
- browser/HTTP/Drive service invocation conditions
- idempotency checks, local persistence payloads, or report scoring
- Drive upload enablement/required behavior

The bounded live verification disables Drive archival while exercising the
real workflow, real browser/OpenRouter acquisition route, local database
effects, and artifact validation.

## Testing And Verification

Implementation begins with a failing structure test proving that the intended
private modules own their function families and `workflow.py` retains the
single coordinator.

After extraction, verification includes:

- `tests/test_report_download_orchestrator.py` and
  `tests/test_report_download_route_planner.py`
- affected browser-report download suites because the workflow calls the
  browser service behind its unchanged boundary
- formatting, typing, split-symbol, forbidden-patching, repository hygiene,
  coverage, mutation, and quality-regression gates
- the default synthetic suite
- a new guarded integration path invoking `run_report_download(...)` with
  real browser/OpenRouter execution against a local click-to-PDF fixture,
  temporary SQLite/files, and Drive upload disabled

## Documentation Deliverables

The implementation updates:

- `docs/architecture/report-download-workflow-decomposition-review.md`
- `README.md`
- `long_scripts.md`
