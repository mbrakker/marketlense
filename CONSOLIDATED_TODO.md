# Consolidated TODO

Last audited: 2026-07-17

This is the repository's single, source-neutral work register. Every task is evaluated by its current codebase evidence and project decision—not by where it was first proposed. Equivalent tasks are merged under one owner; deferred, closed, and excluded work stays visible in the same register.

## How to Use This Backlog

- An item is activated only after an owner, baseline, target, and review date are recorded in its implementation plan or issue.
- One item owns one outcome. Overlapping requests are merged here rather than tracked in parallel.
- Every implementation follows `AGENTS.md`: preserve role boundaries, use typed contracts, avoid placeholders and private-helper patching, and verify behavior with real boundary tests.
- Remove an item when every stated completion check is met. Move its short evidence to **Recently Closed**.

| Priority | Execution lane | Goal |
| --- | --- | --- |
| 1 | Autonomous safety and cost control | Make unattended runs inspectable, bounded, and recoverable. |
| 2 | Public trust and publishing | Make the public site accurate, safe, responsive, and ready for operator review. |
| 3 | Evidence quality and reuse | Turn retained evidence, embeddings, lineage, and crop QA into measurable decisions. |
| 4 | Release integrity | Make release evidence and architecture enforcement visible and reliable. |
| 5 | Boundary simplification | Reduce real control-plane and service complexity without behavior drift. |

## Unified Work Register

All work is listed below in one register. `Active` items have detailed completion checks in **Active Backlog**. `Deferred`, `Closed`, and `Excluded` are not lower-class sources; they are simply the current evidence-based outcome for the same planning standard.

