# Consolidated TODO

Last audited: 2026-07-12

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
| Active | A1 | Single autonomous supervisor, read-only `PipelinePlan`, and mandatory workflow-control authority | One plan-first execution outcome. |
| Active | A2 | `fast_ingest` and other config-driven autopilot profiles | One typed profile outcome. |
| Active | A3 | Durable dead letters, scheduled actions, full autonomous smoke, and side-effect idempotency | One recovery/remediation outcome. |
| Active | A4 | Malformed-Drive-PDF quarantine | Standalone bounded source-recovery outcome. |
| Active | A5 | Business-email, CAPTCHA, anti-bot, terminal-evidence, and avoided-browser-spend route policy | One acquisition hard-blocker outcome. |
| Active | A6 | Day/run/publisher spend guardrails | One pipeline-wide budget outcome. |
| Active | A7 | Budget-aware model routing, compaction, and failure-class fallback | One stable LLM-policy outcome. |
| Active | A8 | Model-call replay drift comparison | Standalone read-only regression outcome. |
| Active | A9 | Source publication-metadata capture for retained regeneration | Source-supported render metadata outcome. |
| Active | P1 | Publish snapshot naming and synchronous idempotent publishing | Publish Readiness outcome. |
| Active | P2 | Stop WordPress intelligence/freshness/authority synthesis | Approved-projection rendering outcome. |
| Active | P3 | Hosted HTTPS, safe errors, and public trust checks | Hosted trust outcome. |
| Active | P4 | Briefing, correction, and submission CTAs | Public intake outcome. |
| Active | P5 | Archive/search facets, mobile navigation, and responsive workflows | Responsive public-workflow outcome. |
| Active | P6 | Editorial report cards, exhibits, visual ranking, and premium copy | Public editorial presentation outcome. |
| Active | P7 | Hosted latency and public performance | Measured public-performance outcome. |
| Active | P8 | Readable evidence spans, methodology/source-quality trust, and deterministic related content | Public evidence/discovery outcome. |
| Active | P9 | Insight-quality benchmark and `so_what` / `now_what` remediation | Advisory quality/remediation outcome. |
| Active | E1 | Claim-embedding freshness, retention, and cost controls | Embedding operations outcome. |
| Active | E2 | Semantic-preselection quality/cost benchmark | Evidence-selection measurement outcome. |
| Active | E3 | Lineage-driven selective regeneration and cost reporting | Compatibility-aware reuse outcome. |
| Active | E4 | Executable retained PDF benchmark corpus in CI | Release-evidence outcome. |
| Active | E5 | Crop QA sidecars, rendered visual metrics, profiles, and HTML visual smoke | Visual-evidence quality outcome. |
| Active | R1 | CI/PR release-evidence summaries | Reviewer-surface outcome. |
| Active | R2 | Role-mixing, import-graph, facade, direct-I/O, mutation-selection, and hygiene enforcement | Architecture enforcement outcome. |
| Active | R3 | Service-quality coverage recovery | Retained-baseline outcome. |
| Active | R4 | Projection-lag status in budget/release decisions | Canonical-accounting outcome. |
| Active | S1 | Canonical external-service boundaries | Service-entrypoint simplification outcome. |
| Active | S2 | Publish/ingest and other control-plane hotspot decomposition | Movement-only orchestration outcome. |
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
| Excluded | X1 | Draft HTML published before enrichment | Public progressive enrichment is not permitted. |
| Excluded | X2 | Automatic lower private-API promotion thresholds | Conservative thresholds remain mandatory. |
| Excluded | X3 | Invented acquisition-form identity facts or public pipeline diagnostics | Only verified identity facts may be mapped; diagnostics remain operator-only. |

## Active Backlog

### 1. Autonomous Safety and Cost Control

#### A1. Plan-first pipeline execution

- **Title:** Plan-first pipeline execution
- **Impact 5 / effort: 3**
- **Context:** `AutonomousRunSupervisorPlan` already emits typed workflow-control decisions, but callers still lack one public, side-effect-free contract that explains the safest next action across CLI and UI entrypoints.
- **Benefit:** Operators can request an intent, inspect all planned side effects, and approve an execution path instead of manually assembling implementation flags.
- **Risks to avoid:** Do not create a second orchestrator or embed generator domain logic in planning.
- **Success criteria:**

