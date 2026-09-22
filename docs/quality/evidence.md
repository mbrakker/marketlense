# Evidence Process

> **Documentation type:** Current reference
> **Canonical topic:** Quality and release evidence
> **Update trigger:** Evidence manifest, review, waiver, retention, or release-review process changes.

Release evidence is generated from executed quality-gate artifacts; it is not hand-maintained in the README. The evidence tooling creates a manifest with artifact identity, schema expectations, freshness, and commit context, then produces a review against the waiver policy.

`test_telemetry_ci.json` and `ci_performance_benchmark.json` are mandatory
release-review inputs, not merely archived diagnostics. The telemetry records
the exact repository SHA and release run ID supplied to the pytest producer;
the benchmark carries that provenance forward and exposes both `passed` and
the legacy-compatible `quality_passed` result. The machine-derived
`release_evidence_executive_summary_ci.json` repeats only scalar status claims
from those two artifacts. The review fails when pytest exited nonzero, any test
failed, either benchmark status is false, the summary contradicts the machine
evidence, or the manifest and required inputs do not share exactly one commit
SHA and run ID. Waivers cannot turn a failed manifest or failed machine input
into a passing release review.

Use the repository scripts `scripts/quality/release_evidence_manifest.py`,
`scripts/quality/build_release_evidence_summary.py`, and
`scripts/quality/release_evidence_review.py` with the arguments required by CI
or the release procedure. Retain generated manifests and reviews in the
configured output/artifact mechanism. The waiver policy is
[`release_evidence_waivers.yaml`](release_evidence_waivers.yaml).

CI also runs `scripts/quality/generate_workflow_queue_evidence.py` against a temporary SQLite database. It requires an expected full commit SHA, checks that HEAD is unchanged before and after generation, and records only queue record IDs and scalar counts. The fixed scenario proves submission, lease/start, completion, one downstream outbox event and materialisation, expired-lease recovery, a bounded retry, a budget deferral, and a dry-run publication-approval handoff. The artifact is required in the release manifest and is included in `release-evidence-bundle`.

This deterministic queue evidence confirms queue semantics at the exact tested revision; it does **not** demonstrate live production throughput, provider behavior, or a public WordPress write. The GitHub job summary explicitly preserves that distinction and bounds any listed unwaived issues.

For operational diagnostics, use structured logs and retained workflow artifacts first. See [monitoring](../ops/monitoring.md) and [recovery](../ops/recovery.md).

## Repair-effectiveness evidence

The validation reliability artifact retains a cohort-compatible, content-free
repair scorecard when regeneration candidate audits include exact
run/cohort/configuration/policy/build identity. Its rows contain stable
failure, strategy/evidence, and candidate fingerprints; typed repair deltas;
validator rule classes; promotion/rollback/removal/scope outcomes; and bounded
usage and latency totals. Prompt identity is namespace plus hash only. The
artifact does not
retain source text, rendered prompts, or provider responses.

The read-only reliability exporter writes this retained projection as
`repair_effectiveness.json`. A missing or incompatible sidecar, or unavailable
usage attribution, is explicitly `unavailable` with `null` metrics. It must
not be represented as a zero-cost or zero-success repair cohort.

The current frozen A21 measurement and its complete retained evidence are in
[`reliability-cohort-20260920-a21-final/`](reliability-cohort-20260920-a21-final/).

The bounded workflow-queue foundation record is retained in
[workflow-queue-foundation-evidence-2026-07-18.md](workflow-queue-foundation-evidence-2026-07-18.md).

## CTO Review Evidence Bundles

`scripts/quality/collect_cto_review_evidence.py` creates a point-in-time CTO-review bundle from retained state. A strict CTO review uses an exact repository HEAD, not merely the best-effort Git marker retained by legacy collection.

Run the strict operator procedure from the repository root after representative report processing has completed. The `FRESH_AFTER` value is an operator-provided, timezone-aware timestamp for that review run; use a current value, not a permanently checked-in date.

```bash
HEAD_SHA="$(git rev-parse HEAD)"
FRESH_AFTER="<current-run-start-ISO-8601>"
python scripts/quality/collect_cto_review_evidence.py \
  --state-dir state \
  --artifact-dir out \
  --log-dir logs \
  --output-dir docs/CTO_evidence \
  --expected-commit-sha "$HEAD_SHA" \
  --require-exact-head \
  --fresh-after "$FRESH_AFTER" \
  --log-corpus-scope representative_report_processing \
  --minimum-source-canaries 5 \
  --minimum-editorial-canaries 5 \
  --include-github-status \
  --replace-output
```

