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

**Outcome:** CLI and UI expose one read-only `PipelinePlan` that adapts the existing supervisor plan, then execute approved steps through current orchestrators.

**Completion checks:**

- Plans list ordered and skipped steps, blockers, credentials, side effects, checkpoints, idempotency keys, and expected artifacts.
- Ready, partial, failed, missing-credential, and publish-only states are covered without side effects during planning.
- Tests assert the plan contract, structured logs, and execution through canonical orchestration paths.

#### A2. Configured run profiles

**Outcome:** Operators choose documented intents instead of low-level switches.

**Completion checks:**

- YAML profiles cover `safe_default`, `fast_cached`, `repair_failed`, `publish_ready`, `browser_acquisition`, `cost_saver`, and `high_quality`.
- Profile resolution is typed, deterministic, logs effective settings, preserves override precedence, and never stores secrets in YAML.
- The plan-first interface can recommend or apply a profile.

#### A3. Durable autonomous remediation

**Outcome:** Autonomous failures become resumable, deduplicated work items rather than UI-only dead letters.

**Completion checks:**

- Records retain run/workflow/step IDs, `AppError` taxonomy, checkpoint, input checksum, artifact references, remediation code, and runbook link.
- A bounded reaper retries transient failures after cooldown, resumes valid checkpoints, invokes targeted repair, and escalates terminal blockers.
- Tests prove retry budget, state transitions, duplicate suppression, stale-checkpoint behavior, and operator-facing remediation.

#### A4. Quarantine irreparably malformed Drive PDFs

**Outcome:** Bounded redownload failure creates reversible source quarantine before expensive report work starts.

**Completion checks:**

- State records file identity, checksum/size, typed error, and next action after PDF-integrity failure.
- Default ingest skips quarantined files; explicit rescan/revalidation clears only a valid replacement.
- CLI or dashboard exposes quarantined inputs and remediation guidance, with tests for each transition.

#### A5. Persist acquisition hard-blocker policy

**Outcome:** Email-domain, anti-bot, and CAPTCHA outcomes suppress only the proven doomed route until evidence expires or conditions change.

**Completion checks:**

- Publisher-scoped, TTL-bound policy records observed form/access-control evidence and the permitted alternate route.
- Identity/mailbox domain alignment is checked before email-form submission; automation uses only configured, verified facts.
- Policy avoids browser launches and mailbox polls when blocked, supports an eligible-mailbox/revalidation override, and has tests for TTL and scope.

#### A6. Pipeline-wide budget manager

**Outcome:** Extend the implemented OpenAI daily pre-call guardrail into a single auditable policy for all costly side effects.

**Current foundation:** OpenAI chat, image chat, embeddings, OCR, and vector-store calls already use canonical daily spend plus an exact task-median forecast where available.

**Completion checks:**

- Typed `RunBudget` covers run, day, and publisher scopes for spend, tokens, time, retries, browser launches, Drive/WordPress writes, and PDFs.
- Non-OpenAI side effects receive explicit `warn`, `pause`, `defer`, `stop`, or authorized `override` decisions; cold-start forecasting is named and logged.
- Health scorecards retain usage, avoided calls, breaches, and overrides; tests cover all outcomes and required log fields.

#### A7. Policy-driven LLM routing, compaction, and same-provider fallback

**Outcome:** Select a model tier, bounded context, and approved fallback deterministically by task and failure class.

**Completion checks:**

- YAML maps task/artifact families to model tier, input budget, compaction policy, quality threshold, and same-provider fallback constraints.
- Routing, compaction, evidence anchors, fallback reason, and expected cost are logged in the stable LLM contract.
- Fixed-corpus benchmarks prove retained citations/evidence and no material quality regression; tests cover success, fallback, exhaustion, and replay-forbidden cases.

#### A8. Compare retained model-call replay bundles

**Outcome:** A read-only command surfaces contract/prompt/output drift from existing replay bundles.

**Completion checks:**

- The command compares deterministic fields, schema validity, prompt hashes, and selected evidence without provider calls by default.
- Output is bounded, reproducible, and links regressions to artifact family and remediation.
- Tests cover equivalent, changed, missing, and malformed bundles.

### 2. Public Trust and Publishing

#### P1. Rename the read-only publish snapshot to Publish Readiness

**Outcome:** The UI, contracts, documentation, and logs accurately describe the existing synchronous, idempotent readiness snapshot.

**Completion checks:**

- `publish_queue_orchestrator.py` terminology is replaced by `Publish Readiness` at public/operator boundaries without creating a queue or outbox.
- The output retains validation, evidence, health, duplicate-suppression, and review blockers; publishing remains draft/review-required by default.
- Failure-injection tests cover restart, retry, duplicate dispatch, and partial WordPress failure.

#### P2. Move public intelligence claims out of WordPress runtime synthesis

