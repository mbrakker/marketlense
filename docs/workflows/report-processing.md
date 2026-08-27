# Report Processing

> **Documentation type:** Current reference
> **Canonical topic:** Report processing workflow
> **Update trigger:** Ingest, extraction, analysis, rendering, or checkpoint changes.

## Canonical report workflow entrypoints

`src/orchestrators/ingest_orchestrator.py::run_ingest` controls batch ingest. It delegates individual files to `src/orchestrators/ingest_file_orchestrator.py::run_ingest_file`, which validates source material and invokes `src/orchestrators/report_pipeline_orchestrator.py::run_report_pipeline`.

The pipeline delegates stage sequencing to `src/orchestrators/report_generation_orchestrator.py::run_report_generation`; the analysis stage is entered through `src/orchestrators/report_analysis_orchestrator.py::run_report_analysis`. Queue workers use explicit `stop_after_stage` boundaries so `source_prepared`, `selection_complete`, `analysis_complete`, and `render_complete` are durable handoffs rather than implicit direct chaining. The workflow extracts and validates report text, prepares evidence and visual candidates, generates structured artifacts, validates output, and renders the publication package. At analysis and render completion, independently verified prompt-family materialisations preserve family-level provenance; an enforced prompt-only repair reuses the retained source and unaffected families, then revalidates and rerenders locally.

`resume_from_stage` supports `source_prepared`, `selection_complete`, `analysis_complete`, `render_complete`, and `latest_safe` when the applicable retained checkpoint passes validation.

Regeneration-attempt lineage is part of the retained analysis checkpoint. A
resume preserves each candidate artifact location, candidate audit location,
and promotion outcome, so render/readiness evaluates the artifact that the
analysis stage actually promoted; a missing value in a legacy checkpoint keeps
the contract default rather than being inferred.

A render-only resume reuses report-card assets only when the complete validated
report-card manifest is also retained. If that manifest is missing, the renderer
regenerates the deterministic cover set and manifest before the package can
reach the blocking publication boundary; it never reports a package as ready
with orphaned card assets.

PDF previews, refinements, and crop regions keep fingerprint sidecars beside
their rendered artifacts. Concurrent workers may produce the same eligible
artifact, so each sidecar write uses a unique temporary file followed by an
atomic replace. A bounded retry absorbs transient Windows replacement
contention. This makes the cache race-safe without treating a missing sidecar
as a valid cache hit; an interrupted write is simply regenerated.
If a report pipeline still observes a missing local processing artifact, it
maps that OS-level condition to the configured bounded report-pipeline retry;
a persistent missing source or artifact remains a typed terminal failure.

Category selection is evidence-first. After the normal structured-output
recovery and one targeted category repair, a candidate that still has no
configured central support is explicitly recorded as an uncategorized
abstention. The report is not blocked and no portal category is invented;
the rejected candidate and its remediation status remain in the retained
category-fit audit payload. Publication readiness accepts only that exact
audited all-rejected outcome; an absent or malformed category assignment still
blocks publication.

Card titles retain the complete canonical title. The approved `xlong` scale
supports readable, normally spaced titles through 140 characters; only an
unbreakable token or a longer title is a render error, rather than silently
truncating public source metadata.

`ingest --force-report-cards` resumes from the validated analysis checkpoint,
not `latest_safe`, only when an existing rendered package has a missing or
invalid card manifest. It rebuilds that render/card package and avoids a second
analysis or model-generation pass. New files follow the normal pipeline and
therefore never request a nonexistent checkpoint.

A frozen-cohort replay receives one new, cohort-wide validation attempt number
with its previous attempt as parent. Every stage in that replay uses that same
lineage, so a recovered result supersedes a prior terminal failure without
mixing reports from different passes. Only a skipped result that explicitly
reuses a retained HTML package is eligible for a `publish_ready` closure;
state-only skips remain typed failures. A forced card/render repair also bypasses
the ordinary state “already processed” shortcut, so it can actually reach the
approved resume stage.