| Status | ID | Work item | Current outcome / merge target |
| --- | --- | --- | --- |
| Closed | A1 | Single autonomous supervisor, read-only `PipelinePlan`, and mandatory workflow-control authority | Plan authorization is enforced by CLI/UI control payloads; retained plan run and full regression passed. |
| Active | A2 | `fast_ingest` and other config-driven autopilot profiles | One typed profile outcome. |
| Active | A3 | Workflow-wide remediation-ledger rollout | Extend the proven remediation ledger to every eligible workflow under explicit safety gates. |
| Active | A4 | Malformed-Drive-PDF quarantine | Standalone bounded source-recovery outcome. |
| Active | A6 | Budget-manager closeout and operational proof | Implementation is complete; collect bounded representative operational proof before closure. |
| Closed | A5 | Business-email, CAPTCHA, anti-bot, terminal-evidence, and avoided-browser-spend route policy | TTL-bound route policy now avoids browser/mailbox work for retained hard blockers and allows explicit revalidation. |
| Active | A10 | Budget-deferred-work recovery and operator requeue | Turn durable budget deferrals into safe, visible, idempotent resumption. |
| Active | A11 | Ledger-driven recurring-failure prevention and operator prioritization | Turn canonical remediation evidence into bounded root-cause and avoided-work decisions. |
| Closed | A7 | Budget-aware model routing, compaction, and failure-class fallback | YAML routing, anchor-preserving compaction, same-provider fallback, retained-corpus evidence gate, and regression coverage are active. |
| Active | A8 | Model-call replay drift comparison | Standalone read-only regression outcome. |
| Active | A9 | Source publication metadata and identity fallback for retained regeneration | Source-supported render metadata and deterministic identity-fallback outcome. |
| Closed | P1 | Publish snapshot naming and synchronous idempotent publishing | Public/UI terminology now says Publish Readiness; the compatibility alias preserves callers and synchronous review-gated publishing remains unchanged. |
| Active | P2 | Bounded public-observability events | Narrow log-event size-bound hardening for public-facing boundaries. |
| Active | P3 | Hosted HTTPS, sitemap, and public trust checks | Safe-error boundary completed; hosted trust outcome remains. |
| Active | P10 | Correlated public-render failure observability | Hosted release-observability outcome. |
| Active | P4 | Briefing, correction, and submission CTAs | Implemented; close after hosted smoke proves the live intake routes. |
| Active | P5 | Archive/search facets, mobile navigation, and responsive workflows | Responsive public-workflow outcome. |
| Active | P6 | Editorial report cards, exhibits, visual ranking, and premium copy | Public editorial presentation outcome. |
| Active | P7 | Hosted latency and public performance | Measured public-performance outcome. |
| Active | P8 | Readable evidence spans, methodology/source-quality trust, and deterministic related content | Public evidence/discovery outcome. |
| Active | E1 | Claim-embedding freshness, retention, and cost controls | Embedding operations outcome. |
| Active | E6 | Retain a hash-pinned claim-embedding benchmark export | Semantic benchmark coverage outcome. |
| Active | E7 | Expand planner-enforced artifact-family reuse beyond rendered HTML | Measured shadow-to-enforce rollout outcome. |
| Closed | E3 | Lineage-driven minimum regeneration | Remains closed; E7 owns expansion beyond the proven rendered-HTML family. |
| Closed | E4 | Executable retained PDF benchmark corpus in CI | Retained corpus is hash-pinned and CI-gated; local release-equivalent run passed. |
| Active | R1 | CI/PR release-evidence summaries | Reviewer-surface outcome, including exact-tested-HEAD linkage and runtime-corpus expansion. |
| Active | R2 | Role-mixing, import-graph, facade, direct-I/O, mutation-selection, and hygiene enforcement | Architecture enforcement outcome. |
| Active | R3 | Service-quality coverage recovery | Retained-baseline outcome. |
| Active | R6 | Bounded-log reduction telemetry and remediation review | Operator feedback outcome for attempted oversized standard events. |
| Closed | R5 | Hash-verified dependency lock artifacts | Native Ubuntu CPython 3.12 wheelhouse and offline hash-locked install are verified. |
| Active | S3 | PDF facade, rendering cache, and visual-heuristics simplification | Canonical PDF-boundary outcome. |
| Active | S4 | Semantic WordPress shortcode ownership | WordPress boundary outcome. |
| Deferred | D1 | Full report-generation DAG scheduler | Revisit when profiling shows material idle dependency time beyond simple parallelism. |
| Deferred | D2 | Streaming Drive prefetch queue and worker-safe PDF context pooling | Revisit when batches wait on Drive while worker capacity is idle. |
| Deferred | D3 | Adaptive concurrency and route-specific worker buffers | Revisit when sustained runs show throttling, SQLite contention, or browser saturation. |
| Deferred | D4 | Multi-provider failover | Revisit when outages create measurable failed-run volume or a service-level commitment requires it. |
| Deferred | D5 | Same-publisher warm workers/session reuse | Revisit when same-publisher volume justifies session-isolation risk. |
| Deferred | D6 | Generic pipeline-wide due-work scheduler | Revisit when deferred work beyond mailbox acquisition is sustained and material. |
| Deferred | D7 | Transactional publish jobs/outbox | Revisit when partial WordPress failures or retry recovery become recurrent. |
| Deferred | D8 | LinkedIn persona variants and comparative positioning | Revisit when an active distribution workflow measures their value. |
| Deferred | D9 | Golden-output prompt evaluation and broader prompt-family scoring | Revisit when the existing fixture corpus cannot detect a measured quality regression. |
| Deferred | D10 | Browser executor, static DOM scan, prompt-payload reduction, and route playbook tuning | Revisit when route telemetry identifies a measurable cost/latency gap not covered by A5. |
| Deferred | D11 | Root pre-commit, declarative quality-gate manifest, stricter mypy/Ruff, and hygiene scorecards | Revisit when current CI/quality-policy evidence proves a specific enforcement gap. |
| Closed | C1 | Cached-provider accounting reconciliation corpus | Real `provider_hit` fixture and cached-token tamper rejection are in the CI-covered ledger path. |
| Closed | C2 | Bounded multimodal crop-QA escalation | Typed escalation generator and deterministic no-model default are implemented and tested. |
| Closed | C3 | Lazy model construction, ranking/crop shortcuts, prefetch, and route prompt improvements | Landed behind existing boundaries with retained regression evidence. |
| Closed | C4 | Capability maps and autonomous release/remediation summaries | Generated capability maps and autonomous smoke evidence are present. |
| Closed | C5 | Prompt partials/schema snippets and prompt fixture regression | Landed with dry-run and corpus validation. |
| Closed | C6 | Core discovery, mailbox acquisition, signal persistence, and claim-embedding persistence | Durable paths, fallback behavior, and focused tests are present. |
| Closed | C7 | Logging content-exposure controls | Redaction, deterministic bounds, retained-content checks, and regression coverage are active; P2 and R6 retain hardening and monitoring. |
| Closed | C8 | CTO evidence-collector integrity | Snapshot, exact-HEAD, provenance, consistency, and inventory validation are implemented; R1 owns runtime-corpus expansion. |
| Excluded | X1 | Draft HTML published before enrichment | Public progressive enrichment is not permitted. |
| Excluded | X2 | Automatic lower private-API promotion thresholds | Conservative thresholds remain mandatory. |
| Excluded | X3 | Invented acquisition-form identity facts or public pipeline diagnostics | Only verified identity facts may be mapped; diagnostics remain operator-only. |

## Recently Closed