Strict mode resolves a full 40-character HEAD before snapshots and again immediately before finalization. It requires the expected, starting, and ending SHAs to match and the worktree to be clean at both checks. Git metadata being unavailable, a dirty worktree, an invalid or mismatched expected SHA, or a moving HEAD all fail the run. This proves the bundle-generation code came from one clean repository revision. Standard structured log contexts additionally retain a producer commit when `MARKET_LENSE_PRODUCER_COMMIT` is supplied, but a collector revision and a historical producer revision remain distinct evidence.

The final check excludes only the collector's own temporary staging directory when that directory is created beneath the repository. Any other tracked or untracked worktree change still fails strict collection.

The `--log-corpus-scope` operator declaration states what the snapshotted corpus represents: `representative_report_processing`, `post_remediation_smoke_only`, or `not_declared`. Strict representative processing requires timezone-aware `--fresh-after` before any snapshot; omission fails rather than creating a false pass. The leakage artifact records `freshness_state` as `passed`, `failed`, `unverified`, or `not_required`, separately from the content-leakage result. The collector verifies snapshots and content coverage, not that a claimed workflow was actually run. A smoke-only bundle explicitly states that no representative report-processing workflow was executed and must not be presented as evidence of that workflow.

For an isolated historical run whose canonical logs were not retained in that
namespace, use `--allow-unavailable-run-logs` with an empty run-owned log
directory. This preserves strict repository, database, artifact, and canary
integrity checks while recording log-content and freshness evidence as
`unavailable`; it never substitutes repository-wide logs or claims a leakage
pass.

Every database is snapshotted with SQLite's backup API before querying; live WAL files are never copied. The collector snapshots the retained crop and report-analysis JSON evidence inputs under `--artifact-dir` before either metrics or canaries are read. It does not treat unrelated benchmark or runtime sidecars as CTO-review inputs. The collector copies only canonical `market_lense_YYYY-MM-DD.log` files from `--log-dir` into the same workspace and scans only those immutable copies, line by line. Snapshot provenance records normalized source-relative and temporary-relative paths, sizes, hashes, source modification time, parsed event timestamp bounds, line/event counts, and accessibility. Noncanonical files are ignored. In strict mode a discovered standard log that cannot be copied is a failure.

Acquisition and browser CSV metrics are derived from the task-scoped `reports.acquisition_attempt_resources` records, not from legacy `publisher_download_route_history`. They retain publisher, route family, terminal outcome, elapsed time, cost, Browser Use model calls and tokens, browser launches and activity, retries, and mailbox/Drive activity. Legacy route history remains historical routing evidence only and is not a fallback input for current acquisition metrics.
An execution-level `terminal_outcome=success` counts as a verified acquisition
only when the same resource record has a nonempty `verified_artifact_hash`.
Email requests and other successful route executions without a normal verified
artifact therefore remain visible in route telemetry but never inflate
acquisition success, rate, or cost-per-verified-acquisition metrics.

The log-content assessment takes deterministic representative samples from two categories:

- source-report text from retained page/source-style fields, source-backed evidence-pack excerpts, and document-map section summaries;
- generated editorial text from retained `artifacts.json` fields such as LinkedIn posts, expert comments, TLDRs, and executive summaries.

It normalizes Unicode and whitespace, rejects short, boilerplate, placeholder, title-only, and identifier-only fields, then deterministically orders and spreads selected paragraphs across reports. Defaults require five source and five editorial canaries, with at most 25 in each class. Missing canaries, no standard logs, or no log at or after `--fresh-after` produce `incomplete`; they never become a zero-match pass.

Raw snapshotted log lines are compared deterministically, including unstructured and JSON-escaped records. A match is either a whole normalized paragraph or two independent long windows from the same paragraph in one log record. The evidence never stores a paragraph, matching log line, raw source, or raw editorial text. It stores only bounded metadata, normalized-text hashes, and redacted match location and structured-event identifiers.

The existing CSV filenames remain stable. The collector additionally writes:

- `detailed_metrics.json`: finalized structured input for summary derivation;
- `executive_summary.json`: totals derived only from that finalized detail;
- `snapshot_manifest.json`: database, retained-artifact, and standard-log snapshot provenance;
- `log_content_leakage.json`: versioned canary coverage and redacted matching result (`passed`, `failed`, or `incomplete`);
- `evidence_run_manifest.json`: exact repository provenance, configuration, snapshot-manifest hash, and canonical file inventory with byte counts and SHA-256 values;
- `consistency_validation.json`: compact checks, exact-head outcome, repository SHA, and finalized run-manifest hash.

The JSON CTO artifacts carry one `evidence_run_id` and one `repository_commit_sha`; the manifest binds stable CSV names through the same inventory. It records the collector Python/OS separately from bounded producer-commit observations in historical structured logs; historical producer runtime version is explicitly `not_retained` when absent. The run manifest intentionally does not hash itself. Instead, `consistency_validation.json` records the finalized run-manifest SHA after independent validation, avoiding a circular hash. Public output paths never include a workstation root or username.

The canonical output location is [`docs/CTO_evidence/`](../CTO_evidence/README.md). In addition to the existing integrity, log-leakage, detailed, summary, and CSV artifacts, every bundle writes these machine-readable CTO artifacts:

- `workflow_to_remediation_coverage.json`, `artifact_lineage_completeness.json`, and `architecture_manifest.json` for commit-bound repository evidence;
- `source_identity_schema.json`, `editorial_rule_catalog.json`, and `effective_run_profile_matrix.json` for the public policy and configured execution surface;
- `github_main_status.json` for the exact tested commit's check/PR state, the latest main commit, and their explicit revision-match relationship when `--include-github-status` is passed; and
- `runtime_telemetry.json` for acquisition, browser, cost, OCR, crop, plan-divergence, deferred-work, remediation, embedding, WordPress, editorial-quality, and public-page evidence.

The lineage artifact reports each family separately: total, active, superseded,
complete-active, active-only completeness, all-history completeness, required
field missing counts, and processing/schema version distributions. Incomplete
historical rows are not silently promoted; reuse remains blocked unless the
canonical lineage boundary can prove every required field.

The collector reports a metric as `available`, `partial`, `empty`, or `unavailable`. `partial` and `unavailable` are explicit retained-data limitations, not zeroes or inferred successes. In particular, the current stores do not prove per-report browser traces, cache hit/miss rates, cost attribution across every side effect, WordPress duplicate/rollback rates, human editorial ratings, or hosted public-page telemetry until those values are retained by their owning boundaries.

Execution-plan telemetry reads the production writer's
`divergence_json.reconciliation_status` as the canonical result. A populated
reconciliation object is normal for both matches and divergences. Older rows
without that status are compared using unordered planned/actual stages, call
categories, and side effects: only unplanned work diverges; malformed or
incomplete historical values remain explicitly `unreconciled`.

All files are first created in a temporary staging directory. The collector validates snapshot integrity, exact-head state, log-content result, summary consistency, run IDs, repository SHAs, and every inventoried file hash before publishing. It will not merge into an existing output directory; use `--replace-output` for an explicit replacement. A failing strict run leaves no partial final bundle. Temporary workspaces are removed after success and failure unless `--debug-retain-snapshots` is set; retained debug workspaces are operator diagnostics and are not publishable evidence.

For release evidence, add the passed CTO JSON artifacts through the generic manifest command. The embedded repository SHA is checked against the requested release commit when `--require-head-commit` is used; a failed leakage artifact is therefore a normal unwaived `artifact_failed` release issue.

```bash
python scripts/quality/release_evidence_manifest.py \
  --release-id "<release-id>" \
  --artifact cto_log_content_leakage=docs/CTO_evidence/log_content_leakage.json \
  --expected-schema cto_log_content_leakage=1.0 \
  --artifact cto_consistency=docs/CTO_evidence/consistency_validation.json \
  --expected-schema cto_consistency=1.0 \
  --require-head-commit
```

Ordinary CI runs the collector and release-evidence unit/contract tests but does not synthesize retained databases, report artifacts, or logs merely to manufacture a passed CTO bundle. The real strict bundle remains an operator/review action against retained state.

For a frozen validation cohort, `scripts/quality/export_reliability_run_evidence.py`
projects terminal-outcome, failure-detail, Pareto, aggregate-funnel, and audit
views directly from the production-derived `cohort_result.json`; it does not
reconstruct terminal state from a separate exporter query. Regenerate those
frozen outcome views without live work using:

```powershell
python scripts/quality/export_reliability_run_evidence.py \
  --cohort-result <retained-cohort_result.json> \
  --output-dir <retained-evidence-export>
```