A completed render checkpoint is reusable only with an explicit passing
`publish_readiness` decision. A legacy, absent, or failed readiness decision
rejects that checkpoint and makes `latest_safe` fall back to an earlier validated
checkpoint; HTML existence never supplies readiness by inference.

If checkpoint lineage is subsequently found non-reusable, its retained processed
state does not suppress the next normal immutable-cohort replay. The ingest
selector explicitly returns that source to the repair path while preserving the
idempotent skip for reports whose retained readiness decision still passes.
When every `latest_safe` checkpoint is non-reusable, the repair pipeline starts
fresh from the already retained source PDF instead of consuming a rejected
checkpoint or aborting; the normal source, analysis, validation, and render
checks then establish replacement lineage.

The same render outcome fails closed when required report-card metadata, such
as publisher, fails public-metadata governance. Such a package remains a render
error with the typed reason and cannot be mistaken for a publication candidate.

Before rendering, a resolved canonical source identity supplies the title and
publisher when analysis or stored report metadata contains a generated
file/checksum name or a placeholder publisher. This is a deterministic
attribution fallback, not an inference: unresolved identities still reach the
same blocking public-metadata gate. A missing verified public source URL does
not block that package; the public attribution states `Source URL: Not
available`.

Public title selection rejects runtime file-name slugs and decodes URL-encoded
canonical, PDF-metadata, and document-map titles before they reach the HTML,
metadata record, or source attribution. The cover's core signal prefers the
ordered, grounded strategic implication of a final insight, then its ordered
factual claim. When the retained claim is too long, deterministic clause
selection keeps a short complete strategic clause (including a supported
outcome phrase) and never splits numeric thousands separators; generic signal
copy remains only for an absent usable claim.

Card-cover title layout preserves the complete normalized title. When an
title word or hyphen segment is wider than an empty title line, the deterministic
cover renderer may wrap it at character boundaries for visual layout; it never
truncates, replaces, or adds title content. The configured title rectangle and
minimum font size remain binding, so a title that still cannot fit fails with
the typed cover-title overflow rather than producing an unreadable asset.

Acquisition persists canonical source identity before its terminal telemetry
for every retained, hashable successful artifact: a downloaded PDF and a
verified on-site capture follow the same source-record and observation path.
A configured publisher carries both its stable `publisher_id` and display name
on the acquisition request. The stable ID is retained in source identity and
resource accounting so admission can enforce a per-publisher cohort limit
without inferring provenance from a Drive filename or folder. An artifact
without a known stable publisher ID is not eligible for that limited cohort.
An accepted email request has no artifact to hash, so its telemetry status is
`provisional` until mailbox delivery retains and verifies the attachment; it
is never treated as a resolved or cohort-eligible report merely because the
form submission succeeded.

When a selected browser-route playbook contains validated private-API evidence,
acquisition attempts its deterministic HTTP route before browser preflight,
browser launch, or Browser Use. Endpoint schema, method, repeated-success
evidence, accepted status, required response markers, JSON-pointer extraction,
and final PDF validation remain mandatory. Any stale, rejected, or unavailable
private-API result records its fallback reason and continues through the normal
browser acquisition route without changing promotion thresholds.

Browser-form blocker claims are untrusted terminal evidence. The
`blocked_missing_identity_field` classification is emitted only when
deterministic matching of the encountered required fields against the resolved
identity profile (including publisher overrides and semantic aliases) finds an
effective value missing. A model claim alone cannot suppress an otherwise
configured form flow.

For `browser_email_form`, before a Browser Use agent is constructed, the
browser service attempts standard visible text inputs, native selects, and
comboboxes using only the resolved configured identity profile (including a
publisher override). The deterministic browser payload retains every resolved
configured identity field, so a late publisher-specific required enum remains
available to its matching control. It can check required legal/report-delivery agreements,
but never optional marketing or newsletter choices. A required field or select
with no matching configured value returns the typed
`blocked_unknown_required_enum` result; the workflow never generates text,
chooses a first visible option, or guesses an identity value. Unsupported DOM
controls, page drift, and failed deterministic interaction retain the existing
Browser Use fallback.