- **C8 — CTO evidence-collector integrity (2026-07-17):** The strict collector snapshots retained inputs, validates exact repository HEAD, checks log-content coverage, run IDs, provenance, summary consistency, and every inventoried file hash before publishing. It fails closed without a partial final bundle. R1 owns expansion of the retained runtime corpus, not collector integrity.
- **C7 — Logging content exposure (2026-07-16):** Standard events apply deterministic byte, depth, node, collection, and text bounds; report and browser terminal events emit scalar summaries with retained audit references; CI rejects direct `fields=asdict(...)` serialization. Focused report/logging and browser suites passed, as did guarded live browser and OpenAI runs. P2 retains the narrow public-boundary size-limit hardening and R6 owns ongoing reduction-telemetry review.
- **A7 (2026-07-14):** The retained 15-report corpus is now a required no-provider routing gate across 30 configured prompt routes. It confirms explicit policy selection, same-provider constraints, and zero lost retained evidence IDs; focused routing/compaction/fallback tests and the full suite pass.
- **R5 (2026-07-15):** The canonical lock records SHA-256 hashes for all 177 active Ubuntu CPython 3.12 artifacts, including `numpy==2.4.2` from its official manylinux wheel. CI installs with `--require-hashes`; a native official-PyPI wheelhouse passed an offline clean install, while a tampered NumPy hash failed before package installation.
- **R4 (2026-07-15):** Publication reads canonical SQLite usage plus projection status; normal bounded lag is accounted, while missing, invalid, or material lag stops the final public write without triggering a rebuild.
- **E5 (2026-07-15):** Retained crop-QA sidecars now form operator-only scorecards and selection telemetry, including deterministic quality/clipping/storage comparisons with no public diagnostic rendering.
- **E3 (2026-07-16):** Lineage-driven minimum regeneration is now the deterministic authority for report and publication repair. It captures current compatibility, persists plan/actual audits, fails historic provenance closed, exposes validated cross-report claim/evidence/summary/chart/metadata reads, and has a render-only enforcement path. A retained provider-backed full run completed in 208.51 seconds; the subsequent enforced render-only replay completed in 0.87 seconds with source, selection, analysis, model, projection, and WordPress work avoided. E3 remains closed; E7 owns all further artifact-family reuse expansion.
- **E2 (2026-07-15):** The retained-artifact benchmark reports Briefing and Signal prompt/token deltas, overlap, source/citation coverage, and explicitly records the deterministic fallback when no retained embedding export exists.
- **P9 (2026-07-15):** The retained public-advisory benchmark now compares a saved baseline and emits typed per-insight source-grounded repair proposals or explicit abstentions without altering public rendering.
- **S1/S2 (2026-07-15):** Canonical service-boundary and publish/ingest facade audits remain CI-enforced; focused decomposition regression coverage preserves the existing routing, retries, state transitions, and external-effect contracts.
- **P1 (2026-07-14):** `build_publish_readiness_snapshot` is the canonical UI/ops boundary, with the old queue-named callable retained only as a compatibility alias. Publish remains synchronous, idempotent, and review-gated; focused tests and the full suite pass.
- **Public WordPress safe-error boundary (2026-07-14):** Public shortcode rendering now returns a branded correlated HTTP 500 section on forced report, publisher, archive, or generic shortcode exceptions, while the private structured event retains exception details. The real local Studio route `/publisher/not-extracted/` changed from an incorrect 200 report archive to the branded 404; homepage, reports, and publisher directory remained HTTP 200 with no public diagnostic signatures.

## Screenshot Baseline Completion Evidence

The original ten-item screenshot baseline is complete in the committed implementation. Its broader successor work remains Active above only where it adds new scope beyond that baseline (for example hosted HTTPS in P3, full intake flows in P4, or visual screenshot comparison plus accessible mobile-menu interaction in P5).

- **Public quality gate (2026-07-14):** The real local Studio site passed the new Playwright-backed responsive gate on the homepage, reports archive, and a retained report detail at 390px, 768px, and 1440px: 9/9 checks had no horizontal overflow and no visible broken image. The same live site passed the public SEO/performance gate across seven public routes with HTTP 200, complete canonical/social metadata, and no configured threshold violations.
- **Core safety, budget, recovery, route-memory, lineage, retained-benchmark, WordPress projection, LLM routing, and publication-gate baseline (2026-07-14):** The implementation is covered by the committed typed contracts and control paths. A focused regression run passed 50 tests across run budgets, canonical LLM accounting, UI-run recovery, artifact lineage, publication, and retained report quality. The underlying A3/A6/E3 implementation evidence remains retained; A3 and A6 are active only for bounded rollout and operational proof, while E7 owns any E3 expansion.

## Active Backlog

### 1. Autonomous Safety and Cost Control

#### A2. Configured run profiles

- **Title:** Configured run profiles
- **Impact 4 / effort: 2**
- **Context:** Workflow control resolves some intents and preflight profiles today, but there is no complete, documented profile that consistently resolves approved low-level settings for common operating modes.
- **Benefit:** Safe defaults become repeatable across CLI, UI, and plan-first execution, while operators can choose an outcome rather than implementation details.
- **Risks to avoid:** Do not introduce a parallel configuration system or place secrets in YAML.
- **Success criteria:**

- YAML profiles cover `safe_default`, `fast_cached`, `repair_failed`, `publish_ready`, `browser_acquisition`, `cost_saver`, and `high_quality`.
- Profile resolution is typed, deterministic, logs effective settings, preserves override precedence, and never stores secrets in YAML.
- The plan-first interface can recommend or apply a profile, with tests proving deterministic resolution and invalid-profile failure.

#### A3. Roll out remediation-ledger coverage across workflows

- **Title:** Roll out remediation-ledger coverage across workflows
- **Impact 5 / effort: 2**
- **Context:** The remediation ledger is the canonical failure backlog. A 31-workflow inventory records coverage or explicit exemption, stateful boundaries retain typed recovery evidence, and execution fails closed outside the current allowlist. The remaining work is a controlled workflow-wide rollout, not greenfield ledger design.
- **Benefit:** Eligible workflows receive one inspectable, deduplicated recovery path without widening automatic execution or losing workflow-specific safety controls.
- **Risks to avoid:** Do not enable a workflow without its checkpoint, lineage, committed-side-effect, budget, input-checksum, idempotency, and runbook evidence. Preserve fail-closed behavior and existing public-write authorization gates.
- **Success criteria:**