The exporter also supports run-specific funnel, recovery, publication, and
cost-attribution views beneath that bundle. It is read-only with respect to
runtime state and exports bounded identifiers and scalar metrics only. It must
not be used to infer a successful publication when publication-stage records
are absent.

For frozen-cohort and run-scoped terminal failures, `failure_details.json`
additionally projects the retained actionable cause when available: `stage`,
`outer_code`, `inner_error_class`, `validator_rule`, `artifact_family`,
`claim_or_entity_id`, `repair_attempt`, and an allowlisted bounded
`error_context`. The projection is built only from the validation-manifest
artifact and remediation record already produced by the canonical workflow;
it does not inspect runtime logs or rerun validation. The reader scans the
failing validation stage records newest-first and keeps scanning past terminal
checkpoint records whose artifacts carry no validation-issues document, so the
generic `validation_failed` outer code surfaces the retained inner validator
finding (rule, affected section/family, claim or entity ID, and bounded repair
attempt) instead of exporting an empty diagnostic. The context accepts only
short identifier-like values (for example rule, field, schema, component, and
evidence IDs). Prompt text, provider/model responses, source text, exception
messages, file paths, and arbitrary error-context values are excluded. For
soft-copy coverage and reference failures, the retained context additionally
includes the bounded `missing_claim_count` and up to three unknown
`missing_references` identifiers, so each terminal record names its exact
uncovered-sentence count or unknown evidence IDs.

The exporter writes `validation_terminal_outcome_missing` for every immutable
member without a current typed terminal attempt and marks that evidence
incomplete; a blank terminal row is never treated as a successful or excluded
report. A measured frozen cohort is submitted as one production cohort and
requires a clean 40-character Git SHA before its supervisor drain begins.
The retained `cohort_result.json` records that SHA at its top level. Batch
usage, elapsed duration, automatic-repair, and operator-intervention metrics
are retained as cohort-scoped totals; member records retain report-specific
terminal evidence and use null numeric fields with
`metric_attribution="unavailable"` when report-level telemetry was not
retained. Aggregate repair rates are likewise `unavailable` unless the
underlying repair records are report-attributable.

Benchmark and reliability evidence MUST use the standard, already-produced
discovery, acquisition, ingest, analysis, render, and publication flows and
their retained logs, state, and artifacts unless an operator explicitly
requests a nonstandard diagnostic flow. A diagnostic harness may inspect or
export those records, but it must not substitute bespoke workflow behavior for
the production path being measured.

The same canonical validation-reliability artifact separately retains the
legacy eventual/current-attempt funnel and an A21 first-attempt funnel through
the durable `awaiting_review` boundary. A21 readiness requires both successful
retained `publication_preflight` evidence and a successful canonical
`workflow_publication_readiness` record linked by immutable package checksum to
the report's completed `publication_readiness` queue job; ingestion alone is
not readiness. An explicit retained approval for that same checksum preserves
the prior achieved readiness boundary after the mutable readiness row becomes
`approved`; approval without the linked completed readiness job cannot create
readiness. The report ID and package checksum must also be bound to the same
immutable workflow lineage: the validation run and each accepted stage record
must carry the same `workflow_run_id` as the matched queue job's
`root_workflow_id`. Missing or mismatched lineage produces no A21 readiness,
approval, retry, or requeue evidence. A first pass is the recovery-aware
completion of that boundary
by an entity's earliest retained non-out-of-cohort attempt; a later success,
automatic repair, targeted regeneration, structured-output repair, or explicit
operator requeue never changes that result. For every report and transition,
the artifact records the first failure code and stage, eventual success,
attempts required, recovery classification, operator-intervention flag,
terminal disposition, verified-replay flag, and
provider calls/tokens/cost through successful recovery. `bounded_recovery`
includes a successful linked later attempt or a retained automatic repair
disposition within attempt 1. A retryable `publication_readiness` queue attempt
that reaches retained `retry_wait` and is followed by a successful later queue
attempt is likewise bounded recovery and retains its queue failure code in the
first-attempt Pareto. Explicit queue `operator_requeue` / `queue-requeue`
transitions are operator intervention, not bounded recovery; automatic retry,
redelivery, and restart remain automatic classifications. `verified_replay` is
true only for a successful retained zero-write `repeat_publication` record with
canonical reuse evidence; ordinary cache or idempotency reuse is not replay
verification. Missing usage-ledger attribution is represented by
`usage_attribution="unavailable"` and null numeric fields, never zeroes.