- Plans list ordered and skipped steps, blockers, credentials, side effects, checkpoints, idempotency keys, and expected artifacts.
- Ready, partial, failed, missing-credential, and publish-only states are covered without side effects during planning.
- Tests assert the plan contract, structured logs, and execution through canonical orchestration paths; a plan-only run proves no external mutation occurred.

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

#### A3. Durable autonomous remediation

- **Title:** Durable autonomous remediation
- **Impact 5 / effort: 3**
- **Context:** UI-run dead letters and typed failure classifications exist, but autonomous failures are not durable workflow-wide remediation records with checkpoint, budget, and idempotency context.
- **Benefit:** Operators do not need to reconstruct failure context, and the system can safely resume repairable work without repeatedly rerunning irreparable work.
- **Risks to avoid:** Enforce cooldowns, attempt budgets, and idempotency so recovery cannot create expensive loops.
- **Success criteria:**

- Records retain run/workflow/step IDs, `AppError` taxonomy, checkpoint, input checksum, artifact references, remediation code, and runbook link.
- A bounded reaper retries transient failures after cooldown, resumes valid checkpoints, invokes targeted repair, and escalates terminal blockers.
- Tests prove retry budget, state transitions, duplicate suppression, stale-checkpoint behavior, operator-facing remediation, and no duplicate side effect on replay.

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

#### A5. Persist acquisition hard-blocker policy

- **Title:** Persist acquisition hard-blocker policy
- **Impact 4 / effort: 2**
- **Context:** Live publishers can reject personal delivery domains or impose CAPTCHA/403 controls after browser work has already begun; those outcomes currently require repeated operator interpretation.
- **Benefit:** Browser and mailbox budget is spent only on routes that can still complete unattended, with retained evidence for why work was skipped.
- **Risks to avoid:** Keep decisions publisher-scoped and TTL-bound; never infer identity facts or suppress valid alternate routes.
- **Success criteria:**

- Publisher-scoped, TTL-bound policy records observed form/access-control evidence and the permitted alternate route.
- Identity/mailbox domain alignment is checked before email-form submission; automation uses only configured, verified facts.
- Policy avoids browser launches and mailbox polls when blocked, supports an eligible-mailbox/revalidation override, and has tests for TTL, publisher/URL scope, and avoided-work telemetry.

#### A6. Pipeline-wide budget manager

- **Title:** Pipeline-wide budget manager
- **Impact 5 / effort: 3**
- **Context:** Canonical OpenAI and OpenRouter calls now evaluate daily spend with exact matched-median forecasts, atomically reserve in-flight cost, release it on canonical recording, and finalize their projection. Browser Use direct vendor clients, Drive, WordPress, and run/publisher limits are not yet governed by that same policy.
- **Benefit:** Unattended runs gain predictable spend, runtime, and call ceilings before they make any expensive side effect.
- **Risks to avoid:** Extend the canonical ledger and service boundaries; do not create a parallel ledger or silently drop work.

**Current foundation:** OpenAI chat, image chat, embeddings, OCR, vector-store, and OpenRouter JSON calls use canonical spend plus matched median and in-flight reservation where available. Projection finalization is fenced, segment-backed, and reconciled from canonical SQLite.

- **Success criteria:**

- Typed `RunBudget` covers run, day, and publisher scopes for spend, tokens, time, retries, browser launches, Drive/WordPress writes, and PDFs.
- Browser Use OpenAI/OpenRouter calls use the same canonical reservation and post-call release path; a crashed worker cannot retain a reservation beyond its bounded TTL.
- Non-OpenAI side effects receive explicit `warn`, `pause`, `defer`, `stop`, or authorized `override` decisions; cold-start forecasting is named and logged.
- Overrides are YAML-backed, expiry-bound, and require actor, reason, and scope; each is durably logged and reconciled to actual canonical cost.
- Health scorecards retain usage, avoided calls, breaches, and overrides; tests cover all outcomes, required log fields, and the absence of side effects after a stop/defer decision.

