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
| Closed | A3 | Workflow-wide remediation-ledger rollout | The 31-workflow coverage matrix, fail-closed bounded reaper, read-only soak, and strict retained evidence bundle passed. |
| Active | A4 | Malformed-Drive-PDF quarantine | Standalone bounded source-recovery outcome. |
| Closed | A6 | Budget-manager closeout and operational proof | Live Drive, OpenAI vector-store, and LLM calls recorded actual use; next governed calls were stopped before provider I/O and strict evidence passed. |
| Closed | A5 | Business-email, CAPTCHA, anti-bot, terminal-evidence, and avoided-browser-spend route policy | TTL-bound route policy now avoids browser/mailbox work for retained hard blockers and allows explicit revalidation. |
| Active | A10 | Budget-deferred-work recovery and operator requeue | Turn durable budget deferrals into safe, visible, idempotent resumption. |
| Active | A11 | Ledger-driven recurring-failure prevention and operator prioritization | Turn canonical remediation evidence into bounded root-cause and avoided-work decisions. |
| Closed | A7 | Budget-aware model routing, compaction, and failure-class fallback | YAML routing, anchor-preserving compaction, same-provider fallback, retained-corpus evidence gate, and regression coverage are active. |
| Active | A8 | Model-call replay drift comparison | Standalone read-only regression outcome. |
| Closed | A9 | Canonical report-source identity and publication provenance | Schema v19 immutable observations, deterministic source resolution, safe public projection, render-only invalidation, and live idempotent source capture passed. |
| Closed | P1 | Publish snapshot naming and synchronous idempotent publishing | Public/UI terminology now says Publish Readiness; the compatibility alias preserves callers and synchronous review-gated publishing remains unchanged. |
| Active | P2 | Bounded public-observability events | Narrow log-event size-bound hardening for public-facing boundaries. |
| Active | P3 | Hosted HTTPS, sitemap, and public trust checks | Safe-error boundary completed; hosted trust outcome remains. |
| Active | P10 | Correlated public-render failure observability | Hosted release-observability outcome. |
| Active | P4 | Briefing, correction, and submission CTAs | Implemented; close after hosted smoke proves the live intake routes. |
| Active | P5 | Archive/search facets, mobile navigation, and responsive workflows | Responsive public-workflow outcome. |
| Active | P6 | Editorial report cards, exhibits, visual ranking, and premium copy | Release gate is implemented and live-validated; blind human editorial acceptance remains. |
| Active | P11 | Route verified acquired reports into governed ingest | Eliminate the manual per-folder handoff from the canonical downloader to live report analysis. |
| Active | P7 | Hosted latency and public performance | Measured public-performance outcome. |
| Active | P8 | Readable evidence spans, methodology/source-quality trust, and deterministic related content | Public evidence/discovery outcome. |
| Active | E6 | Retain a hash-pinned claim-embedding benchmark export | Semantic benchmark coverage outcome. |
| Active | E9 | Attest active model-pricing rates before they become stale | Keep cost attribution and spend enforcement trustworthy as provider pricing changes. |
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