When a browser route reaches a PDF, a current-session local PDF that passes
normal artifact validation is retained even when its filename differs from the
landing-page title, provided its filename ties it to a browser-observed PDF
URL. If no file was emitted, recovery may fetch a PDF URL only when the browser
itself observed it as a document request; ordinary unobserved URL
candidates still require report-identity matching. Both paths retain the
existing native-PDF validation rather than treating a browser claim as
successful acquisition.

The same deterministic pass runs directly on Browser Use's asynchronous
`BrowserSession`; it awaits the already-open preflight page rather than opening
another session or bypassing form handling because startup is asynchronous. If
it must fall back, the Browser Use Agent runs on that same event loop, rather
than through a second `asyncio.run()` lifecycle that would invalidate the
retained CDP session.

When a standard required select or combobox is unresolved but the configured
identity profile may directly support one of its visible options, the service
makes one constrained model call before Browser Use. The response must cite an
exact configured key/value and an exact observed option; both are validated
before the existing deterministic helper fills the control. An unavailable,
invalid, or ungrounded response preserves the typed blocker rather than
guessing or escalating the identity decision to Browser Use.

A deterministic submit records the actual terminal URL, title, and HTML rather
than asserting confirmation fields. The existing terminal-evidence finalizer
is the sole authority for accepting email delivery, so a visible confirmation,
form disappearance, URL change, or other established terminal evidence must
verify the submit before it is considered successful. A verified deterministic
form therefore incurs zero Browser Use model calls and is never submitted
again by the fallback path. An unverified, ambiguous, or unsuccessful submit
keeps the existing preflight browser session and continues to Browser Use from
that exact page state; only an unknown required identity value ends as the
typed blocker without a Browser Use call.

After repairing a required lookup, the browser helper recognizes the report
form's visible `Access`, `Unlock`, and `Resource` CTAs as submit actions, in
addition to conventional submit/download/send labels. It applies that matching
only on the discovered form and still requires terminal confirmation evidence.
When a route is promoted for reuse, failed or unverified actions remain in the
attempt audit but are excluded from the active playbook; only successful,
verifiable steps become reusable guidance.

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

Run a configured batch with `python -m src.cli ingest --attempt-limit 1`. The
selection controls have deliberately distinct semantics:

| Control | Meaning | Release/reliability use |
| --- | --- | --- |
| `--cohort-size N --cohort-manifest <path>` | Freeze exactly `N` admitted reports, persist the immutable ordered membership, and retain every later failure in the denominator. | Required mode. |
| `--attempt-limit N` | Process no more than `N` unique selected reports; an error remains an attempted result, not a missing success. | Bounded ordinary operation only. |
| `--success-target N` | Explicitly continue with later candidates until `N` reports succeed or no candidates remain. | Prohibited. |

`--limit` is a deprecated alias for `--attempt-limit`; it emits a migration
notice and cannot be combined with the first-class option. Every acquired source, including
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

New cohort manifests use schema `1.2`. Each member records its immutable
`report_id` (the Drive file ID), admitted `publisher_id`, canonical
`source_identity_id`, exact source-PDF MD5, and selection reason. The manifest
records the configuration hash, policy hash, cohort ID, derived validation-run
ID, and a redacted effective-configuration snapshot. Loading recomputes the
cohort and validation identities from those records, so an edited member list
fails closed rather than silently changing an existing cohort. Schema `1.0`
and `1.1` manifests remain readable for replay compatibility; schema `1.1`
retains a checksum in its historical `source_identity_id` field, so publication
uses that checksum for artifact compatibility while still rejecting stale source
metadata. A new membership must be frozen into a new schema-`1.2` manifest and
cohort identity.