`first_attempt_failure_pareto` is a deterministic one-cause-per-lost-report
count, sorted by descending count then code, with canonical transition pairs.
It uses the earliest retained failure where present and stable generic codes
for repair-only, operator, incomplete-transition, and missing-readiness cases,
so successful intra-attempt repairs cannot vanish from causal accounting. It
does not alter the legacy `failure_pareto`, which remains the all-attempt
failure view. Building or writing this artifact reads only retained SQLite
manifest, queue/readiness-state, and LLM-ledger records; it makes no provider,
browser, Drive, mailbox, or WordPress call.
Canonical JSON ordering and an artifact hash over the complete payload make
identical retained inputs byte- and hash-equivalent.

### A21 frozen `bfab37bb` retained-evidence closure

The deterministic regression fixture
[`tests/fixtures/a21_bfab37bb_evidence_closure.json`](../../tests/fixtures/a21_bfab37bb_evidence_closure.json)
records the 12 affected members from frozen revision
`bfab37bbd1e4c194c027f14dd54817fb61f940a6`. This closure is read-only:
it does not rerun the 20-report cohort or infer an unretained model output.

All seven `schema_reference_missing` members stopped in the first
`report_analysis.editorial_plan` family before a rendered artifact family was
retained. Their retained source packs use canonical references in namespaced
form: zero-padded finding IDs (Bigcommerce, Activate), unpadded finding IDs
(StackAdapt, Criteo, DHL eCommerce, Mintel), a slug finding ID
(DoubleVerify), and quote-candidate IDs using underscore or hyphen forms.
The source pack is evidence of the reference forms available to the family,
not the discarded raw model field. The artifact boundary canonicalizes each
form in `editorial_plan.themes[].evidence_ids` before the existing strict
reference validator runs; an unknown identifier remains unknown and is still
rejected. The fixture exercises every retained report/pattern against that
boundary.

Of the five historical `workflow_queue_report_stage_failed` members, retained
render evidence recovers `publish_readiness_failed` for Contentstack
(`publish_readiness.repeated_boilerplate`) and Deloitte
(`publish_readiness.editorial_quality` and
`publish_readiness.source_fidelity`). KPMG and Capgemini had passing retained
readiness artifacts, which proves only that their missing historical value was
a non-readiness report-card error; its typed code was not retained. Reuters
has neither a retained readiness artifact nor the underlying report-render
value. The latter three are explicitly `unresolved` in the fixture rather
than classified by guesswork. Current queue terminal evidence preserves an
available typed report-pipeline code; no common production root cause is
proven by the two recovered readiness failures.

The retained LLM ledger and surviving artifacts also isolate the six remaining
structured-artifact/provenance members without recovering or retaining raw
model prose. Bain's two artifact attempts were provider-parse-valid JSON whose
private soft-copy bindings failed semantic coverage after the shared bounded
recovery sequence. SimilarWeb's three limitations attempts were likewise
parse-valid but normalized to an empty optional list without the existing
formal-abstention reason. Robeco and Algolia reached artifact assembly with
valid model bindings, then a source-display correction could change public
soft-copy after that binding check. Adjust's unsupported numeric claim had no
claim ID, so E13 could not select its sentence and reconstructed the family.
Qualtrics had valid initial bindings but its claim-scoped LinkedIn regeneration
prompt simultaneously required a one-sentence replacement and a full
180–280-word post.

The production boundaries now formalize an empty limitations list as
`limitations_not_found`, apply source-display preservation before soft-copy
binding validation, attach the retained soft-copy claim ID to numeric validator
failures, and separate E13 claim-scoped LinkedIn replacement requirements from
full-post requirements. The final shared structured-output regeneration now
carries its immediately preceding repair response as untrusted context, which
may be invalid or incomplete; source evidence remains authoritative for any
correction or provenance rebinding. These changes retain the existing shared
recovery and E13 rebind paths: valid artifacts remain unchanged, recoverable
binding drift is re-rendered through the bounded sequence, and an irrecoverable
payload remains terminal. The evidence does not contradict E11: each relevant
provider response was already JSON-parse-valid, so the failure was semantic or
post-normalization rather than a regression in E11 structured-output parsing.

Before any live A21 canary, the deterministic full-chain A21 gate must pass:

```powershell
python -m pytest -q tests/test_validation_queue_lineage.py -k "a21_full_chain"
```