**Outcome:** WordPress renders approved projection/artifact data and never infers analytical claims from post counts or dates.

**Completion checks:**

- Signal, freshness, strategic-theme, and publisher-authority modules use an approved source contract.
- Missing projections fail closed with neutral UI or an admin-visible diagnostic.
- Tests and README map each intelligence surface to its projection source.

#### P3. Resolve hosted-site trust blockers

**Outcome:** The public hostname uses HTTPS, canonical HTTPS URLs, safe failures, and branded 404/500 pages.

**Completion checks:**

- HTTP redirects to successful HTTPS; robots and sitemap URLs are canonical HTTPS.
- Public failures expose no stack trace, plugin path, filesystem path, or troubleshooting internals.
- Hosted smoke evidence covers transport, representative pages, sitemap, and safe error handling.

#### P4. Implement public briefing, correction, and submission intake

**Outcome:** Each public CTA reaches a validated, privacy-conscious intake path and a confirmed delivery/persistence boundary.

**Completion checks:**

- Correction and submission forms collect only the documented, necessary fields and present confirmation/error states.
- Requests use an approved service boundary with redacted structured logging.
- Browser or hosted smoke checks prove route, validation, empty/spam rejection, and successful submission.

#### P5. Finish responsive search and navigation

**Outcome:** Key public pages work cleanly at 390px, tablet, and desktop widths.

**Completion checks:**

- No horizontal overflow, clipping, overlap, or unusable search/filter controls on homepage, search, archive, detail, contact, and submit views.
- Mobile navigation has accessible open/close and focus behavior with an intentional panel/backdrop.
- Retained visual-smoke screenshots cover each key view.

#### P6. Raise report-card and evidence-exhibit editorial quality

**Outcome:** Public cards use source-grounded human titles, captions, previews, and summaries instead of OCR or internal artifacts.

**Completion checks:**

- Public copy rejects raw figure labels, OCR fragments, generic boilerplate, required-field placeholders, and internal identifiers.
- Blank/low-information thumbnails use deterministic covers or validated source previews.
- Audit identifiers remain available without being presented as reader-facing labels.

#### P7. Improve hosted public-site performance without contract loss

**Outcome:** Representative public routes materially improve response-start and DOM-complete timings while retaining SEO/social contracts.

**Completion checks:**

- Homepage, reports, briefings, signals, methodology, contact, and submit pages improve against `config/public_site_baselines.yaml` without increased page weight or request count.
- Remaining target gaps are measured and documented.
- Hosted evidence confirms canonical URLs, Open Graph, Twitter metadata, and archive completeness remain intact.

#### P8. Complete concise public evidence, methodology, and related-content surfaces

**Outcome:** Readers can verify high-impact claims and discover relevant approved content without seeing internal diagnostics.

**Completion checks:**

- Claim support can show source report, publisher, page, concise excerpt, limitation, and original link where approved.
- Methodology shows scope, source pages, material limitations, and evidence state.
- Report pages start with deterministic related report, briefing, topic, and publisher links; missing approved data fails closed.

#### P9. Close public-advisory quality gaps from retained evidence

**Outcome:** The advisory benchmark measures insight quality and generates grounded, targeted remediation for missing `so_what` / `now_what` fields.

**Completion checks:**

- Read-only benchmark measures role diversity, duplicate overlap, report lens, score calibration, evidence linkage, and advisory coverage against a saved baseline.
- Missing fields create typed targets; regeneration fills them only with source support and records abstention otherwise.
- Tests cover metrics, narrow-report fallback, grounded repair, abstention, and unchanged rendering when evidence is insufficient.

### 3. Evidence Quality and Reuse

#### E1. Operate claim embeddings with freshness, retention, and cost visibility

**Outcome:** Operators can see embedding health and avoid unnecessary re-embedding.

**Completion checks:**

- A concise report groups embedded, pending, failed, stale, and model-mismatched claims by publisher/report/topic.
- Retention/pruning policy is documented and tested.
- Unchanged rows are skipped with cost-avoidance telemetry; failures retain retry visibility.

#### E2. Benchmark semantic evidence preselection

**Outcome:** Embedding-backed selection is measured against deterministic fallback on existing projected artifacts.

**Completion checks:**

- Read-only benchmark reports prompt/token deltas, evidence overlap, source coverage, and citation coverage for Briefing and Signal.
- Coverage loss beyond a documented threshold warns or fails.
- Results and fallback ordering are deterministic and tested.

#### E3. Use artifact lineage for selective regeneration

**Outcome:** Compatibility-aware planning regenerates only invalidated work and reports work avoided.

**Completion checks:**

- Typed planning maps source, prompt, template, crop, and validator changes to the smallest required checkpoint stage.
- Report and cross-report workflows consult valid lineage before model, PDF, crop, render, and publication work.
- Regression tests prove render-only reuse and prohibit reuse after source invalidation; quality output reports fan-out, reuse, and avoided work.