If an interrupted run cannot recreate its configuration identity, do not alter
the original manifest or admit replacements. The canonical provenance-recovery
operation may create a distinct linked manifest only when its policy hash still
matches. A producer revision transition requires explicit operator opt-in and
is retained as such; it copies every immutable member unchanged, derives a new
validation-run ID from the current configuration, and retains the source
manifest, source identities, operator reason, and timestamp. The normal `ingest
--cohort-manifest <linked-path>` command then resumes that exact cohort.

The publisher accepted by admission is retained unchanged in every frozen-cohort
stage record and in the immutable member ledger; later processing must not
replace it with an `unattributed` fallback.

Publish a fixed cohort with the same `--cohort-manifest <path>` passed to
`publish-wp`. A frozen cohort automatically creates and retains a validation
run manifest. Its immutable member ledger is populated by discovery and is
checked independently of execution attempts, so a cohort report cannot vanish
from the final audit. Every stage record carries the validation and workflow
run IDs, cohort, report/source/publisher identity, attempt lineage, artifact
inputs and outputs, timestamps, typed result and retryability, repair and
supersession disposition, idempotency state, configuration and policy hashes,
and producer build identity.

An immutable validation run may contain bounded recovery replays, each with a
new workflow-run ID. Usage telemetry therefore requires a non-empty workflow
run ID plus exact validation-run and cohort identity; it does not require a
replay to impersonate the original workflow invocation. Configuration, policy,
and producer identities remain mandatory for every usage event.

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

Passing `--cohort-manifest` makes that immutable member set the authoritative,
one-to-one publish set before any WordPress operation; it is not merely an
outcome-recording argument. Each admitted member must bind to exactly one
existing, identity-compatible, publish-ready Report artifact, and every binding
must succeed before any WordPress write. A missing, duplicate, changed, stale,
incompatible, ambiguous, or unready member aborts the full cohort without
silently excluding it or admitting unrelated artifacts. The ordered binding and
its deterministic candidate-set hash are retained with the manifest/cohort and
configuration/policy identities; see [publishing](publishing.md) for the
artifact location and validation details. Authenticated WordPress lookup covers
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

Before the artifact generator enters this structured-output path, it checks
each independently retained artifact prompt family against its exact retained
provenance. The seven current routes are summary, candidate insights, quotes,
final insights, cover semantics, expert comment, and LinkedIn post. Reuse
requires a verified report/source identity, prompt and execution identities,
provider/model and model-policy namespace, schema/validator, semantic input,
configuration-policy, and output hashes, plus a passed validation state. A
missing or unverifiable record is a normal, explicit regeneration reason. The
generator retains bounded family telemetry with requested/reused/regenerated
families, reasons, avoided/actual model calls, token/cost usage, and available
provider-call duration. Reused outputs still pass deterministic assembly and
the normal report grounding, semantic, editorial, render, and publish-readiness
gates.

Vector-backed artifact reuse additionally requires a content identity composed
from the source, vector-store, provider-file, and indexing identities; absent
vector provenance disables reuse. A family that needed structured-output repair
or regeneration is retained without primary-family reuse proof, so a later run
regenerates it through the primary route before it can converge to reusable
state.

Each non-prunable, reference-bearing artifact response (candidate insights,
final insights, and quotes) is also checked against the canonical document map
and evidence packs before it leaves that bounded structured-output recovery
path. An unknown evidence identifier therefore supplies the recovery prompt
with the exact grounding error; it cannot be deferred until shared artifact
assembly. Summary claims remain deterministically prunable when no source span
can be bound. The final assembly grounding and semantic gates remain blocking
defence-in-depth checks.

When primary candidate-insight output is incomplete, the first-run deterministic
fallback selects only distinct findings with both a retained finding ID and
substantive finding text. The finding ID remains the evidence reference. If an
optional evidence excerpt is absent, the retained finding text is used as that
candidate's excerpt; no new claim or evidence ID is invented. Fewer than two
such grounded items remains a typed card-content failure rather than triggering
an ungrounded card insight.