It creates a frozen one-report cohort and exercises the durable queue/outbox,
handlers, manifest, checkpoints, report/state databases, validation,
claim-scoped regeneration, rendering, publication readiness, and A21 builder.
Its clean fixture proves first-pass `awaiting_review`; its repair fixture proves
one unsupported soft-copy claim can recover without rewriting valid sibling
copy or requesting an operator requeue. Both rebuild the same A21 artifact and
require identical bytes and SHA-256. The fixtures mock only external
provider/browser/Drive/WordPress boundaries, do not publish, and are a
mandatory precondition rather than a substitute for the separately authorized
live canary.

### Final A21 frozen 20-report validation — 2026-09-19

The final bundle in
[`reliability-cohort-20260919-a21-final/`](reliability-cohort-20260919-a21-final/)
reused the exact immutable cohort and source hashes from official baseline
`bfab37bbd1e4c194c027f14dd54817fb61f940a6`. It made one fresh isolated
production submission from clean, CI-green
`c89c545d649a2852f4602b8ddbfa4c09a8c39e18`, retained 20/20 admissions and
typed terminal outcomes, and made no WordPress publication attempt or operator
intervention.

First-attempt `awaiting_review` and publication readiness improved from 2/20
(10%) to 5/20 (25%), but missed the A21 targets of 19/20 and 18/20. Four final
packages were ready without targeted editorial regeneration; one used a
bounded targeted repair. All 15 typed failures, stage conversion,
repair/regeneration, provider usage, tokens, cost, duration, source-manifest
identity, and ready-package editorial/factual inspection are retained. The
remaining failure Pareto is led by `schema_reference_missing` (6) and
`artifact_structured_output_invalid` (4); no result was waived, rerun, or
reclassified.

### Targeted real-report replay — LinkedIn provenance fix verification — 2026-09-20

The bundle in
[`reliability-replay-20260920-linkedin-provenance-fix/`](reliability-replay-20260920-linkedin-provenance-fix/)
retains six canonical one-attempt production replay rounds (baseline
`9c1146dd` through fix `0fd194d8`) for the frozen-cohort members targeted by
the LinkedIn soft-copy provenance fix, including the Adjust regression
control. Verbatim per-member runner results and their SHA-256 hashes are
committed in [`results/`](reliability-replay-20260920-linkedin-provenance-fix/results/),
with canonical `--cohort-result` exporter projections per round under
[`evidence-export/`](reliability-replay-20260920-linkedin-provenance-fix/evidence-export/).
The evidence records that ten of the eleven baseline failures plus the control
reached `awaiting_review` under the fixed code, that Mintel remains blocked by
source-PDF glyph corruption, and that single-run model variance flips
borderline reports between rounds. Contentstack's former model-provenance
classification was superseded by the clean, one-member replay retained below;
it reached `awaiting_review` without a publisher exception, weakened
validation, automatic repair, or operator intervention.

### Targeted real-report replay — Contentstack E13 verification — 2026-09-20

[`reliability-replay-20260920-contentstack-e13/`](reliability-replay-20260920-contentstack-e13/)
retains the sanitized terminal outcome of a fresh isolated production-queue
run for the immutable Contentstack source `source:ac8915b43ea20012f9da2bf3c8150b9f`
at `c2df11a5`. The normal submit, supervisor, validation, render, and
publication-readiness path completed in one workflow attempt: validation and
publication readiness passed and the result reached `awaiting_review`. The
record is an outcome measurement, not a claim that an individual model call is
deterministic; it corrects the prior conclusion that Contentstack was a stable
non-repairable pipeline/model-contract blocker.

### Targeted real-report replay — E13 deterministic and adaptive repair — 2026-09-22

[`reliability-replay-20260922-e13-deterministic-repair/`](reliability-replay-20260922-e13-deterministic-repair/)
retains the completion evidence for the remaining E13 repair scope at
implementation SHA `dda61ad4`: deterministic canonical corrections (report
identity, exact quotes, protected insight metric fields) with zero model
calls, the fixed `metadata.title` repair routing, the bounded typed
compatibility scorer replacing lexical-only alternative-evidence ranking, the
materially distinct strategy ladder with actual-strategy/evidence
fingerprints and executed-planned-key rejection, and deterministic
candidate→final insight factual preservation. All five targeted frozen-cohort
reports (Bigcommerce, Capgemini, DHL, SimilarWeb, Contentstack) retained
`awaiting_review` terminal outcomes with zero operator interventions, and the
record retains the live intermediate rounds that exercised the identity and
protected-metric repairs and exposed (and verified the fix for) the repeated
deterministic-strategy hole. The record also documents the pre-existing
artifact-finalization blocker
(`soft_copy_claim_provenance_bindings_incomplete` /
`soft_copy_claim_provenance_coverage_invalid`) that stochastically fails some
rounds before analysis; it is owned with the A21 soft-copy stream, not with
E13.