#### A7. Policy-driven LLM routing, compaction, and same-provider fallback

- **Title:** Policy-driven LLM routing, compaction, and same-provider fallback
- **Impact 5 / effort: 4**
- **Context:** JSON chat has deterministic compaction and provider decisions, but model selection is mostly static by namespace and lacks a policy tying difficulty, budget, evidence retention, and recoverable failure together.
- **Benefit:** The pipeline reduces cost and latency on routine work while keeping difficult-artifact recovery and prompt-size decisions reproducible.
- **Risks to avoid:** Preserve evidence anchors and same-model replay constraints; do not leak provider payloads into generators.
- **Success criteria:**

- YAML maps task/artifact families to model tier, input budget, compaction policy, quality threshold, and same-provider fallback constraints.
- Routing, compaction, evidence anchors, fallback reason, and expected cost are logged in the stable LLM contract.
- Fixed-corpus benchmarks prove retained citations/evidence and no material quality regression; tests cover primary success, fallback, exhaustion, replay-forbidden cases, and typed failure output.

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

#### A9. Capture source-supported publication metadata at acquisition

- **Title:** Capture source-supported publication metadata at acquisition
- **Impact 5 / effort: 2**
- **Context:** Retained report regeneration can safely reuse PDF, model, and render checkpoints, but older acquisitions may lack a source-supported publication date and therefore fail the report-card gate during an otherwise render-only recovery.
- **Benefit:** Acquisition provenance directly enables reliable low-cost regeneration and avoids broad reruns caused solely by absent public-card metadata.
- **Risks to avoid:** Persist only source-page evidence with its URL and retrieval timestamp; never infer a date from a filename, file mtime, or report title.
- **Success criteria:**

- Acquisition records normalized source publication date, source URL, retrieval timestamp, and evidence locator when the publisher exposes them.
- Render and regeneration consume the persisted source-backed metadata without an operator override; missing or contradictory evidence still fails closed.
- Retained-source tests cover metadata extraction, persistence, render-only recovery, absent evidence, and conflicting dates.

### 2. Public Trust and Publishing

#### P1. Rename the read-only publish snapshot to Publish Readiness

- **Title:** Rename the read-only publish snapshot to Publish Readiness
- **Impact 4 / effort: 2**
- **Context:** `publish_queue_orchestrator.py` is used by UI and operations flows, but it only builds a read-only snapshot from HTML files and publish state; its queue name promises durability it does not provide.
- **Benefit:** Operators receive truthful workflow terminology and review evidence without prematurely introducing queue/outbox infrastructure.
- **Risks to avoid:** Keep public publishing synchronous, idempotent, and draft/review-required until operating evidence justifies durable jobs.
- **Success criteria:**

- `publish_queue_orchestrator.py` terminology is replaced by `Publish Readiness` at public/operator boundaries without creating a queue or outbox.
- The output retains validation, evidence, health, duplicate-suppression, and review blockers; publishing remains draft/review-required by default.
- Failure-injection tests cover restart, retry, duplicate dispatch, and partial WordPress failure, with retained findings for any future outbox decision.

#### P2. Move public intelligence claims out of WordPress runtime synthesis

- **Title:** Move public intelligence claims out of WordPress runtime synthesis
- **Impact 5 / effort: 3**
- **Context:** Some shortcode/stat surfaces still derive weekly signals, strategic themes, freshness-style movement, or publisher authority from WordPress counts and dates despite the pipeline owning approved projections.
- **Benefit:** Analytical claims remain reproducible, source-grounded, and owned by the Python pipeline rather than mutable runtime queries.
- **Risks to avoid:** Fail closed when projections are unavailable; do not invent neutral-looking claims from WordPress data.
- **Success criteria:**

- Signal, freshness, strategic-theme, and publisher-authority modules use an approved source contract.
- Missing projections fail closed with neutral UI or an admin-visible diagnostic.
- Tests prove no claim is generated solely from WordPress counts/dates, and README maps each intelligence surface to its projection source.