#### E4. Make retained PDF benchmark evidence executable in CI

**Outcome:** PDF candidate/crop benchmark artifacts are real, integrity-pinned release evidence—not waived missing assets.

**Completion checks:**

- CI securely materializes the approved source/crop corpus with license/retention metadata, SHA-256 hashes, and expected paths.
- Missing or hash-mismatched evidence fails; candidate, crop-refine, trend, scorecard, manifest, and review run without missing-asset warnings.
- A CI run for the release SHA retires the temporary PDF waiver entries.

#### E5. Promote crop-QA sidecars to scorecards and selection telemetry

**Outcome:** Deterministic crop diagnostics drive operational quality signals without leaking to public pages.

**Completion checks:**

- Scorecards aggregate accepted/rejected counts, quality, defects, detector confidence, DPI, and artifact-size deltas from `.qa.json` sidecars.
- Selection telemetry retains the chosen profile, QA sidecar, total score, defects, and detector summary.
- Existing-artifact benchmarks flag quality/clipping/storage/runtime regressions; tests cover aggregation, missing evidence, public redaction, and no-model default behavior.

### 4. Release Integrity and Architectural Enforcement

#### R1. Publish release-evidence reviews where reviewers work

**Outcome:** CI job summaries and PR/release notes show approval status, unwaived issues, and the archived evidence bundle.

**Completion checks:**

- CI appends bounded review Markdown after approval gating.
- PR/release automation links the bundle and final approval status.
- README distinguishes inline review from full archived evidence.

#### R2. Enforce role boundaries, direct-I/O discipline, and controlled module growth

**Outcome:** CI detects role mixing, direct-I/O drift, missing service integration coverage, and unjustified first-party monolith growth.

**Completion checks:**

- Gates target first-party files and require owner/expiry for every waiver.
- Service integration-test absence is a failure unless explicitly waived.
- Documentation explains adding and retiring a waiver.

#### R3. Restore service quality coverage above the retained baseline

**Outcome:** Full-suite `src/services` coverage reaches at least 82.9680% without lowering other coverage.

**Completion checks:**

- New behavior-focused coverage prioritizes ledger recovery, browser-worker lifecycle, and artifact-lineage failure paths.
- Assertions cover returned contracts or persisted state, not coverage-only paths.
- The quality baseline is refreshed only by a passing full CI run and records its exact SHA.

#### R4. Consume canonical LLM projection status in budget and release decisions

**Outcome:** Hard spend/release decisions account for pending canonical usage rather than relying on lagging compatibility exports.

**Current foundation:** `get_projection_status` already reports checkpoint, pending count/cost, timestamp, and derived-file validity without rebuilding exports.

**Completion checks:**

- Run-budget and release evidence either account for pending usage or require an explicit fresh projection.
- Structured outcomes distinguish normal lag, threshold projection, missing/stalled checkpoint, and invalid exports.
- Tests prove those cases and prove ordinary reads do not rebuild.

### 5. Boundary Simplification

All work in this lane is movement-only unless behavior change receives explicit approval. Public facades, order, retries, idempotency, logs, and side effects must remain stable.

#### S1. Simplify canonical service entrypoints

**Outcome:** Each external system has one discoverable canonical service boundary; internal capability modules do not become peer public services.

**Completion checks:**

- Audit identifies top-level service proliferation, duplicate public entrypoints, and ownership gaps.
- Internal capabilities move behind the existing canonical boundary only where that reduces coupling.
- Import/contract tests preserve public callers and prevent new competing entrypoints.

#### S2. Reduce control-plane hotspots, including publish orchestration

**Outcome:** Large ingest/publish orchestration surfaces retain their public facades while stable private capabilities get semantic owners.

**Completion checks:**

- Review separates routing/retry/state control from generator domain decisions and service I/O.
- `publish_orchestrator.py` and `ingest_orchestrator.py` remain canonical facades; any extraction has explicit semantic ownership.
- Focused movement evidence preserves imports, retry counts, cursors, state transitions, logs, and external effects.

#### S3. Simplify the PDF visual-heuristics boundary

**Outcome:** `pdf_service` stays the sole external/library boundary while its public facade exposes only necessary semantic operations.

**Completion checks:**

- Remove unnecessary re-exports and forwarding chains without changing callers or outputs.
- Keep visual heuristics capability-owned and testable behind the canonical PDF boundary.
- Equivalence tests preserve candidate/crop behavior and artifact paths.

#### S4. Give WordPress shortcodes semantic ownership

**Outcome:** The large shortcode class is split or simplified by stable shortcode capability, without creating artificial pass-through layers.

**Completion checks:**

- Each extracted unit owns a coherent shortcode family and documents why the boundary reduces coupling.
- Public shortcode behavior, output, and WordPress hooks remain unchanged.
- PHP/runtime tests cover each public surface and compatibility facade.

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
