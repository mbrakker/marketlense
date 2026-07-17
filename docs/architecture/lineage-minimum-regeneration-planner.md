# Lineage-driven minimum regeneration planner

## Purpose and ownership

The minimum regeneration planner is the single deterministic authority for
deciding which retained report artifacts may be consumed, which are unsafe,
and which workflow stages remain necessary. It is intentionally not a general
DAG scheduler: the report pipeline keeps its existing source, selection,
analysis, render, and publication ordering.

The pure policy lives in `src/utils/minimal_execution_planner.py`; its typed
input and output contracts live in `src/contracts/minimal_execution_plan.py`.
The report-store planning boundary observes files and SQLite lineage, records
audits, and exposes validated cross-report reads. Orchestrators consume an
already-built plan before model-client construction or publication preflight.

## Compatibility and fail-closed policy

`ExecutionCompatibilityVersions` carries the current schema, processing,
prompt, model-routing, validator, crop, template/render, parser, and OCR
versions. A retained artifact is reusable only when all of the following are
proven:

- its retained file exists and its observed SHA-256 equals its immutable hash;
- its direct dependency edges exactly match its declared dependencies;
- it is active and its lineage status is `complete`;
- the artifact-family compatibility keys match the current policy; and
- its source hash, source metadata, or publication target still agrees when
  those inputs apply.

Missing provenance is a blocker, not an optimistic cache hit. Historic rows
created before complete compatibility capture are explicitly
`legacy_unverified`; the bounded existing backfill can register missing rows,
but cannot silently upgrade them to complete provenance.

| Change or observation | Invalidated family | Minimum required work |
| --- | --- | --- |
| Source bytes, parser, OCR, missing retained file, hash mismatch, or dependency edge | Changed artifact and descendants | Existing stage order from the earliest affected stage |
| Persisted source publication metadata or template | Rendered HTML and downstream publication | Render only; no OCR, source parsing, analysis, artifacts, validation, or model client |
| Crop profile | Crop/preview and rendered HTML | Selection plus render; no report analysis |
| Prompt, schema, model policy, or validator | Affected analysis family and downstream outputs | Analysis plus render, preserving family-level evidence where available |
| Publication target | Publication record | Publication only |

The compatibility matrix in `tests/test_minimal_execution_planner.py` covers
each of these cases, deterministic plan hashing, targeted prompt-family
repair, render-only regeneration, crop repair, and publication-only retry.
It makes no provider calls.

## Integration and rollout

`run_report_pipeline` creates and persists a plan in `shadow` mode by default
before constructing model clients. Its first enforceable family is a proven
render-only plan: it resumes at `analysis_complete` without constructing the
OCR, analysis, validation, or artifact clients. The report-generation and
analysis orchestrators record the consumed plan hash and stages. Other plans
remain shadowed until their actual executor can preserve the existing stage
contracts.

`run_publish` creates a publication-repair plan before WordPress preflight.
In enforce mode, incomplete validated rendered lineage prevents preflight and
the WordPress write. Plan/audit rows retain planned stages and calls, actual
stages and calls, and deterministic divergence.

The policy switch remains `shadow`, `enforce`, or `disabled`. Rollout is:

1. collect shadow plans and compare planned and actual work;
2. enforce rendered-HTML-only reuse;
3. enable the next artifact family only after retained-fixture evidence;
4. revert to the existing latest-safe checkpoint behavior with `disabled` if
   needed. Plan/audit records remain available after rollback.

## Cross-report read boundary

Future cross-report code calls
`report_store_service.read_validated_report_artifacts()` with report ID,
requested `claim`, `evidence`, `summary`, `chart`, or `metadata` families,
current compatibility, and known source hashes. The boundary plans a
`cross_report_read` first and returns no artifacts on invalid or incomplete
lineage, so it cannot re-ingest a source PDF or accidentally consume a stale
retained artifact.

## Observability

The report-store boundary emits plan-created, artifact-reused,
artifact-invalidated, missing-lineage, hash-mismatch, compatibility-mismatch,
stage-skipped, external-call-avoided, estimated-cost-avoided, and
planned-versus-actual-divergence events. Reuse logs include the content hash,
direct dependency proof, compatibility profile, and consumer stage.

`artifact_execution_plan_runs` is the durable plan/audit projection added by
reports migration 17. Reports migration 18 adds bounded source-publication
provenance; the rendered-HTML compatibility hash incorporates that record so
only rendering and downstream publication are invalidated. It stores
deterministic plan identity and both planned and observed work without
altering checkpoint storage. See [source publication metadata](../ops/source-publication-metadata.md)
for the extraction and fail-closed policy.