- **E7 — Planner-enforced artifact-family reuse (2026-07-17):** Enforce mode now covers retained render, crop, checkpointed analysis/validator, combined crop-plus-analysis, publication preflight, and cross-report reads with a persisted plan/actual reconciliation, report-artifact lease, canonical lineage replacement, and requested-family dependency scoping. Real retained-report replays matched every planned stage/call/side effect: the final post-fix render-only canary completed in 1.190 s (1.190 s audited) with exactly `render_complete`, `html_render`, and checkpoint/HTML writes; crop-only completed in 15.760 s (15.513 s audited) with only crop QA/render and HTML render; and a real model-policy repair issued 17 LLM calls (134,969 input / 40,241 output tokens, estimated $0.114225) while retaining source extraction. The final HTML was complete (77,911 bytes, 469 tags, five images, no `undefined`). A temporary normal-policy replay rejected an incomplete payload before rendering or publication, and a later normal-policy repair completed in 245.980 s with a matched audit. A final full fresh rebuild was correctly stopped by canonical PDF budget authority before provider I/O; no budget bypass was attempted.
- **A3 — Workflow-wide remediation-ledger rollout (2026-07-17):** The generated 31-workflow matrix is CI-checked. A controlled typed `provider_timeout` persisted one remediation record across two submissions; the bounded reaper inspected it once and held it as `operator_action_required` without an executor or external side effect. The read-only soak reported one created, one deduplicated, zero stale, zero eligible, and one held record with no missing runbook mapping. Strict evidence bundle `21a046e89de64aa3a4fcc73250e74074` passed on exact commit `3da3d70e4b202cd2be4f206347982b9d55c94a13`.
- **A6 — Budget-manager closeout and operational proof (2026-07-17):** The public vector-store service now forwards a typed `RunBudget` and preserves canonical budget-stop errors. A live Drive list, OpenAI vector-store create/delete, and minimal OpenAI JSON call completed under canonical authority; ledger evidence recorded one Drive read, one vector create, one vector cleanup, and 168 LLM tokens. The next Drive and vector calls were blocked before provider I/O. Temporary vector stores were removed. The strict exact-HEAD bundle passed.
- **A9 — Canonical report-source identity and publication provenance (2026-07-17):** Reports schema v19 stores immutable, hash-addressed source observations and deterministic resolutions; it preserves v18 compatibility, projects safe source fields to analytics, report cards, and WordPress, and invalidates only rendering/publication when source metadata changes. A live Julius Baer landing page returned HTTP 200 with 218,676 bounded HTML bytes; its existing retained PDF benchmark resolved verified source provenance, while an exact repeat produced no duplicate observation. No LLM call or production write was made.
- **A12 — Complete configured model-pricing coverage for spend budgets (2026-07-18):** The canonical rate card now pins active OpenAI routes to an effective version/source, separately bills cached input, and holds unpriced or unapproved routes before provider I/O. Usage events project cost by report, workflow, prompt namespace, artifact family, and publisher. A bounded live OpenAI embedding recorded 49 input tokens, $0.000001 estimated spend, and complete claim-embedding attribution; the SQLite ledger and JSONL/daily projections reconciled exactly across 1,206 events.
- **E1 — Claim-embedding freshness, retention, and cost controls (2026-07-18):** The existing queue now uses deterministic due-work selection, expiring atomic leases, rechecks before provider I/O, bounded retries/budgets, and a health surface with age percentiles, throughput, drain estimate, failure reasons, model drift, and avoided calls. A live one-row OpenAI canary embedded one valid claim with no duplicate work; queue depth fell from 2,648 to 2,647 and content-hash skips rose from four to five. Historic non-claim rows remain explicitly `unknown_requires_review`, not silently embedded.
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

#### A13. Add approved deferred-work resume adapters for acquisition workflows

- **Title:** Add approved deferred-work resume adapters for report download and publisher inventory
- **Impact 5 / effort: 2**
- **Context:** Durable budget-deferred recovery now safely resumes report generation through a fresh minimal plan. Budget decisions from acquisition workflows are recorded and visible, but workflows without a typed resume adapter deliberately hand off to remediation rather than guessing their source state.
- **Benefit:** Recovering Drive, browser, and acquisition capacity can complete retained report-download and publisher-inventory work automatically while reusing route evidence, artifact caches, and existing public-write gates.
- **Risks to avoid:** Do not replay browser, Drive, mailbox, or public-write work without a fresh canonical budget decision, typed route/checkpoint validation, original idempotency proof, and the existing review gate.
- **Success criteria:**

- Approved adapters rebuild the workflow-specific minimum plan from retained route and artifact evidence, fail closed on missing source state, and resume only the latest safe stage.
- A single bounded invocation proves release-capacity and UTC-day recovery for each adapter, with duplicate worker suppression and no bypass of publishing/mail authorization.
- Dashboard projections distinguish supported auto-resume workflows from remediation-only deferred records with bounded scalar counts.

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
- **Context:** The deterministic public editorial release gate now blocks raw figure labels, OCR/table fragments, generic boilerplate, placeholders, internal identifiers, unsupported numeric claims, duplicate prose, broken assets, and empty implications before WordPress readiness. It preserves before/attempt/after audit artifacts and requests only evidence-grounded repairs. The remaining acceptance is qualitative human review.
- **Benefit:** High-value research reads as analyst-curated while retaining deterministic evidence provenance and auditability.
- **Risks to avoid:** Do not fabricate claims, hide evidence provenance, or substitute automated scores for the specified blind human assessment.
- **Success criteria:**

- Public copy rejects raw figure labels, OCR fragments, generic boilerplate, required-field placeholders, and internal identifiers.
- Blank/low-information thumbnails use deterministic covers or validated source previews.
- Audit identifiers remain available without being reader-facing labels; regression checks fail known leakage patterns in rendered output.
- Three independent blind evaluators assess 30 paired public reports with median readability, decision usefulness, evidence clarity, and appropriate certainty at least 4/5, and an explicit record of any outlier/appeal decision.

#### P11. Route verified acquired reports into governed ingest