#### P3. Resolve hosted-site trust blockers

- **Title:** Resolve hosted-site trust blockers
- **Impact 5 / effort: 2**
- **Context:** Live public-site checks found HTTPS failure, HTTP sitemap URLs, a fatal `/publisher/not-extracted/` response exposing PHP paths, and no branded failure surface.
- **Benefit:** Transport, safe errors, and reliable navigation meet the baseline expected of a trust-positioned research product.
- **Risks to avoid:** Verify staging and production separately and never disclose stack traces, paths, or diagnostics publicly.
- **Success criteria:**

- HTTP redirects to successful HTTPS; robots and sitemap URLs are canonical HTTPS.
- Public failures expose no stack trace, plugin path, filesystem path, or troubleshooting internals.
- Hosted smoke evidence covers transport, representative pages, sitemap, branded 404/500 pages, and safe error handling in both staging and production.

#### P4. Implement public briefing, correction, and submission intake

- **Title:** Implement public briefing, correction, and submission intake
- **Impact 5 / effort: 2**
- **Context:** `Request a briefing`, `Send a correction`, and submission CTAs currently loop to information pages instead of collecting actionable structured requests.
- **Benefit:** Visitors can convert, correct, or submit sources through a trustworthy route that gives operators usable context.
- **Risks to avoid:** Collect only necessary data and do not create a new external boundary without explicit review.
- **Success criteria:**

- Correction and submission forms collect only the documented, necessary fields and present confirmation/error states.
- Requests use an approved service boundary with redacted structured logging.
- Browser or hosted smoke checks prove CTA route, validation, empty/spam rejection, successful persistence/delivery, and confirmation state.

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

#### P9. Close public-advisory quality gaps from retained evidence

- **Title:** Close public-advisory quality gaps from retained evidence
- **Impact 4 / effort: 3**
- **Context:** The retained advisory benchmark measures claim support and basic advisory coverage, while older retained artifacts still have missing `so_what` / `now_what`, weak role diversity, or uncalibrated scores.
- **Benefit:** Measured gaps become targeted, source-supported repairs instead of broad regeneration or cosmetic metadata.
- **Risks to avoid:** Do not turn benchmark prose into brittle fixtures or populate unsupported advisory fields.
- **Success criteria:**

- Read-only benchmark measures role diversity, duplicate overlap, report lens, score calibration, evidence linkage, and advisory coverage against a saved baseline.
- Missing fields create typed targets; regeneration fills them only with source support and records abstention otherwise.
- Tests cover metrics, narrow-report fallback, grounded repair, abstention, unchanged rendering when evidence is insufficient, and baseline-stable output.

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

#### E2. Benchmark semantic evidence preselection

- **Title:** Benchmark semantic evidence preselection
- **Impact 4 / effort: 3**
- **Context:** Briefing and Signal can use persisted claim embeddings for bounded semantic selection, but the cap and ranking policy have no retained-corpus measurement against lexical/category fallback.
- **Benefit:** Prompt-size reductions become measurable without silently reducing citation recall, source-report coverage, or useful evidence diversity.
- **Risks to avoid:** Use stable retained corpora and deterministic ordering; do not synthesize fixtures to prove quality.
- **Success criteria:**

- Read-only benchmark reports prompt/token deltas, evidence overlap, source coverage, and citation coverage for Briefing and Signal.
- Coverage loss beyond a documented threshold warns or fails.
- Results and fallback ordering are deterministic and tested against stale/no-embedding cases as well as populated embeddings.

#### E3. Use artifact lineage for selective regeneration

- **Title:** Use artifact lineage for selective regeneration
- **Impact 5 / effort: 3**
- **Context:** Artifact lineage already persists checkpoint artifacts, dependencies, compatibility metadata, and invalidation state, but workflows do not use it to calculate the smallest valid regeneration plan.
- **Benefit:** Lineage reduces LLM/PDF/render cost and latency while preserving explainable source-to-publication traceability.
- **Risks to avoid:** Never reuse invalidated or incompletely provenanced artifacts; missing lineage must fail closed.
- **Success criteria:**