- The generated inventory remains complete as production workflows change, and CI rejects an unclassified workflow or an expired exemption.
- Each newly eligible workflow passes a bounded read-only soak covering creation, deduplication, held/eligible transitions, and runbook linkage before it is added to the execution allowlist.
- Release evidence records the workflow coverage, allowed execution scope, and any held compatibility record without exposing source payloads or provider responses.

#### A4. Quarantine irreparably malformed Drive PDFs

- **Title:** Quarantine irreparably malformed Drive PDFs
- **Impact 4 / effort: 2**
- **Context:** Live ingest has encountered cached and redownloaded PDFs that remain structurally malformed; current behavior stops expensive work but does not preserve a durable, actionable source state.
- **Benefit:** Repeated malformed-source retries stop consuming Drive/API capacity, while operators receive a precise repair path after the source changes.
- **Risks to avoid:** Do not quarantine transient failures permanently; source replacement must be revalidated explicitly.
- **Success criteria:**

- State records file identity, checksum/size, typed error, and next action after PDF-integrity failure.
- Default ingest skips quarantined files; explicit rescan/revalidation clears only a valid replacement.
- CLI or dashboard exposes quarantined inputs and remediation guidance, with tests for write, skip, revalidation, and valid-replacement transitions.

#### A6. Complete budget-manager operational proof

- **Title:** Complete budget-manager operational proof
- **Impact 5 / effort: 2**
- **Context:** The canonical SQLite ledger already owns typed pre-side-effect decisions, TTL-bound reservations, actual-use finalization, deferrals, and avoided-effect telemetry for the configured costed operations. Focused tests and a guarded Drive list passed; the prior guarded OpenAI smoke reached the provider but exceeded its surrounding process deadline. The remaining work is operational closeout, not budget-manager implementation.
- **Benefit:** Operators can close the budget authority with representative evidence that reservations, reconciliation, deferral, and recovery hold under its real configured limits.
- **Risks to avoid:** Keep probes bounded, credential-gated, and non-publishing. Do not raise limits, bypass a pre-side-effect decision, or introduce a second accounting ledger merely to collect proof.
- **Success criteria:**

- A bounded, credential-gated operational run records one permitted decision and one safely denied or deferred decision, including reservation/actual reconciliation and the retained idempotency key.
- The evidence records configured request, token, duration, and cost ceilings; an unavailable credential or exhausted ceiling skips or fails safely without a completion claim.
- Release evidence links the operational result to the exact ledger schema/configuration and shows no unauthorized WordPress, mailbox, or browser side effect.

#### A10. Budget-deferred-work recovery and operator requeue

- **Title:** Budget-deferred-work recovery and operator requeue
- **Impact 5 / effort: 2**
- **Context:** The budget authority now persists actionable deferred work with its run, publisher, workflow, effect kind, limit, and next action. Operators can inspect that evidence, but there is no bounded reaper that rechecks capacity and idempotently requeues eligible work.
- **Benefit:** Capacity recovered through actual-use reconciliation or a new UTC day can turn into completed work without manual ledger archaeology, while preserving the same idempotency and side-effect ceilings.
- **Risks to avoid:** Do not create a generic queue or distributed scheduler. Reuse workflow control, require a fresh pre-side-effect decision, preserve original idempotency keys, and keep public writes review-gated.
- **Success criteria:**

- Workflow control lists pending budget deferrals with scopes, breached metrics, and actionable next steps in the operator surface.
- A bounded explicit reaper re-evaluates only eligible deferred records, claims them idempotently, and records completion, continued deferral, or terminal operator action.
- Tests prove day rollover, released reservation capacity, duplicate reaper suppression, failed requeue recovery, and zero public WordPress/mail side effects without their existing authorization gates.

#### A11. Ledger-driven recurring-failure prevention and operator prioritization

- **Title:** Ledger-driven recurring-failure prevention and operator prioritization
- **Impact 5 / effort: 2**
- **Context:** The canonical ledger now retains deduplication, held/eligible state, runbook coverage, and bounded side-effect evidence, but recurring root causes still require manual cross-record review.
- **Benefit:** Operators can prioritize the few failure classes that repeatedly consume time or provider capacity, and prevent known bad work before it enters expensive processing.
- **Risks to avoid:** Keep aggregation deterministic and redacted; do not create a scheduler, auto-resolve records, or suppress a source without a typed approval and expiry.
- **Success criteria:**

- A bounded read-only report groups retained remediation records by workflow, error code, action, and runbook status with scalar counts, age, and deduplication trend.
- The operator surface produces explicit prevention recommendations linked only to record IDs and retained evidence references; it never exposes source payloads or provider responses.
- Tests prove deterministic ordering, no cross-tenant/source leakage, threshold behavior, and that recommendations cannot trigger execution or hide historical transitions.

#### A8. Compare retained model-call replay bundles

- **Title:** Compare retained model-call replay bundles
- **Impact 4 / effort: 2**
- **Context:** Model-call replay bundles are retained, but comparing prompt, contract, evidence, and output changes currently requires manual inspection across artifacts and logs.
- **Benefit:** Regression evidence becomes reviewable without live calls, cost, or log archaeology.
- **Risks to avoid:** Keep comparison deterministic and bounded; do not invoke providers by default.
- **Success criteria:**