Before the reference check, the artifact boundary deterministically resolves
only unambiguous source aliases to their retained canonical identifiers: case
and compact finding forms such as `F1` for `F1_digital_identity`, document-map
section forms such as `doc_map:section-1`, and the document source identifier.
Ambiguous aliases and identifiers absent from retained evidence remain unknown
and enter the bounded recovery path; no publisher-specific mapping or
ungrounded fallback is permitted.

If final-insight generation abstains after that reference check, its empty
result remains empty. Candidate insights may complete a partial substantive
final-insight response, but they never replace a safety abstention or an
unknown-evidence rejection.

If a model returns no candidate insights despite a generated findings pack,
artifact assembly uses up to five distinct findings that each retain a finding
ID, text, and source evidence. This first-run fallback does not invent
editorial claims or duplicate a weak candidate; it provides the final-insight
family with addressable grounded inputs before any regeneration is considered.

Insight padding never turns one grounded candidate into several apparently
independent claims. It retains each normalized text-and-evidence pair once and
uses empty slots for the rest; the existing family policy then records an
insufficient distinct-evidence outcome for bounded recovery or explicit
abstention rather than sending fabricated duplicates to validation.

The publish-readiness identifier gate targets identifier-shaped internal tokens
and private locations, not ordinary editorial language such as
“evidence-backed” or “evidence-linked.” This preserves the public safety check
without rejecting grounded prose solely for describing its evidence quality.
Identifier-shaped strings in a public source URL's `href` are likewise not
rendered identifiers; private Drive and local-location URLs remain blocked.

The summary's public card TLDR sentence contract is also checked inside that
same structured-output recovery path, rather than only after all artifact calls
have completed. Generated artifact payloads retain the canonical selected
category IDs separately from the human-readable category labels used to ground
prompts, so the publish-readiness category-consistency gate can compare the
same persisted assignment at analysis and render time. Public citation lines
may show report title and page references, but never internal evidence tokens
such as `quote_02`; those identifiers remain in private artifact lineage.

Category-fit reconciliation is deterministic after the model returns its
schema-valid candidate set. Each rule audit records its stable mapping-rule ID,
explicit configured semantic concepts, and the exact retained context labels
that support the rule. Exclusion rules can match only an explicit diminishing
concept in central context (`title`, `overview`, or `key_findings`); loose token
overlap and unreferenced model rationale cannot reject a category.

An evidenced exclusion deterministically rejects the candidate. Otherwise,
explicit configured inclusion support in the title, overview, or key findings
deterministically promotes a candidate to primary, regardless of the model's
advisory rejection or score. Supported but non-central high-confidence coverage
is normalized to secondary. This prevents a low-scored model false negative from
blocking an evidence-backed category. Selected category IDs are always derived
from those normalized decisions, never from the provider's advisory selection
list, and retain at most five independently central categories (one primary and
up to four secondary categories under the model contract).

A primary or secondary candidate without deterministic inclusion support, and a
high-confidence rejected candidate without enough evidence to resolve it, are
ambiguous. They trigger exactly one category-only semantic reclassification only
when no supported assignment survives; that repair is routed to its declared
ambiguous IDs plus already supported selections and cannot introduce another
category or discard a supported selection. When the model omits all candidates
but an unreturned configured category has explicit central inclusion evidence,
the deterministic mapper selects it before the report can be treated as
uncategorized. An exhausted recovery remains a typed failure; it never becomes
an empty successful analysis package. A response with no category candidates
likewise triggers the bounded recovery and then fails closed. By contrast, an
all-rejected, schema-valid candidate set is an explicit uncategorized outcome:
it is not mistaken for an empty model response during analysis. Publication is
nevertheless prohibited until both the canonical and retained category assignments
contain the same non-empty normalized category set. The canonical Technology & Innovation
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