- Typed planning maps source, prompt, template, crop, and validator changes to the smallest required checkpoint stage.
- Report and cross-report workflows consult valid lineage before model, PDF, crop, render, and publication work.
- Regression tests prove render-only reuse and prohibit reuse after source invalidation; quality output reports fan-out, reuse, avoided work, and missing-lineage failures.

#### E4. Make retained PDF benchmark evidence executable in CI

- **Title:** Make retained PDF benchmark evidence executable in CI
- **Impact 5 / effort: 3**
- **Context:** CI currently permits missing retained PDF/crop assets, producing warnings and expiry-dated waivers instead of independently executable candidate and crop-refine evidence.
- **Benefit:** Candidate/crop equivalence, runtime, and model-work regressions are independently verified on every release SHA.
- **Risks to avoid:** Keep the corpus licensed, non-secret, bounded, and hash-pinned; never replace it with synthetic passing evidence.
- **Success criteria:**

- CI securely materializes the approved source/crop corpus with license/retention metadata, SHA-256 hashes, and expected paths.
- Missing or hash-mismatched evidence fails; candidate, crop-refine, trend, scorecard, manifest, and review run without missing-asset warnings.
- A CI run for the release SHA publishes passing benchmark evidence and retires the temporary PDF waiver entries.

#### E5. Promote crop-QA sidecars to scorecards and selection telemetry

- **Title:** Promote crop-QA sidecars to scorecards and selection telemetry
- **Impact 5 / effort: 3**
- **Context:** Final crop QA emits DPI, scores, defects, and detector diagnostics, but release evidence and selection summaries still rely mainly on candidate signatures and manual visual review.
- **Benefit:** Crop regressions become measurable by report, candidate type, and profile rather than discovered only manually after publication work.
- **Risks to avoid:** Keep unproven metrics diagnostic and never render raw QA diagnostics publicly.
- **Success criteria:**

- Scorecards aggregate accepted/rejected counts, quality, defects, detector confidence, DPI, and artifact-size deltas from `.qa.json` sidecars.
- Selection telemetry retains the chosen profile, QA sidecar, total score, defects, and detector summary.
- Existing-artifact benchmarks flag quality/clipping/storage/runtime regressions; tests cover aggregation, missing evidence, public redaction, stable profile comparison, and no-model default behavior.

### 4. Release Integrity and Architectural Enforcement

#### R1. Publish release-evidence reviews where reviewers work

- **Title:** Publish release-evidence reviews where reviewers work
- **Impact 3 / effort: 2**
- **Context:** Release-evidence review Markdown is generated and archived, but reviewers must open the artifact bundle to learn approval status, owners, expiry dates, and unwaived issues.
- **Benefit:** Release readiness is visible where reviewers already work, reducing missed evidence and review latency.
- **Risks to avoid:** Keep summaries bounded and links stable while preserving all unwaived issue detail.
- **Success criteria:**

- CI appends bounded review Markdown after approval gating.
- PR/release automation links the bundle and final approval status.
- README distinguishes inline review from full archived evidence, and tests cover bounded summaries with unwaived detail retained.

#### R2. Enforce role boundaries, direct-I/O discipline, and controlled module growth

- **Title:** Enforce role boundaries, direct-I/O discipline, and controlled module growth
- **Impact 4 / effort: 3**
- **Context:** CI already enforces imports, forbidden patching, coverage, and mutation, but role mixing, direct-I/O drift, service-integration coverage, facade thickness, and long-file growth are not yet uniformly executable.
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

#### R4. Consume canonical LLM projection status in budget and release decisions

- **Title:** Consume canonical LLM projection status in budget and release decisions
- **Impact 5 / effort: 2**
- **Context:** `get_projection_status` exposes the checkpoint, latest canonical event, pending count/cost, timestamp, and derived-file validity, but run-budget and release gates do not consume it.
- **Benefit:** Incremental projection performance no longer makes spend or release decisions undercount actual canonical usage.
- **Risks to avoid:** Distinguish normal bounded lag from missing/stalled/invalid projections without forcing routine rebuilds.