- The command compares deterministic fields, schema validity, prompt hashes, and selected evidence without provider calls by default.
- Output is bounded, reproducible, and links regressions to artifact family and remediation.
- Tests cover equivalent, changed, missing, and malformed bundles, including deterministic output ordering and zero-provider-call default execution.

#### A9. Capture source-backed publication metadata and identity fallback at acquisition

- **Title:** Capture source-backed publication metadata and identity fallback at acquisition
- **Impact 5 / effort: 2**
- **Context:** Retained report regeneration can safely reuse PDF, model, and render checkpoints, but older acquisitions may lack a source-supported publication date or a durable source identity and therefore fail the report-card gate during an otherwise render-only recovery. Runtime resolution can use an MD5 match and a constrained title/publisher fallback today; acquisition must make the selected source identity explicit and durable.
- **Benefit:** Acquisition provenance directly enables reliable low-cost regeneration and avoids broad reruns caused solely by absent public-card metadata or a lost source identity.
- **Risks to avoid:** Persist only source-page evidence with its URL and retrieval timestamp. Never infer a date from a filename, file mtime, or report title, and never turn an identity fallback into an ungrounded identity claim.
- **Success criteria:**

- Acquisition records normalized source publication date, source URL, retrieval timestamp, and evidence locator when the publisher exposes them.
- The selected source identity records its resolution source. Consumers prefer a checksum match, permit the constrained title/publisher fallback only when it is unambiguous, and retain an explicit unresolved outcome otherwise.
- Render and regeneration consume the persisted source-backed metadata and identity without an operator override; missing or contradictory evidence still fails closed.
- Retained-source tests cover metadata extraction, identity resolution, persistence, render-only recovery, absent evidence, ambiguous fallback, and conflicting dates.

### 2. Public Trust and Publishing

#### P2. Harden bounded public-observability events

- **Title:** Harden bounded public-observability events
- **Impact 4 / effort: 1**
- **Context:** Shared structured logging already has deterministic event-size limits and generic regression coverage, but public intake and public-render boundary events need a narrow contract check as their fields evolve. R6 owns aggregate reduction telemetry; this item owns the per-event size and content-safety guard at those public boundaries.
- **Benefit:** Public-facing workflows retain useful correlation and outcome signals without allowing a new high-cardinality field, user submission, or exception detail to make a standard event oversized or content-bearing.
- **Risks to avoid:** Do not create a second logger, retain dropped content, or expose private diagnostics in a public artifact. Use the canonical log schema and scalar summaries, hashes, or retained-artifact references.
- **Success criteria:**

- Public intake and public-render success/failure events remain at or below the canonical byte limit with maximum-size representative fields.
- Focused tests prove that oversized submissions and exception-like inputs preserve the correlation/outcome summary while omitting user text, paths, stack details, and discarded values.
- A bounded reduction remains visible to R6 without duplicating telemetry storage or changing the public response contract.

#### P3. Resolve hosted-site trust blockers

- **Title:** Resolve hosted-site trust blockers
- **Impact 5 / effort: 2**
- **Context:** Live public-site checks found HTTPS failure and HTTP sitemap URLs. The public rendering failure boundary and branded handling of the legacy `/publisher/not-extracted/` sentinel are complete.
- **Benefit:** Transport, safe errors, and reliable navigation meet the baseline expected of a trust-positioned research product.
- **Risks to avoid:** Verify staging and production separately and never disclose stack traces, paths, or diagnostics publicly.
- **Success criteria:**

- HTTP redirects to successful HTTPS; robots and sitemap URLs are canonical HTTPS.
- Hosted smoke evidence covers transport, representative pages, and sitemap behavior in both staging and production.

#### P10. Operate correlated public-render failure telemetry

- **Title:** Operate correlated public-render failure telemetry
- **Impact 4 / effort: 2**
- **Context:** The public shortcode boundary now emits the stable `marketlense_public_render_failure` event with a correlation ID, route, entity context, and private exception diagnostics, but hosted release evidence does not yet aggregate or alert on those events.
- **Benefit:** A bad public projection can be identified and repaired from one correlation ID before it becomes a repeated visitor-facing outage, without publishing diagnostic detail.
- **Risks to avoid:** Keep exception messages, traces, filesystem paths, and identifiers in private logs only; do not add a public diagnostics route.
- **Success criteria:**

- Hosted smoke records a bounded count of boundary failures and correlation IDs without serializing private exception fields into artifacts available to visitors.
- Release evidence distinguishes zero failures, expected injected failures, and unexpected render failures by route/entity type.
- Tests prove log redaction, deterministic aggregation, and that no public response or public artifact contains a stack/path signature.

#### P4. Close public briefing, correction, and submission intake

- **Title:** Close public briefing, correction, and submission intake
- **Impact 5 / effort: 2**
- **Context:** `Request a briefing`, `Send a correction`, and submission CTAs now collect structured requests through the approved boundary. The remaining closeout is hosted smoke evidence for the live routes, validation, delivery/persistence, and confirmation behavior.
- **Benefit:** Visitors can convert, correct, or submit sources through a trustworthy route that gives operators usable context, with closure based on the deployed behavior rather than implementation alone.
- **Risks to avoid:** Collect only necessary data, preserve redacted logging, and do not treat a local or simulated result as hosted proof.
- **Success criteria:**

