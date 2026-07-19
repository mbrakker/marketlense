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
`legacy_unverified` or `legacy_incomplete`. The bounded backfill first audits
the retained record, hash, report/source identity, producer/schema/processing
versions, and deterministic dependencies. It promotes only checkpoints that
already retain every proof field; all other rows remain non-reusable, with a
bounded missing-field code rather than fabricated provenance. Repeating the
same backfill is idempotent.

| Change or observation | Invalidated family | Minimum required work |
| --- | --- | --- |
| Source bytes, parser, OCR, missing retained file, hash mismatch, or dependency edge | Changed artifact and descendants | Existing stage order from the earliest affected stage |
| Resolved canonical source metadata (v19) or template | Rendered HTML and downstream publication | Render only; no OCR, source parsing, analysis, artifacts, validation, or model client |
| Crop profile | Crop/preview and rendered HTML | Selection plus render; no report analysis |
| Prompt, schema, model policy, or validator | Affected analysis family and downstream outputs | Resume from selection plus analysis/render; preserve source PDF and selected crops |
| Publication target | Publication record | Publication only |

## Prompt-family materialisations

At the `analysis_complete` checkpoint, the report-generation orchestrator
persists separate, content-addressed family records through the report-store
lineage boundary. These cover the document map, each evidence pack, taxonomy
and category fit, each artifact prompt family, and grounding/semantic
validation. A record retains only bounded provenance in the lineage database:
family/schema/processing versions, prompt-content hashes, content-addressed
dependency manifests, execution identities, routing information, direct
dependency IDs and hashes, evidence-set hash, output hash, validation state,
and supersession reference. The prompt-content identity includes both YAML
roots, ordered partials, and schema snippets without timestamps or absolute
paths. The execution identity adds the resolved model/provider, generation and
token controls, retrieval, routing/compaction, output-contract, and validator
settings. The JSON output itself remains in the controlled report-analysis
output directory and is never put in operational logs.

Prompt-family records are reusable only when their validation status is
`pass`, all direct edges and hashes remain valid, and their family-specific
prompt/execution compatibility matches. An execution-identity mismatch rejects
reuse before provider work. Older rows remain readable and are explicitly
labelled legacy when they lack the new identity; they cannot satisfy a request
that requires current identity compatibility. Legacy composite `artifacts`
files remain valid checkpoint inputs but are not treated as proof that a
constituent family is independently reusable. The planner exposes `required_prompt_families` and
`reused_prompt_families`, allowing an operator to see the exact intended model
scope before a targeted repair. The existing checkpoint executor remains the
rollback path. In enforce mode, a proven artifact-family change resumes from
the active render checkpoint when present, regenerates only the planned
artifact families, re-runs grounding and semantic validation, then performs
deterministic rendering. The rendered-html lineage record explicitly depends
on the accepted prompt-family records. Any missing lineage, unsupported family,
validation failure, or planned/actual family mismatch fails closed.

The compatibility matrix in `tests/test_minimal_execution_planner.py` covers
each of these cases, deterministic plan hashing, targeted prompt-family
repair, render-only regeneration, crop repair, and publication-only retry.
It makes no provider calls.

## Integration and rollout

`run_report_pipeline` creates and persists a plan in `shadow` mode by default
before constructing model clients. Enforce mode now consumes these proven
checkpoint shapes:

- rendered HTML only resumes at `analysis_complete` and constructs no model
  clients;
- crop/preview plus render resumes at `source_prepared`, retaining source and
  analysis checkpoints and constructing no model clients;
- analysis/validator plus render resumes at `selection_complete`, retaining
  the source and selected crops; and
- a combined crop-and-analysis plan resumes at `source_prepared`, which still
  avoids source parsing and OCR.

Unsupported shapes and incomplete lineage fail before provider work. The
report pipeline acquires an artifact-scoped, 300-second lease for enforce-mode
work and releases it on success and expected failure. Its plan/actual audit
rejects any unplanned stage, external-call category, or side effect.

Legacy checkpoints that represent optional vector state as `null` are resumed
by re-establishing that vector resource from the retained source checkpoint;
they never fall back to PDF extraction or crop selection. A new immutable
lineage materialization supersedes prior records at the same report/family/path
and their active descendants, so the planner sees only the canonical active
graph rather than stale historical observations. Checkpoint lineage registers
dependencies before their dependents even when JSON serialization changes ref
order; source-publication metadata compatibility applies only to rendered HTML
and its downstream publication, never to retained source or analysis inputs.
Planning validates the requested output family and its transitive retained
dependencies; incomplete unrelated projections cannot block a safe repair.

`run_publish` creates a publication-repair plan before WordPress preflight.
In enforce mode, incomplete validated rendered lineage prevents preflight and
the WordPress write. Existing stable publication idempotency remains the
duplicate-write protection. Plan/audit rows retain planned stages, calls and
side effects; actual stages, calls, side effects, duration, reuse identities,
and deterministic reconciliation are recorded on completion.

The policy switch remains `shadow`, `enforce`, or `disabled`. Rollout is:

1. collect shadow plans and compare planned and actual work;
2. enforce the retained render, crop, and checkpointed-analysis families;
3. retain `shadow` as the rollback/observation mode and enable later families
   only after retained-fixture and bounded live evidence;
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
reports migration 17 and expanded by migration 20 with planned/actual side
effects, duration, actual and avoided cost fields, and reusable artifact
identities. Reports migration 18 adds bounded source-publication
provenance and migration 19 adds immutable canonical source-identity
observations plus their deterministic resolutions. The rendered-HTML
compatibility hash uses the v19 resolution (with a v18 fallback) so only
rendering and downstream publication are invalidated. It stores
deterministic plan identity and both planned and observed work without
altering checkpoint storage. See [source publication metadata](../ops/source-publication-metadata.md)
for the extraction and fail-closed policy.