- **Title:** Route verified acquired reports into governed ingest
- **Impact 5 / effort: 2**
- **Context:** The canonical downloader now retains verified report PDFs in Drive with route, checksum, and idempotency evidence, but the standard ingest scope does not discover their publisher folders. A live report needs a manual `--folder` handoff despite already being a verified sample.
- **Benefit:** Newly acquired reports enter the same bounded analysis and editorial-release workflow automatically, reducing manual operations and turning source-acquisition diversity into faster quality coverage.
- **Risks to avoid:** Reuse the existing report store, Drive service, cursor, idempotency, and budget authority. Do not duplicate PDFs, create a second queue, loosen source verification, or allow automatic WordPress publication.
- **Success criteria:**

- A verified canonical acquisition record is a deterministic, bounded ingest candidate with source-folder provenance and checksum compatibility checks.
- Default ingest discovers each eligible acquired PDF once, preserves cursor/idempotency behavior, and leaves failed or operator-held records actionable without repeated provider work.
- Focused tests cover discovery, duplicate suppression, stale/mismatched provenance, budget deferral, and no publication side effect; a bounded Drive-to-analysis live canary proves the handoff.

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

#### E6. Retain a hash-pinned claim-embedding benchmark export

- **Impact 4 / effort: 2**
- **Context:** The semantic-selection benchmark correctly falls back when a retained corpus has no persisted vectors, so it cannot yet measure real semantic ranking on the fixed corpus.
- **Benefit:** A bounded, redacted export makes semantic quality and prompt savings reproducible without live embedding calls.
- **Success criteria:** Persist a hash-pinned, retention-governed benchmark export containing only approved vector IDs/content hashes/vectors; benchmark it in CI and compare semantic coverage against lexical fallback without provider calls.

#### E9. Attest active model-pricing rates before they become stale

- **Title:** Attest active model-pricing rates before they become stale
- **Impact 5 / effort: 1**
- **Context:** Cost-governed routes now fail closed when their canonical pricing is missing, stale, invalid, or explicitly held, but price-source review and expiry remain a manual operator responsibility.
- **Benefit:** Spend estimates and report-level attribution remain trustworthy as providers update model pricing, without restoring silent zero-cost execution.
- **Risks to avoid:** Do not scrape or activate a provider rate automatically; preserve explicit operator approval, effective dates, source provenance, and the existing hold-before-I/O behavior.
- **Success criteria:**

- A bounded read-only check reports active, expiring, stale, held, and missing route rates against configured production routes with version/source metadata only.
- Operator acknowledgement creates a reviewed rate-card transition with before/after estimates for recent canonical usage; activation remains an explicit configuration change.
- Tests prove unknown, expired, held, and changed-rate routes cannot silently bypass canonical spend authority.

#### E8. Use canonical source identity to suppress duplicate research work

- **Title:** Use canonical source identity to suppress duplicate research work
- **Impact 5 / effort: 2**
- **Context:** Schema v19 now produces stable canonical source IDs and metadata hashes for the same report observed through different routes, but selection, analytics, and cross-report retrieval do not yet consume that identity as a deduplication and filter key.
- **Benefit:** Equivalent publisher URLs and repeated downloads can reuse validated evidence and avoid duplicate parsing, embedding, and model work while making source/publisher/date filters precise.
- **Risks to avoid:** Never merge merely similar titles; require a canonical identity backed by content hash or publisher-verifiable evidence, retain all observations, and leave conflicts visible for operator review.
- **Success criteria:**

- Selection and cross-report retrieval can filter by canonical source ID, publisher, and verified publication date without exposing private provenance.
- Equivalent identities reuse validated retained artifacts and record avoided parsing/embedding/model calls; conflicting or unknown identity remains non-reusable.
- Retained-corpus and bounded live evidence measure duplicate-work suppression, false-merge prevention, and zero unintended public writes.

#### E9. Materialize prompt families for single-family repair

- **Title:** Materialize prompt-family outputs and route only their required model calls
- **Impact 5 / effort: 3**
- **Context:** E7 now safely reuses source and crop checkpoints and records exact stage/call categories, but the retained analysis payload is still a composite. A real model-policy repair therefore invoked 17 LLM calls even though only the analysis family changed.
- **Benefit:** Prompt, validator, and advisory changes can regenerate the one affected family plus deterministic downstream assembly, reducing LLM time and spend while retaining E7's plan/actual enforcement.
- **Risks to avoid:** Preserve immutable evidence, validation, claims, and rendered-HTML dependency edges; do not duplicate model routing, bypass the LLM ledger, or treat an incomplete family as reusable.
- **Success criteria:**

- Persist typed, hash-pinned per-family materializations and their direct dependencies under the current report-analysis boundary.
- Planner output names the exact family call set; executor constructs only those scoped clients and reconciles actual ledger calls against the plan.
- Retained-corpus and bounded live comparisons show a material call/time/cost reduction from the observed 17-call composite repair while preserving semantic validation and zero unplanned side effects.

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