- Correction and submission forms collect only the documented, necessary fields and present confirmation/error states.
- Requests use an approved service boundary with redacted structured logging.
- Hosted smoke checks prove each CTA route, validation, empty/spam rejection, successful persistence/delivery, and confirmation state in the deployed environment; then move P4 to Recently Closed.

#### P5. Finish responsive search and navigation

- **Title:** Finish responsive search and navigation
- **Impact 4 / effort: 3**
- **Context:** Visual QA found search overflow, cramped archive controls, an unfinished mobile menu, a stray list artifact, tall hero stacking, and clipped header-search text.
- **Benefit:** Search and navigation remain credible and usable on the screens where users actually discover and evaluate content.
- **Risks to avoid:** Do not alter archive-query semantics or projection contracts while changing theme behavior.
- **Success criteria:**

- No horizontal overflow, clipping, overlap, or unusable search/filter controls on homepage, search, archive, detail, contact, and submit views.
- Mobile navigation has accessible open/close and focus behavior with an intentional panel/backdrop.
- Retained visual-smoke screenshots cover each key view at phone, tablet, and desktop widths and are compared for regressions.

#### P6. Raise report-card and evidence-exhibit editorial quality

- **Title:** Raise report-card and evidence-exhibit editorial quality
- **Impact 4 / effort: 3**
- **Context:** Public cards and detail pages can expose raw OCR/table fragments, generic figure labels, weak thumbnails, duplicate summaries, and internal identifiers without reader-facing context.
- **Benefit:** High-value research reads as analyst-curated while retaining deterministic evidence provenance and auditability.
- **Risks to avoid:** Do not fabricate claims, hide evidence provenance, or remove auditability.
- **Success criteria:**

- Public copy rejects raw figure labels, OCR fragments, generic boilerplate, required-field placeholders, and internal identifiers.
- Blank/low-information thumbnails use deterministic covers or validated source previews.
- Audit identifiers remain available without being reader-facing labels; regression checks fail known leakage patterns in rendered output.

#### P7. Improve hosted public-site performance without contract loss

- **Title:** Improve hosted public-site performance without contract loss
- **Impact 4 / effort: 3**
- **Context:** The hosted gate measures stable SEO/performance baselines, but homepage, report archive, and signal archive response-start and DOM-complete values remain materially above documented targets.
- **Benefit:** Existing measurement drives real discovery and research performance gains rather than merely preventing further regression.
- **Risks to avoid:** Do not weaken metadata, public contracts, archive completeness, or projection boundaries to gain speed.
- **Success criteria:**

- Homepage, reports, briefings, signals, methodology, contact, and submit pages improve against `config/public_site_baselines.yaml` without increased page weight or request count.
- Remaining target gaps are measured and documented.
- Hosted evidence confirms canonical URLs, Open Graph, Twitter metadata, archive completeness, and representative page contracts remain intact after optimisation.

#### P8. Complete concise public evidence, methodology, and related-content surfaces

- **Title:** Complete concise public evidence, methodology, and related-content surfaces
- **Impact 5 / effort: 3**
- **Context:** Rendering already redacts canonical IDs and exposes claim-support labels, but lacks a compact source/excerpt/limitation contract and the first useful approved relationship links.
- **Benefit:** Decision-useful evidence and discovery improve trust while keeping OCR, model, crop, and vector diagnostics operator-only.
- **Risks to avoid:** Remain concise and source-grounded; fail closed when approved data is missing.
- **Success criteria:**

- Claim support can show source report, publisher, page, concise excerpt, limitation, and original link where approved.
- Methodology shows scope, source pages, material limitations, and evidence state.
- Report pages start with deterministic related report, briefing, topic, and publisher links; tests prove redaction and fail-closed behavior when approved data is absent.

### 3. Evidence Quality and Reuse

#### E1. Operate claim embeddings with freshness, retention, and cost visibility

- **Title:** Operate claim embeddings with freshness, retention, and cost visibility
- **Impact 4 / effort: 2**
- **Context:** Claim embeddings persist locally with status and provider metadata, but operators cannot yet see stale content, failed attempts, model-version drift, retention state, or avoidable re-embedding spend in one actionable view.
- **Benefit:** Embedding drift becomes visible before it degrades evidence selection or cost, and unchanged content avoids unnecessary provider calls.
- **Risks to avoid:** Keep reporting lightweight and do not create another dashboard surface without an action path.
- **Success criteria:**

- A concise report groups embedded, pending, failed, stale, and model-mismatched claims by publisher/report/topic.
- Retention/pruning policy is documented and tested.
- Unchanged rows are skipped with cost-avoidance telemetry; failures retain retry visibility; tests cover reporting, pruning, retries, and skip accounting.

#### E6. Retain a hash-pinned claim-embedding benchmark export

- **Impact 4 / effort: 2**
- **Context:** The semantic-selection benchmark correctly falls back when a retained corpus has no persisted vectors, so it cannot yet measure real semantic ranking on the fixed corpus.
- **Benefit:** A bounded, redacted export makes semantic quality and prompt savings reproducible without live embedding calls.
- **Success criteria:** Persist a hash-pinned, retention-governed benchmark export containing only approved vector IDs/content hashes/vectors; benchmark it in CI and compare semantic coverage against lexical fallback without provider calls.

