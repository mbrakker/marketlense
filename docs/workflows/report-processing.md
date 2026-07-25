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

The same render outcome fails closed when required report-card metadata, such
as publisher, fails public-metadata governance. Such a package remains a render
error with the typed reason and cannot be mistaken for a publication candidate.

`region` and `covered_period` are optional card labels: placeholder, extraction
leakage, and prose-like values are deterministically omitted before manifest
validation, while a placeholder publisher or extraction leakage in required
metadata remains a blocking error. This prevents internal labels from reaching
WordPress without inventing metadata.
The report-card contract permits those omitted optional labels and renders an
unknown geography rather than manufacturing a period or location.
When a covered period is a complete month-by-month list, the card image uses
its deterministic first-to-last month range so the fixed small cover remains
readable; the complete period is retained in the manifest and HTML.

Run a configured batch with `python -m src.cli ingest --attempt-limit 1`. An
attempt limit counts selected reports, including failures; it never continues
selecting replacements to meet a success count. `--limit` remains a deprecated
alias with the same attempt-limit meaning. Every acquired source, including
ordinary and success-target ingest, passes one deterministic admission
preflight after local acquisition and before vector-store creation, evidence
generation, OCR, or editorial model work. It verifies the retained artifact,
supported PDF type, parser structure, checksum identity, exact duplicate and
non-blocking near-title signal, active quarantine, bounded native text,
configured size/page limits, a non-public Drive-source classification, stable
title fallback, publisher sentinel, required evidence-family potential,
runtime paths/dependencies, model-policy coverage, and a bounded budget
forecast. The typed outcome is one of `admitted`, `duplicate`,
`unsupported_document`, `corrupt_source`, `insufficient_content`,
`missing_source_identity`, `policy_blocked`, `budget_blocked`, or
`quarantined`. Each decision retains the preflight version, configuration and
policy identities, deterministic decision hash, and bounded inspection and
forecast values. It does not create a vector store.

The report-pipeline entrypoint fails closed without that retained decision
hash. The durable report queue performs admission only for the first source
stage, retains the decision in the funnel, and carries its identity through
later checkpoint payloads; a legacy checkpoint without the identity is
admitted before it can resume. This prevents repeated text inspection while
also preventing a vector-store or editorial call on an unadmitted source.

Rejected sources return a skipped ingest outcome and are written to a retained
`out/admission/<run>-<decision-set>.json` acquisition/admission funnel. Fixed
cohorts also embed that decision set in their immutable manifest. They are not
admitted cohort members and therefore never enter the ingest reliability
denominator. A normalized title match remains only an operator
signal: the workflow never merges different content identities merely because
their titles are similar.

Release and reliability validation use `--cohort-size N --cohort-manifest
<path>`: files first pass that same admission, then the exact admitted IDs are
atomically persisted before report-generation work begins. The ordered
candidate pool continues only while this pre-manifest admission has fewer than
`N` accepted sources; a rejected candidate is retained in the manifest funnel
but is not silently included. After the manifest is written, no failure can
trigger a replacement. Re-running with only `--cohort-manifest <path>` replays
the same immutable members without a Drive reselection. A malformed manifest,
duplicate member, size mismatch, rejected admission candidate cannot enter the
cohort, and an insufficient eligible population fails closed. Admission
prefetches each selected source PDF and carries its deterministic local MD5
into the cohort member when the Drive listing omitted that metadata. The same
value is checked against PDF integrity before the manifest is frozen; it is not
inferred from a title or replaced with a non-content identifier. A filename is
optional in the metadata-only listing mode and is used only as an additional
duplicate signal; it is resolved later when presentation needs it, never
treated as required source identity.
`--success-target N` is the only explicit mode allowed to select later
candidates after a failure; it is prohibited for release/reliability rates.
Publish a fixed cohort with the same `--cohort-manifest <path>` passed to
`publish-wp`. A frozen cohort automatically creates and retains a validation
run manifest. Its immutable member ledger is populated by discovery and is
checked independently of execution attempts, so a cohort report cannot vanish
from the final audit. Every stage record carries the validation and workflow
run IDs, cohort, report/source/publisher identity, attempt lineage, artifact
inputs and outputs, timestamps, typed result and retryability, repair and
supersession disposition, idempotency state, configuration and policy hashes,
and producer build identity.