**Current foundation:** `get_projection_status` already reports checkpoint, pending count/cost, timestamp, and derived-file validity without rebuilding exports.

- **Success criteria:**

- Run-budget and release evidence either account for pending usage or require an explicit fresh projection.
- Structured outcomes distinguish normal lag, threshold projection, missing/stalled checkpoint, and invalid exports.
- Tests prove those cases, required log fields, and that ordinary status reads do not rebuild exports.

### 5. Boundary Simplification

All work in this lane is movement-only unless behavior change receives explicit approval. Public facades, order, retries, idempotency, logs, and side effects must remain stable.

#### S1. Simplify canonical service entrypoints

- **Title:** Simplify canonical service entrypoints
- **Impact 4 / effort: 4**
- **Context:** The repository has already split several oversized boundaries, but top-level service proliferation and internal capability modules can still become competing public entrypoints.
- **Benefit:** Clear ownership prevents callers from choosing between duplicate paths to the same external system and lowers future navigation cost.
- **Risks to avoid:** Do not create forwarding wrappers or split modules merely for file-size aesthetics.
- **Success criteria:**

- Audit identifies top-level service proliferation, duplicate public entrypoints, and ownership gaps.
- Internal capabilities move behind the existing canonical boundary only where that reduces coupling.
- Import/contract tests preserve public callers, prevent new competing entrypoints, and document semantic ownership for every retained layer.

#### S2. Reduce control-plane hotspots, including publish orchestration

- **Title:** Reduce control-plane hotspots, including publish orchestration
- **Impact 5 / effort: 5**
- **Context:** Publish and ingest coordinators still combine enough state filtering, materialization, worker coordination, term handling, and finalization logic to make control-flow changes high risk.
- **Benefit:** High-risk control-plane behavior gains clearer ownership without forcing callers through a public behavior migration.
- **Risks to avoid:** This is movement-only unless explicitly approved otherwise; preserve ordering, retries, idempotency, logs, and side effects.
- **Success criteria:**

- Review separates routing/retry/state control from generator domain decisions and service I/O.
- `publish_orchestrator.py` and `ingest_orchestrator.py` remain canonical facades; any extraction has explicit semantic ownership.
- Focused movement evidence preserves imports, retry counts, cursors, state transitions, logs, external effects, and existing test expectations.

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

- Canonical LLM accounting uses SQLite with deterministic JSONL/daily projections, reconciliation, replay suppression, task-median forecasting, and configured OpenAI day guardrails.
- The retained CI accounting corpus now includes valid, invalid, replay-suppressed, and real cached-provider (`provider_hit`) events; cached-token tampering is rejected by reconciliation tests. This closes the former cached-provider corpus task.
- Claim embeddings, stale/no-embedding fallback, bounded semantic preselection, durable Signal artifacts, artifact lineage storage, and lineage invalidation are present.
- Workflow-control intent/preflight, UI dead letters, mailbox acquisition, resume checkpoints, prompt dry runs, provider decisions, and deterministic JSON-chat compaction are present.
- Public report rendering exposes approved advisory/metric-spine data while redacting canonical IDs; strict crop acceptance emits typed QA sidecars.
- WordPress report, briefing, and signal entities have REST draft/readback verification; hosted SEO/social/performance gate exists. Hosted HTTPS/error handling, intake, responsive UI, and editorial leakage remain active public-site gaps.
- CI runs formatting, typing, architecture/import checks, forbidden-patching checks, hygiene, coverage, mutation, prompt regression, release-evidence archival, and WordPress staging verification when configured. PDF benchmark evidence remains temporarily waived when retained assets are unavailable.

## Audit Notes

- This register replaces duplicated simplification context, migrated x100 intake, and repeated launch plans with source-neutral status rows. No task is excluded because of its origin.
- The active backlog contains 30 outcome-owned items. Deferred, closed, and excluded rows remain visible above; any newly discovered work must be merged into an existing outcome or justified as a new one.