#### E7. Expand planner-enforced artifact-family reuse beyond rendered HTML

- **Title:** Expand planner-enforced artifact-family reuse beyond rendered HTML
- **Impact 5 / effort: 3**
- **Context:** The lineage planner now produces fail-closed plans for crop, targeted analysis, and publication repair, while only the proven rendered-HTML family is enabled for stage skipping. The remaining families stay in shadow to preserve current stage contracts.
- **Benefit:** Measured evidence can safely extend avoided provider calls, crop work, and WordPress preflight/write work without introducing a general DAG scheduler.
- **Risks to avoid:** Do not enable a family from synthetic evidence, downgrade missing-lineage blockers, or permit a plan to fall back to unplanned provider work.
- **Success criteria:**

- Shadow audits provide retained-fixture and live evidence for crop, prompt-family, validator, and publication plans, including zero unplanned calls for each candidate executor.
- Crop repair is enabled only after it reuses validated analysis artifacts; targeted prompt repair preserves unaffected artifact families; publication repair verifies the current target without a public write when provenance is incomplete.
- Each family has an explicit rollback switch, bounded live canary, plan/actual divergence threshold, and regression coverage before enforcement.

### 4. Release Integrity and Architectural Enforcement

#### R1. Publish release-evidence reviews where reviewers work

- **Title:** Publish release-evidence reviews where reviewers work
- **Impact 3 / effort: 2**
- **Context:** Release-evidence review Markdown is generated and archived, but reviewers must open the artifact bundle to learn approval status, owners, expiry dates, and unwaived issues. Strict CTO evidence already validates a clean, exact repository HEAD; that exact-tested-HEAD linkage and the expansion of its retained runtime corpus are not yet consistently surfaced in CI/PR review.
- **Benefit:** Release readiness, the exact tested revision, and the scope of runtime evidence are visible where reviewers already work, reducing missed evidence and review latency.
- **Risks to avoid:** Keep summaries bounded and links stable while preserving all unwaived issue detail. Do not imply that a smoke-only corpus proves representative report processing.
- **Success criteria:**

- CI appends bounded review Markdown after approval gating, including the exact tested HEAD or an explicit unavailable/mismatch result.
- PR/release automation links the bundle, final approval status, and exact tested HEAD to the reviewed commit.
- The retained runtime corpus expands under the existing strict collector with declared scope/provenance; inline review distinguishes representative processing from smoke-only evidence.
- README distinguishes inline review from full archived evidence, and tests cover bounded summaries, exact-HEAD mismatch, runtime-corpus scope, and unwaived detail retention.

#### R2. Enforce role boundaries, direct-I/O discipline, and controlled module growth

- **Title:** Enforce role boundaries, direct-I/O discipline, and controlled module growth
- **Impact 4 / effort: 3**
- **Context:** CI enforces imports, forbidden patching, direct `fields=asdict(...)` rejection, coverage, and mutation, but role mixing, direct-I/O drift, service-integration coverage, facade thickness, and long-file growth are not yet uniformly executable.
- **Benefit:** Architectural constraints prevent drift before merge instead of relying on manual review and retrospective refactors.
- **Risks to avoid:** Use narrow, expiry-owned waivers and avoid noisy generic governance checks.
- **Success criteria:**

- Gates target first-party files and require owner/expiry for every waiver.
- Service integration-test absence is a failure unless explicitly waived.
- Documentation explains adding and retiring a waiver; tests prove violations fail and valid waivers expire as intended.

#### R3. Restore service quality coverage above the retained baseline

- **Title:** Restore service quality coverage above the retained baseline
- **Impact 4 / effort: 3**
- **Context:** Full-suite service coverage is 82.5763%, above the enforced floor but below the retained 82.9680% snapshot after accounting, browser, PDF, and lineage service growth.
- **Benefit:** The retained quality baseline continues to reflect real protection for durable external and stateful boundaries.
- **Risks to avoid:** Add behavior tests with observable contracts or state; do not weaken floors, add exemptions, or add coverage-only paths.
- **Success criteria:**

- New behavior-focused coverage prioritizes ledger recovery, browser-worker lifecycle, and artifact-lineage failure paths.
- Assertions cover returned contracts or persisted state, not coverage-only paths.
- The quality baseline is refreshed only by a passing full CI run, records its exact SHA, and demonstrates no reduction in global/generator/orchestrator coverage.

#### R6. Review bounded-log reduction telemetry and remediate recurring callers

- **Title:** Review bounded-log reduction telemetry and remediate recurring callers
- **Impact 4 / effort: 2**
- **Context:** Standard structured logging now bounds nested values and emits `log_payload_reduced` only when an event exceeds the byte contract, but operators do not yet aggregate those events to distinguish legitimate high-cardinality summaries from callers that still attempt to serialize domain payloads.
- **Benefit:** Repeated source/model/browser payload attempts become measurable remediation work, preserving useful operational summaries while reducing log volume and accidental content-retention risk.
- **Risks to avoid:** Aggregate only bounded metadata, hashes, event/module identifiers, and counts; never reconstruct discarded content or create a second unrestricted log store.
- **Success criteria:**