### Reusable sanitized acquisition-assessment projection

When a completed acquisition assessment has a retained raw current JSONL and a
comparable retained baseline JSON, use
`scripts/quality/acquisition_evidence_projection.py` to make the diagnostic
views reviewable from the committed evidence directory. This is a read-only
evidence transformation: it **must not** rerun discovery, acquisition, browser
automation, mailbox polling, or any downstream stage.

The inputs are the exact current JSONL, the exact baseline JSON containing its
`records` list, and the known SHA-256 of the current JSONL. Retain the output
under `docs/CTO_evidence/<assessment>/sanitized_projection/`:

```text
python scripts/quality/acquisition_evidence_projection.py \
  --current-jsonl <retained-current>/acquisition_attempts.jsonl \
  --baseline-json <retained-baseline>/baseline_replay.json \
  --output-dir docs/CTO_evidence/<assessment>/sanitized_projection \
  --expected-current-sha256 <retained-current-sha256>
```

The generated canonical projection contains only candidate and publisher IDs,
tested commit/configuration hashes, route, terminal reason, derived failure
class, and the safe `blocked_reason`, `blocker_state`, `submission_state`, and
`confirmation_state` enums, normal artifact verification/source-format fields,
scalar duration/browser/Agent/token/cost/
mailbox/Drive metrics, and aggregate views. It omits URLs, local paths,
screenshots, form values, raw browser content, and model output. It writes a
per-candidate projection, failure Pareto, route metrics, baseline-versus-
current metrics, remaining failures, and a consistency record. The consistency
record proves the input hashes, candidate counts, exact candidate-set equality,
and agreement between the remaining-failure list and aggregate metrics.

When the canonical acquisition result carries a typed blocker, the projection
uses that blocker as its terminal reason rather than falling back to a generic
outcome. In particular, `blocked_static_archive` carries the derived
`external_source_unavailable` failure class; it is not reported as
`email_required`.
Only a typed `blocked_*` machine label is retained as `blocked_reason`.
`blocker_state` maps approved labels to safe categories such as
`missing_identity`, `unknown_required_enum`, `form_validation`, `captcha`,
`email_domain_rejected`, and `static_archive`; it never retains field names,
identity values, or route prose. Submission and confirmation states are
similarly limited to safe lifecycle enums, including `not_submitted`,
`submitted`, `submission_unconfirmed`, `delivery_confirmed`, and `blocked`.

An input-hash mismatch is a hard error. A candidate-set mismatch remains
explicit in the output so an assessor can diagnose it, but the baseline and
current run are not comparable and must not be used to claim an improvement.
Commit the resulting views, their input references/hashes, and the invocation
in the assessment README; do not commit the raw JSONL when it contains
non-sanitized runtime data.

The retained partial record for the 2026-08-13 frozen 20-report run is
[reliability-run-2026-08-13.md](reliability-run-2026-08-13.md). It records a
blocked sandbox publication target explicitly and is not release evidence.

## A9/A3/A6 representative operational evidence

Before a strict bundle used to close source provenance, remediation, or budget
authority work, regenerate the two matrices, retain a read-only remediation
soak, and run the credential-gated provider smoke when its opt-in is present.
The provider smoke is a bounded real call; a missing credential or opt-in is a
blocked validation, never a synthetic substitute.

```powershell
python scripts/quality/generate_remediation_coverage.py
python scripts/quality/generate_budget_authority_coverage.py
python -m src.cli remediation-soak
$env:RUN_OPENAI_SMOKE_TEST = "1"
python -m pytest tests/integration/test_openai_smoke.py -m integration -q
```

Record the run ID, report/source IDs or hashes, decision statuses, reservation
reconciliation status, and persisted actual-use counts in the evidence notes.
Do not include source HTML, report paragraphs, prompts, provider responses, or
credentials. The strict collector remains the exact-head authority for the
resulting snapshots and log-content assessment.