The required chain is discovery, candidate qualification, acquisition,
admission preflight, source preparation and validation, evidence generation,
structured-output repair, taxonomy, category fit, artifact generation,
regeneration, grounding and semantic validation, rendering, final HTML
validation, ingestion, publication preflight, WordPress lookup and write,
authenticated readback, and repeat publication. A blocked downstream stage is
recorded explicitly when a terminal earlier failure makes it unsafe to run.
Each admitted report must finish with exactly one current state:
`published_verified`, `publish_ready`, `blocked`, `permanent_failure`,
`abstained`, `cancelled`, or `superseded`.

For the final repeat, pass `--require-full-validation-manifest`. It rejects a
closure with a missing terminal state, incorrect current-attempt overlap,
unreconciled cohort/current/terminal totals, a missing cohort member, duplicate
source identity, or an ambiguous WordPress lookup. A terminal outcome by itself
is not enough: for a `published_verified` report the second, unchanged
publication must retain a successful `repeat_publication` stage with reused
idempotency and no write. An ambiguous WordPress lookup blocks before any
WordPress create or update operation.

Passing `--cohort-manifest` also scopes publish candidate selection to that
immutable member set before WordPress lookup, taxonomy resolution, or writes;
it is not merely an outcome-recording argument. This keeps a validation run
from touching unrelated report artifacts. Authenticated WordPress lookup covers
every visible status, including drafts, so a repeat can verify and reuse a
sandbox-draft post without creating a duplicate. A cohort's initial creation
also reads its exact returned post ID before its outcome is recorded.

All required model-generated JSON artifacts use
`structured_output_service`, including document maps, taxonomy, report context
category fit, evidence packs (findings, methods, limitations, scope and quote
candidates), report artifacts (summary, insights, expert commentary, LinkedIn
material and cover semantics), and model-backed grounding and semantic
validation output. The service requests provider JSON Schema constraints when
the endpoint supports them, then applies Unicode and fence normalization,
deterministic extraction/parsing, contract normalization, one deterministic
JSON repair, one model repair using the original response plus exact errors,
and one source-evidence regeneration. Every attempt writes a bounded audit
event with report ID, artifact family, attempt, error class, provider/model,
token/cost usage, and disposition. Empty or malformed output cannot be stored
as a successful artifact. A schema-valid explicit insufficient-evidence result
may abstain only for a downstream family contract that represents abstention;
required non-abstainable families finish as a typed permanent failure when the
bounded sequence is exhausted.

Category-fit reconciliation is deterministic after the model returns its
schema-valid candidate set. Each rule audit records its stable mapping-rule ID,
explicit configured semantic concepts, and the exact retained context labels
that support the rule. Exclusion rules can match only an explicit diminishing
concept in central context (`title`, `overview`, or `key_findings`); loose token
overlap and unreferenced model rationale cannot reject a category.

A rejected category above the configured
`high_confidence_fit_threshold` is promoted to primary when an inclusion rule
is supported, its category concepts are central, and no evidenced exclusion
matches. Supported but non-central high-confidence coverage is normalized to
secondary. An evidenced exclusion deterministically rejects the candidate.
Selected category IDs are always derived from those normalized decisions, never
from the provider's advisory selection list.

A primary or secondary candidate without deterministic inclusion support, and a
high-confidence rejected candidate without enough evidence to resolve it, are
ambiguous. They trigger exactly one category-only semantic reclassification
routed only to their declared category IDs; that repair cannot introduce another
category. An exhausted recovery remains a typed failure; it never becomes an
empty successful analysis package. A response with no category candidates
likewise triggers the bounded recovery and then fails closed. By contrast, an
all-rejected, schema-valid candidate set is an explicit uncategorized outcome:
it is not mistaken for an empty model response. The canonical Technology & Innovation
rules explicitly cover reports whose dominant subject is immersive experiences,
spatial computing, virtual worlds, or Metaverse technology.

Candidate ranking deterministically splits each candidate kind into at most
four-item batches, then uses zero-temperature structured output with a bounded
4,096-token completion allowance. This preserves a complete JSON result for
every candidate without silently truncating a large batch. Concurrent ranking
calls obtain distinct ledger ordinals;
an occupied derived-projection lease is logged as a bounded deferral while the
canonical SQLite event remains the source of truth and the workflow finalizer
materializes the projection.
Use `--rescan` only when the normal cursor should be bypassed. Queue operations and checkpoint recovery are
documented in [asynchronous workflow queue](../architecture/asynchronous-workflow-queue.md).
See [validation and regeneration](validation-and-regeneration.md), [artifact
model](../architecture/data-and-artifact-model.md), and
[configuration](../ops/configuration.md).