- Release evidence reports reduction-event count, event/module grouping, attempted-size percentiles, and zero-content samples.
- A thresholded review identifies recurring callers and links them to an owner or remediation item without exposing discarded values.
- Tests prove deterministic aggregation, redaction preservation, and that the scorecard cannot contain source text, prompts, model output, browser terminal text, or credentials.

### 5. Boundary Simplification

All work in this lane is movement-only unless behavior change receives explicit approval. Public facades, order, retries, idempotency, logs, and side effects must remain stable.

#### S3. Simplify the PDF visual-heuristics boundary

- **Title:** Simplify the PDF visual-heuristics boundary
- **Impact 4 / effort: 4**
- **Context:** PDF visual extraction has accumulated facade re-exports, rendering/cache concerns, and heuristic helpers that can obscure the single canonical external/library boundary.
- **Benefit:** A smaller semantic surface keeps the PDF capability navigable, replaceable, and testable without scattering external-library access.
- **Risks to avoid:** Preserve candidate/crop outputs, artifact paths, and the one canonical external/library boundary.
- **Success criteria:**

- Remove unnecessary re-exports and forwarding chains without changing callers or outputs.
- Keep visual heuristics capability-owned and testable behind the canonical PDF boundary.
- Equivalence tests preserve candidate/crop behavior, artifact paths, cache semantics, and benchmark signatures.

#### S4. Give WordPress shortcodes semantic ownership

- **Title:** Give WordPress shortcodes semantic ownership
- **Impact 4 / effort: 4**
- **Context:** The WordPress shortcode class owns several unrelated public surfaces, making it difficult to isolate presentation changes and trace a shortcode to its feature contract.
- **Benefit:** Shortcode behavior becomes understandable by stable feature ownership rather than one catch-all class.
- **Risks to avoid:** Do not add navigation-only layers or alter public hooks/output during a movement-only refactor.
- **Success criteria:**

- Each extracted unit owns a coherent shortcode family and documents why the boundary reduces coupling.
- Public shortcode behavior, output, and WordPress hooks remain unchanged.
- PHP/runtime tests cover each public surface and compatibility facade, proving unchanged output and hook registration.

## Guardrails

- Never normalize cross-publisher metrics with incompatible definitions, geography, methodology, or time period.
- Never publish incomplete public pages for later enrichment; preview/draft is allowed only outside the public release surface.
- Never invent identity attributes for acquisition forms; map only configured, verified values.
- Never lower private-API promotion thresholds automatically.
- Never publish OCR, model, crop, vector, or validation diagnostics as public product content.

### Non-negotiable publishing guardrail

Automation may plan, resume, retry, repair, validate, render, draft, hold, and notify. It must not public-auto-publish until retained evidence demonstrates safe claims, no internal-ID leakage, stable crop acceptance, stable WordPress updates, duplicate suppression, rollback, and consistent editorial quality.

## Current-State Evidence

- A1 plan-first authority is now typed and checksum-bound across CLI/UI control payloads. A retained publish plan emitted no external mutation; a live zero-item publish invocation authorized before correctly failing local missing-credential validation; the full suite passed 3,888 tests in 461.92 seconds.
- A5 acquisition hard-blocker policy now reuses TTL-bound publisher route history, checks configured identity/mailbox facts, and avoids browser/mailbox work for fresh exact CAPTCHA/domain blocks unless `revalidate_route_policy` is explicitly requested. A retained CAPTCHA record confirmed the behavior; focused route/acquisition tests passed 40/40.
- Canonical LLM accounting uses SQLite with deterministic JSONL/daily projections, reconciliation, replay suppression, task-median forecasting, and configured OpenAI day guardrails.
- The retained CI accounting corpus now includes valid, invalid, replay-suppressed, and real cached-provider (`provider_hit`) events; cached-token tampering is rejected by reconciliation tests. This closes the former cached-provider corpus task.
- Claim embeddings, stale/no-embedding fallback, bounded semantic preselection, durable Signal artifacts, artifact lineage storage, and lineage invalidation are present.
- Workflow-control intent/preflight, UI dead letters, mailbox acquisition, resume checkpoints, prompt dry runs, provider decisions, and deterministic JSON-chat compaction are present.
- Public report rendering exposes approved advisory/metric-spine data while redacting canonical IDs; strict crop acceptance emits typed QA sidecars.
- WordPress report, briefing, and signal entities have REST draft/readback verification; `sync-wordpress-intelligence` now projects 64 retained local public entities (47 reports, 5 briefings, 12 signals, and 29 publishers) through the authenticated plugin route, while missing/invalid projections render neutral values. Hosted HTTPS/error handling, intake, responsive UI, and editorial leakage remain active public-site gaps.
- CI runs formatting, typing, architecture/import checks, forbidden-patching checks, hygiene, coverage, mutation, prompt regression, release-evidence archival, hash-pinned PDF candidate/crop/trend gates, public report-quality gates, and WordPress staging verification when configured.

## Audit Notes

- This register replaces duplicated simplification context, migrated x100 intake, and repeated launch plans with source-neutral status rows. No task is excluded because of its origin.
- The active backlog contains 25 outcome-owned items. Deferred, closed, and excluded rows remain visible above; any newly discovered work must be merged into an existing outcome or justified as a new one.
