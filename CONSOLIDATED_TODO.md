# Consolidated TODO

Last audited: 2026-07-12

This file is the single active backlog for this repository. It supersedes older backlog notes, archived planning docs, and ad hoc audit intake.

Items below were rechecked against the current repository state. Completed capabilities are listed as closed evidence and are not active backlog. Partially landed capabilities remain only when a concrete implementation gap is still visible in code, tests, README, or local WordPress assets.

## Backlog Rules

- Treat this file as the only active TODO source.
- Treat migrated intake items as proposals, not approval: revalidate the current state, establish a baseline, and promote only work that meets the decision register below.
- Remove an item when all acceptance criteria are met.
- Merge overlapping work into one item instead of creating parallel tasks.
- Before implementation starts, every prioritized item must have an owner, baseline metric, target metric, and review/expiry date.
- Keep changes compliant with `AGENTS.md`: no placeholder logic, no role mixing, no prompt text in code, no private-helper monkeypatching, and no new deployable boundary without architecture review.

Scoring:

- `Impact`: `1` low leverage, `5` highest leverage across reliability, quality, cost, speed, or architecture.
- `Effort`: `1` localized change, `5` broad refactor/migration with cross-module coordination.

## Active Backlog

### Priority Order

1. Pipeline autopilot, planning, resume, and recovery interconnections.
2. Cost and LLM controls.
3. Analytics projection and embeddings.
4. Publish durability, WordPress/public entity alignment, and public-site QA.
5. User-facing output quality and editorial contracts.
6. PDF/performance hotspots.
7. Architecture, schema compatibility, and observability gates.
8. Simplification and boundary cleanup.

### 1. Cost and LLM Controls

- **Title:** Route Browser Use direct calls through the canonical reserved-spend policy [Impact: 5/5, Effort: 2/5]
  - Problem fixed: Canonical OpenAI and OpenRouter calls now reserve exact matched-median in-flight spend atomically, release it when canonical usage is recorded, and finalize the projection at call completion. Browser Use's direct vendor clients still bypass that policy, and there is no expiry-bound, actor-attributed operator override.
  - Why implement: Extends the newly proven hard-limit behavior to the remaining expensive provider path without allowing browser automation or unbounded overrides to create a spend blind spot.
  - Tradeoffs / risks: Browser client wiring must not add another provider boundary or cause a reservation to survive a crashed worker beyond its bounded TTL.
  - Acceptance Criteria:
    - Browser Use OpenAI/OpenRouter calls use the same canonical pre-call reservation and post-call release as public LLM service calls.
    - YAML-backed, expiry-bound overrides require actor, reason, and scope; every override is durably logged and reconciled to actual canonical cost.
    - Breaches and overrides emit typed events with provider, action, reservation, actor/reason, and expiry fields.
    - Process-level tests cover concurrent Browser Use admission, expired reservation recovery, and override expiry without bypassing actual cost accounting.

- **Title:** Implement budget-aware model routing and compaction policy rollout [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Deterministic pre-call compaction exists for JSON chat request contracts, but model resolution is still mostly static through configured OpenAI models and namespace matching. `llm_service` records budget policy as not configured.
  - Why implement: Reduces cost, latency, timeout risk, and unreviewable ad hoc prompt trimming.
  - Tradeoffs / risks: Requires careful evidence-retention tests and benchmark ownership.
  - Acceptance Criteria:
    - Policy table maps task families to model tier, max input budget, fallback tier, and quality threshold.
    - Routing decision, budget decision, compaction strategy, and reason are logged for each call.
    - Existing deterministic compaction policy is wired into each budgeted model-call family, not only direct JSON chat request contracts.
    - Regression tests protect evidence retention on a fixed prompt/output corpus across the routed task families.
    - Benchmarks show token/cost reduction without quality regression on that corpus.





---

### 2. Analytics Projection, Signals, and Embeddings

- **Title:** Add claim embedding freshness, retention, and cost controls [Impact: 4/5, Effort: 2/5]
  - Problem fixed: Embedding records now persist locally, but operators need visibility into stale content, failed attempts, model-version drift, and avoidable re-embedding spend.
  - Why implement: Prevents silent embedding drift and unnecessary provider calls while making retry/cleanup decisions operationally visible.
  - Tradeoffs / risks: Needs concise reporting so this does not become another dashboard surface.
  - Acceptance Criteria:
    - A lightweight report summarizes embedded, pending, failed, stale, and model-version-mismatched claim counts by publisher/report/topic.
    - Retention policy documents and tests which historical embedding versions are kept or pruned.
    - The embedding workflow skips unchanged rows with a logged cost-avoidance count.
    - Tests cover stale-count reporting, failed retry visibility, retention pruning, and unchanged-row skip accounting.

- **Title:** Add semantic evidence preselection quality and cost benchmark [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Briefing and Signal evidence preselection now uses persisted claim embeddings, but the cap and ranking policy should be measured against existing projected corpora so quality gains and prompt-size reductions stay explicit as reports accumulate.
  - Why implement: Prevents silent recall loss, tunes prompt-size reduction with evidence, and gives operators a regression signal for embedding model/version changes.
  - Tradeoffs / risks: Needs a stable corpus and clear citation-coverage metric to avoid noisy benchmark churn.
  - Acceptance Criteria:
    - A benchmark command compares deterministic fallback vs embedding-backed preselection on existing projected reports without synthesizing fixtures.
    - Output reports prompt character/token deltas, selected evidence overlap, source-report coverage, and citation coverage by Briefing/Signal run.
    - The benchmark fails or warns when semantic preselection reduces required citation/source coverage below a documented threshold.
    - Tests cover benchmark metric calculation, stale/no-embedding fallback metrics, and deterministic output ordering.

---

### 3. Publish Durability and WordPress Alignment

- **Title:** Rename the publish snapshot as Publish Readiness and retain synchronous idempotent publishing [Impact: 4/5, Effort: 2/5]
  - Problem fixed: `publish_queue_orchestrator.py` is live in UI/ops flows but only builds a read-only snapshot from HTML files and publish state; its queue name overstates its behavior.
  - Why implement: Makes the operator workflow accurate without adding premature queue/outbox infrastructure.
  - Tradeoffs / risks: Publishing remains synchronous until retained evidence shows recurring partial WordPress failures or retry-recovery gaps that require durable jobs.
  - Acceptance Criteria:
    - Contracts, UI labels, docs, and logs use `Publish Readiness` terminology for the read-only feature.
    - Publish remains synchronous, idempotent, and restricted to WordPress draft or review-required status by default.
    - The readiness output records validation, evidence, health, duplicate-suppression, and operator-review blockers.
    - Failure-injection tests cover restart, retry, duplicate dispatch, and partial WordPress failures; findings are retained as evidence for or against a future outbox.

- **Title:** Stop WordPress from synthesizing intelligence, freshness, and authority claims at render time [Impact: 5/5, Effort: 3/5]
  - Problem fixed: README says WordPress must assemble approved projections/artifacts, but current WordPress shortcode/stat code still computes weekly signals, strategic themes, freshness-style movement, and publisher authority from WordPress counts and dates.
  - Why implement: Keeps analytical claims owned by the Python pipeline and reproducible from approved artifacts.
  - Tradeoffs / risks: Homepage modules need replacement data contracts and fail-closed behavior when projections are absent.
  - Acceptance Criteria:
    - WordPress intelligence modules read approved projection/artifact data instead of deriving claims from live WP queries.
    - Missing projections fail closed with neutral UI or admin-visible diagnostics.
    - Tests prove no Signal, freshness, strategic-theme, or publisher-authority claim is generated solely from WordPress post counts.
    - README documents the projection source used by each WordPress intelligence module.

- **Title:** Harden hosted WordPress launch trust surface [Impact: 5/5, Effort: 2/5]
  - Problem fixed: The hosted public site currently fails HTTPS for the tested hostname, publishes HTTP sitemap URLs, exposes a fatal WordPress/PHP stack trace on `/publisher/not-extracted/`, and lacks the expected branded failure surface for production incidents.
  - Why implement: A trust-positioned intelligence product cannot feel premium or reliable while transport security, error handling, and infrastructure disclosure are visibly broken.
  - Tradeoffs / risks: Requires coordinated hosting, WordPress configuration, and deployment validation; staging and production behavior must be verified separately.
  - Acceptance Criteria:
    - `https://marketlense.medianewsonline.com/` serves successfully and HTTP requests redirect to HTTPS.
    - Robots and sitemap URLs use HTTPS canonical URLs.
    - Public fatal errors never expose PHP stack traces, plugin paths, server filesystem paths, or WordPress troubleshooting internals.
    - Branded 404/500 pages render with safe copy, navigation, and no diagnostic leakage.
    - A hosted smoke test verifies HTTPS, canonical sitemap URL, representative public pages, and safe error behavior.

- **Title:** Add real public intake flows for briefing, correction, and report submission CTAs [Impact: 5/5, Effort: 2/5]
  - Problem fixed: The live `Request a briefing`, `Send a correction`, and `Start a submission request` paths loop back to informational pages and do not expose a form, email, calendar, or structured intake workflow.
  - Why implement: Broken conversion paths make the site look unfinished and prevent strategic leads, corrections, and source submissions from reaching operators with usable context.
  - Tradeoffs / risks: Intake must avoid collecting secrets or unnecessary personal data and must route submissions without introducing a new external boundary unless explicitly reviewed.
  - Acceptance Criteria:
    - Briefing, correction, and submission CTAs each lead to a working intake path with explicit required fields and confirmation state.
    - Correction intake requires report URL, section, source-backed correction text, and contact details.
    - Submission intake requires source URL/upload location, publisher, publication date when known, region when known, urgency, and business context.
    - Submitted requests are persisted or delivered through an approved service boundary with structured logs and redaction.
    - Tests or hosted smoke checks cover successful submission, validation errors, spam/empty input rejection, and CTA routing.

- **Title:** Polish mobile search, navigation, and responsive public workflows [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Mobile QA found horizontal overflow on search results, a cramped archive/search control row, an unfinished-looking mobile menu overlay, a stray bullet artifact near the open menu, a very tall hero text stack, and clipped desktop header search placeholder text.
  - Why implement: Search and navigation are primary workflows; responsive defects make the product feel less mature than its content architecture.
  - Tradeoffs / risks: Changes should be scoped to theme/UI behavior and must not alter archive query semantics or WordPress projection contracts.
  - Acceptance Criteria:
    - Homepage, search results, reports archive, report detail, contact, and submit pages have no horizontal overflow at 390px, tablet, and desktop widths.
    - Mobile menu uses an accessible button with open/close state, focus behavior, and a visually intentional panel/backdrop.
    - Header search input and button labels fit without clipping across tested widths.
    - Mobile search/filter/sort controls remain usable without layout shifts or overlapping text.
    - Visual browser smoke screenshots are captured for the key public pages and retained as release evidence.

- **Title:** Raise report-card and evidence-exhibit presentation to premium editorial quality [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Report cards and detail pages expose raw OCR/table fragments, labels like `Additional figure 2`, blank or weak thumbnails, repeated generated summaries, and internal identifiers such as `f1`/`q3` without enough editorial context.
  - Why implement: The report detail structure is strategically valuable, but raw extraction artifacts make the experience feel automated rather than analyst-curated.
  - Tradeoffs / risks: Exhibit and card titles must be source-grounded and deterministic; editorial polish must not fabricate claims or hide evidence provenance.
  - Acceptance Criteria:
    - Report cards use concise, analyst-quality summaries with no raw extraction prefixes, OCR fragments, or duplicate generated boilerplate.
    - Exhibit cards render human-readable titles and captions instead of raw table strings or generic figure numbers.
    - Blank or low-information thumbnails are replaced by deterministic branded covers or validated source previews.
    - Evidence identifiers remain available for audit but are presented with readable labels and source context.
    - Regression checks fail when public card/exhibit copy contains known leakage patterns such as `F1`, `Additional figure`, `Overview ... Executive summary`, or required-field placeholders.

- **Title:** Reduce hosted public-site latency toward the committed performance targets [Impact: 4/5, Effort: 3/5]
  - Problem fixed: The hosted SEO/performance gate now records stable representative metrics, but homepage, report archive, and signal archive response-start and DOM-complete timings remain much slower than the documented targets.
  - Why implement: The new gate should drive measurable speed gains for discovery and research workflows instead of only preventing worse regressions.
  - Tradeoffs / risks: Optimizations must not weaken public metadata, archive completeness, WordPress projection contracts, or the no-runtime-intelligence-synthesis boundary.
  - Acceptance Criteria:
    - A hosted baseline comparison run shows response-start and DOM-complete reductions for homepage, report archive, briefing archive, signal archive, methodology, contact, and submit pages against `out/public_site_seo_performance_live.json`.
    - At least the homepage, report archive, and signal archive meet or materially move toward the `target` values in `config/public_site_baselines.yaml`, with any remaining gap documented.
    - The gate continues to pass all SEO/social metadata checks and records request count plus page weight without increasing either metric above the current baseline.
    - Tests or hosted smoke evidence prove optimizations do not remove approved public contracts, canonical URLs, Open Graph tags, or Twitter metadata.

---

### 4. PDF, Dashboard, and Runtime Performance

- **Title:** Make retained PDF benchmark evidence executable in CI [Impact: 5/5, Effort: 3/5]
  - Problem fixed: CI deliberately permits missing retained PDF and crop-refine assets, so both benchmark artifacts become warned and currently require expiry-dated release-evidence waivers instead of providing executable evidence.
  - Why implement: Restores the intended release guarantee: candidate and crop-refine equivalence, runtime, and estimated model-work regressions are independently verified on every release SHA.
  - Tradeoffs / risks: The corpus must remain non-secret, licensed, integrity-pinned, and bounded in download/runtime; do not replace retained artifact verification with synthetic fixtures or silently treat missing evidence as passing.
  - Acceptance Criteria:
    - CI securely materializes the existing approved benchmark PDFs and generated crop artifacts (or an integrity-pinned retained corpus) before the two benchmark gates run.
    - Candidate, crop-refine, trend, health-scorecard, manifest, and release review all pass without `--allow-missing-assets` warnings or release-evidence waivers.
    - Corpus manifests record source, license/retention decision, SHA-256 hashes, and expected paths; missing or hash-mismatched inputs fail the release gate.
    - A real CI run on the exact release SHA publishes fully passing benchmark evidence and retires the temporary PDF waiver entries.

- **Title:** Promote final-crop QA sidecars into release scorecards and selection telemetry [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Final crop QA now emits DPI, quality score, defect labels, and table/chart/card detector diagnostics, but release evidence and selection summaries still rely mostly on candidate/crop signatures and manual visual review.
  - Why implement: Makes the new deterministic detectors operational: regressions become visible by report, candidate type, publisher, and crop profile, and selection can prioritize high-quality accepted crops without waiting for manual review.
  - Tradeoffs / risks: Metrics must remain diagnostic until retained real-artifact baselines prove stable, and public rendering must not expose raw QA internals.
  - Acceptance Criteria:
    - Run health scorecards and release evidence manifests can ingest final crop `.qa.json` sidecars and report accepted/rejected counts, mean/min quality score, defect-label counts, detector confidence bands, render DPI, and artifact-size deltas.
    - Figure selection telemetry records the selected crop profile, QA sidecar path, total score, defect labels, and detector summary for each accepted user-facing crop.
    - Benchmarks compare the same existing report artifacts before/after profile changes and flag quality-score drops, clipped-boundary increases, or unexpected storage/runtime growth.
    - Tests cover sidecar aggregation, missing-sidecar failure reporting, redaction of diagnostics from public output, and no change to default no-model crop behavior.

### 5. User-Facing Output Quality and Editorial Contracts

- **Title:** Extend the retained public-advisory benchmark to scored insight quality [Impact: 4/5, Effort: 2/5]
  - Problem fixed: `public_advisory_render_benchmark.py` already measures public claim support and `so_what`/`now_what` availability, but it does not yet measure role diversity, duplicate overlap, report-lens support, or metric-backed score calibration.
  - Why implement: Converts the new contract fields into a measurable quality loop and prevents score/role drift from becoming decorative metadata.
  - Tradeoffs / risks: The benchmark must evaluate source-grounded structure and diversity without brittle wording expectations.
  - Acceptance Criteria:
    - A quality command evaluates existing report-analysis artifacts for role diversity, duplicate insight overlap, non-empty `so_what`/`now_what`, supported report lens, metric-backed score calibration, and evidence linkage.
    - Output compares current artifacts against a saved baseline and reports improvements/regressions by publisher/report family.
    - The benchmark can run in default read-only mode without model calls and optionally sample live regeneration behind an explicit flag.
    - Tests cover metric calculation, narrow-report fallback, unsupported-role detection, and unchanged-artifact baseline stability.

- **Title:** Complete concise public evidence, methodology, and related-content surfaces [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Rendering already exposes readable claim-support labels, methodology material, and public-intelligence cards while redacting canonical IDs; the remaining gap is a compact public source/excerpt/limitation contract and the first useful related-content links.
  - Why implement: Readers need a compact, decision-useful way to verify a claim and discover relevant research.
  - Tradeoffs / risks: Public output must remain source-grounded and concise; OCR/model/crop/vector diagnostics remain operator-only.
  - Acceptance Criteria:
    - High-impact claims can render report title, publisher, source page, a short supporting excerpt where useful, material limitation, and original-report link without leaking paths, extraction fragments, or canonical evidence IDs.
    - Methodology surface shows publisher, publication date, geographic/temporal scope, original-report methodology when available, source pages, material limitations, and a simple evidence state.
    - Report pages begin with related reports, related briefings, topic links, and publisher links; other relationship modules require measurable engagement and useful inventory before promotion.
    - Tests prove public output redacts internal processing diagnostics and fails closed when approved evidence/projection data is absent.


- **Title:** Add advisory `so_what` / `now_what` remediation from retained render benchmark gaps [Impact: 4/5, Effort: 3/5]
  - Problem fixed: The retained public-advisory benchmark can now measure `so_what` and `now_what` coverage, and live verification found older retained artifacts with advisory coverage but zero `so_what`/`now_what` availability.
  - Why implement: Converts benchmark gaps into targeted artifact remediation so public advisory pages become more decision-useful without broad regeneration.
  - Tradeoffs / risks: Repairs must remain source-grounded, target only affected artifact families, and keep benchmark output as evidence rather than a brittle text fixture.
  - Acceptance Criteria:
    - Benchmark rows with missing `so_what` or `now_what` produce typed remediation targets linked to the affected report and artifact family.
    - Targeted regeneration fills missing fields only when source support exists and records abstentions when it does not.
    - Release evidence reports coverage improvement across retained artifacts and flags unsupported attempted repairs.
    - Tests cover missing-field target creation, grounded repair acceptance, abstention behavior, and unchanged public rendering when fields remain unsupported.

### 6. Architecture, Schema Compatibility, and Observability

- **Title:** Operationalize lineage-driven selective regeneration and cost reporting [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Canonical artifact lineage now records retained checkpoint artifacts, dependency edges, compatibility metadata, and invalidation state, but pipeline planning does not yet choose the smallest valid regeneration plan or quantify avoided work from those decisions.
  - Why implement: Converts the new lineage foundation into measurable LLM/PDF/render cost and latency reductions while preserving source-to-publication traceability.
  - Tradeoffs / risks: Regeneration planning must remain fail-closed on missing provenance, preserve checkpoint compatibility, and never treat an invalidated artifact as reusable.
  - Acceptance Criteria:
    - A typed planner maps source, prompt, template, crop, and validator changes to the minimal checkpoint stage(s) requiring regeneration.
    - Report and cross-report publish workflows consult compatibility-aware lineage reuse before model, PDF, crop, render, and publication work.
    - A bounded quality command reports invalidation fan-out, compatible reuse hits/misses, avoided provider/PDF/render work, and lineage coverage by artifact family.
    - Retained-artifact regression tests prove render-only changes reuse analysis and source changes never reuse dependent artifacts.

- **Title:** Publish release evidence reviews into CI job summaries and PR release notes [Impact: 3/5, Effort: 2/5]
  - Problem fixed: Release evidence review Markdown is now generated and archived, but reviewers still need to open the artifact bundle to see the approval surface.
  - Why implement: Puts unwaived issues, waived issues, owners, expiry dates, and artifact freshness directly where release reviewers already work.
  - Tradeoffs / risks: Requires careful formatting and stable links so CI output stays concise and auditable.
  - Acceptance Criteria:
    - CI appends the generated release evidence review Markdown to the GitHub job summary after the approval gate runs.
    - Pull request or release-note automation links the archived `release-evidence-bundle` artifact and includes the final approval status.
    - Summary output remains bounded for large manifests while preserving all unwaived issue details.
    - README documents where reviewers should inspect the inline summary versus the full archived bundle.

- **Title:** Extend CI gates into role-mixing and monolith-growth enforcement [Impact: 4/5, Effort: 3/5]
  - Problem fixed: The repo already has broad CI coverage. The remaining useful gap is automation for role mixing, direct-I/O drift, service integration coverage waivers, and first-party long-file growth.
  - Why implement: Prevents architectural drift earlier and keeps the current rule set enforceable.
  - Tradeoffs / risks: Requires careful allowlist design for legitimate edge cases.
  - Acceptance Criteria:
    - Gate logic flags role mixing, direct I/O drift, or monolith-growth violations on first-party files.
    - Allowlist entries require owner plus expiry date.
    - Missing per-service integration coverage requires a marked test or explicit temporary waiver.
    - README documents how to add and retire waivers.

- **Title:** Restore service-quality coverage above the pre-June snapshot [Impact: 4/5, Effort: 3/5]
  - Problem fixed: The measured full-suite service coverage is 82.5763%, above the enforced 47% package floor but below the previous 82.9680% aggregate snapshot after substantial service growth in accounting, browser acquisition, PDF, and lineage capabilities.
  - Why implement: Recovering targeted coverage keeps the quality snapshot a true non-regression signal and hardens the service boundaries that now own more durable workflow state.
  - Tradeoffs / risks: Add behavior-focused tests for real service contracts and failure recovery; do not weaken the enforced floor, add exemptions, or use coverage-only execution paths.
  - Acceptance Criteria:
    - Full default coverage reaches or exceeds 82.9680% for `src/services` without reducing global, generator, or orchestrator coverage.
    - New coverage prioritizes canonical ledger recovery, browser worker lifecycle, and artifact-lineage failure paths with observable contract or persisted-state assertions.
    - The quality baseline is refreshed only from a passing full CI run and records the exact resulting SHA.

- **Title:** Surface canonical LLM projection lag to budget and release gates [Impact: 5/5, Effort: 2/5]
  - Problem fixed: Incremental token/cost exports intentionally lag by up to nineteen canonical events, but operators and budget decisions do not yet see that lag or its possible cost impact.
  - Why implement: Makes the batching performance gain safe for live spend controls and release evidence.
  - Tradeoffs / risks: The gate must distinguish normal bounded lag from a failed or stalled projection and must not force a full rebuild on every read.
  - Acceptance Criteria:
    - Projection status reports checkpoint event ID, latest canonical event ID, pending-event count, pending estimated cost, and last successful projection time.
    - Run-budget and release evidence consume that status and either account for pending canonical usage directly or require an explicit fresh projection before a hard spend or release decision.
    - Tests cover normal bounded lag, threshold projection, missing checkpoint, stalled projection, and no-unnecessary-rebuild behavior.


---

### 7. Pipeline Autopilot, Resume, and Recovery Interconnections

- **Title:** Quarantine malformed Drive PDFs after bounded redownload attempts [Impact: 4/5, Effort: 2/5]
  - Problem fixed: Live ingest found a Drive PDF source that remained missing its EOF marker after cache invalidation and redownload; the pipeline now stops before expensive report work, but operators still need durable quarantine/remediation state.
  - Why implement: Repeated malformed-source retries waste Drive/API time and hide source-quality problems from batch operators.
  - Tradeoffs / risks: Quarantine must be reversible after the source file is replaced and must not suppress transient download failures that recover on retry.
  - Acceptance Criteria:
    - After bounded redownload attempts fail PDF integrity checks, the state DB records a typed malformed-source quarantine with file ID, md5/size, error taxonomy, and next action.
    - Future ingest skips quarantined sources by default, with an explicit `--rescan` or repair command to clear or revalidate quarantine after source replacement.
    - Dashboard/CLI output lists quarantined Drive files and recommended remediation.
    - Tests cover quarantine write, default skip, explicit revalidation, and clearing after a valid replacement PDF.

- **Title:** Expose existing supervisor planning as a single pipeline plan before execution [Impact: 5/5, Effort: 3/5]
  - Problem fixed: `AutonomousRunSupervisorPlan` already produces typed workflow-control decisions, but CLI/UI callers cannot yet use one explicit plan contract to inspect and approve the safest next action across entrypoints.
  - Why implement: A plan-first control layer lets the pipeline need less user direction: users can request an intent such as `process ready reports`, `repair failed runs`, or `publish ready artifacts`, while the system decides which steps to run, skip, resume, or block.
  - Tradeoffs / risks: Requires careful scope control so the planner does not become a second orchestration implementation or embed domain logic.
  - Acceptance Criteria:
    - The public `PipelinePlan` contract adapts the existing `AutonomousRunSupervisorPlan` and lists ordered steps, skipped steps, blockers, required credentials, side-effect boundaries, resume points, idempotency keys, and expected outputs.
    - A planner uses existing services/read models to inspect current state without performing side effects.
    - CLI/UI can run a read-only plan mode before execution and can execute an approved plan through existing orchestrators.
    - Tests cover ready, partially complete, failed, missing-credential, and publish-only states with plan contract and log assertions.

- **Title:** Complete config-driven autopilot profiles for common pipeline intents [Impact: 4/5, Effort: 2/5]
  - Problem fixed: Workflow control already resolves intent maps and preflight profiles such as `safe_default`, `repair_failed`, `publish_ready`, and `browser_acquisition`, but operators cannot yet select a complete, documented run profile that resolves all approved low-level settings.
  - Why implement: Profiles let users choose intent, not implementation details, and let the planner select safe defaults based on current state.
  - Tradeoffs / risks: Profiles must be thin presets over existing typed settings, not a parallel configuration system.
  - Acceptance Criteria:
    - YAML defines documented profiles such as `safe_default`, `fast_cached`, `repair_failed`, `publish_ready`, `browser_acquisition`, `cost_saver`, and `high_quality`.
    - The planner can recommend or apply a profile while logging every resolved low-level setting that changes behavior.
    - Profile resolution validates against the existing settings contract and never hides secrets in YAML.
    - Tests cover profile selection, explicit override precedence, invalid profile names, and deterministic resolved settings.

- **Title:** Promote existing UI dead letters into durable autonomous remediation records [Impact: 5/5, Effort: 3/5]
  - Problem fixed: UI-run dead letters and typed failure classifications exist, but failed autonomous work is not yet represented as durable, workflow-wide remediation records.
  - Why implement: Failed runs should become managed work items that can be retried, resumed, repaired, or escalated without users reconstructing context.
  - Tradeoffs / risks: Needs attempt budgets and loop prevention so the system does not repeatedly spend on irreparable failures.
  - Acceptance Criteria:
    - Dead-letter records include run ID, workflow, failing step, `AppError` taxonomy, retry decision, checkpoint stage, input checksum, artifact refs, remediation code, and runbook link.
    - A reaper orchestrator retries transient failures after cooldown, resumes from valid checkpoints, invokes targeted repair where available, and escalates only irreducible blockers.
    - Attempt budgets, terminal states, and duplicate suppression are enforced through idempotency.
    - Tests cover transient recovery, permanent failure, missing credentials, stale checkpoint, repeated failure loop prevention, and runbook surfacing.

- **Title:** Add a run-level budget manager for cost, tokens, time, retries, and external calls [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Cost, retry, latency, worker, browser, and model limits are configured or reported in separate places, but no online budget manager enforces total run/day/publisher constraints before each expensive action.
  - Why implement: Autonomous execution needs predictable spend, runtime, and call ceilings without operator babysitting.
  - Tradeoffs / risks: Budget enforcement must distinguish warning, defer, stop, and approved override outcomes without silently dropping work.
  - Acceptance Criteria:
    - A typed `RunBudget` contract tracks max USD, model calls, tokens, wall-clock time, retries, browser launches, Drive writes, WordPress writes, and PDFs per batch by run/day/publisher scopes.
    - Before each model call, the manager reads the exact historical median for the matching provider/action/model/prompt namespace from `llm_usage_medians`, records the forecast sample count and projected tokens/USD, and uses only an explicit cold-start policy when no matching history exists.
    - Orchestrators check budget before model, browser, OCR, Drive, and WordPress side effects and emit typed budget decisions.
    - The health scorecard consumes final budget usage and reports avoided calls, budget breaches, and override usage.
    - Tests cover normal use, warning thresholds, hard stop, defer, override, and structured log fields.

- **Title:** Add model fallback policies by failure class and artifact family [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Model selection is mostly namespace-static, so the system cannot automatically switch to cheaper models for easy work or stronger/different models for repeated schema or validation failures.
  - Why implement: Policy-driven fallback within the existing provider contract can reduce cost on easy tasks and rescue difficult artifacts without user intervention.
  - Tradeoffs / risks: Fallback must preserve reproducibility and must be forbidden when policy requires same-model replay; multi-provider failover remains deferred under the decision register.
  - Acceptance Criteria:
    - YAML fallback policy maps artifact family and failure class to an approved existing-provider model tier, temperature, max attempts, schema compatibility, and reproducibility constraints.
    - Fallback decisions are orchestrator-visible, bounded, logged, and included in cost/health evidence.
    - Generators continue to consume one typed LLM response contract.
    - Tests cover cheap-primary success, schema-failure fallback, validation-failure fallback, fallback exhaustion, reproducibility-forbidden fallback, and cost reporting.

- **Title:** Auto-skip or route business-domain-only gated forms before mailbox polling [Impact: 4/5, Effort: 2/5]
  - Problem fixed: Several live gated publishers reject non-business delivery addresses before a report email can be requested, and a 2026-07-06 BigCommerce rerun proved browser identity email drift from the IMAP mailbox can turn a deliverable route into `blocked_email_domain` until corrected.
  - Why implement: Converts repeated external constraints and local identity/mailbox drift into fast, unattended route policy so the system avoids doomed submissions and spends browser budget on publishers where delivery is possible.
  - Tradeoffs / risks: The blocker must be evidence-backed and publisher-scoped with TTL so a future accepted mailbox or changed form does not stay permanently suppressed.
  - Acceptance Criteria:
    - `blocked_email_domain` outcomes persist publisher-scoped route policy with observed field label, host, and evidence timestamp.
    - Browser identity delivery email, work/professional email fields, and mailbox IMAP user are preflighted for domain alignment before email-form submission.
    - Form automation maps only configured, verified identity facts to host-specific option labels; it never infers or invents job title, seniority, company size, revenue, department, industry, or organization type.
    - Future same-publisher gated candidates fail fast as typed `email_required / blocked_email_domain` unless an eligible configured business-domain mailbox is available.
    - Workflow-control reports avoided browser launches and skipped mailbox polls for the policy decision.
    - Live verification covers at least one publisher already observed with `blocked_email_domain` and shows reduced runtime without an operator step.
    - Tests cover policy TTL expiry, mailbox-availability override, exact-URL versus publisher-scope behavior, and required structured logs.

- **Title:** Persist anti-bot and CAPTCHA acquisition blockers as route policy [Impact: 4/5, Effort: 2/5]
  - Problem fixed: Live Genetec and Proximic reruns reached external access controls (`HTTP 403` and interactive CAPTCHA) after generic form/onsite handling was fixed, but that blocker evidence is not yet promoted into fast autonomous route policy.
  - Why implement: Avoids repeated browser/model spend on publisher paths that cannot currently be completed unattended and lets discovery prioritize alternate report mirrors, direct PDFs, or mailbox routes.
  - Tradeoffs / risks: Policies must be TTL-bounded and scoped to the exact host/route family so temporary protection changes do not suppress future valid acquisition.
  - Acceptance Criteria:
    - `blocked_captcha`, `blocked_access_forbidden`, and equivalent HTTP anti-bot outcomes persist host, URL, route family, evidence type, first/last seen timestamps, and TTL.
    - Planner preflight consults blocker policy before browser launch and either selects a cheaper alternate route or returns a typed unattended blocker with avoided-cost telemetry.
    - Discovery reruns can rank alternate publisher URLs above known blocked exact URLs without changing artifact verification requirements.
    - Live verification covers one exact-URL fast-fail, one alternate-route success or attempted discovery rerank, and one TTL-expired retry.
    - Tests cover policy scoping, TTL expiry, avoided browser/model logging, and preservation of current behavior when no blocker evidence exists.

- **Title:** Expose existing model-call replay bundles through a drift-comparison command [Impact: 4/5, Effort: 2/5]
  - Problem fixed: `llm_service.build_model_call_replay_bundle(...)` already produces a typed replay bundle, but operators still need a first-class command to select retained calls and compare prompt/model/schema/cache drift without making provider calls by default.
  - Why implement: Replayable audit review shortens debugging of model regressions and makes prompt or schema drift visible before costly reruns.
  - Tradeoffs / risks: Replay output must preserve redaction and must require explicit opt-in before any live provider call.
  - Acceptance Criteria:
    - CLI reads structured logs or retained audit artifacts and emits a deterministic replay bundle for a selected run/model call.
    - Drift comparison reports prompt hash, rendered-prompt redaction hash, model, seed support, schema version, cache key, validation status, and response ID differences.
    - Live-provider replay is disabled by default and requires an explicit flag plus budget confirmation.
    - Tests cover audit extraction, redacted bundle output, missing audit fields, cache-hit records, and drift comparison.

### 8. Simplification and Boundary Cleanup

#### 1. Canonical Service-Boundary Simplification

- **Title:** Audit top-level service proliferation and demote internal capabilities [Impact: 4/5, Effort: 4/5]
  - Problem fixed: Many top-level service files appear to be internal capabilities rather than true external-system boundaries.
  - Why implement: Makes service ownership easier to discover and reduces peer-boundary confusion.
  - Tradeoffs / risks: Requires careful compatibility facades for public imports.
  - Acceptance Criteria:
    - Every top-level service is classified as an external system boundary, canonical service boundary, or candidate internal capability.
    - Internal capabilities move under private subpackages only when semantic ownership improves.
    - Public imports remain compatible or migration is explicitly approved.

---

#### 2. Generator and Orchestrator Role-Boundary Cleanup

- **Title:** Audit large orchestrators for domain-logic leakage [Impact: 4/5, Effort: 4/5]
  - Problem fixed: Several orchestrators approach 800-1,000 lines and may mix control flow with domain decisions.
  - Why implement: Reduces future drift and improves test isolation.
  - Tradeoffs / risks: Must avoid size-only splitting and preserve behavior.
  - Acceptance Criteria:
    - Each audited orchestrator has a role classification note and list of any domain decisions found.
    - Domain decisions move to generators only with red tests and movement audit evidence.
    - Pipeline tests prove retry counts, state transitions, and idempotency remain unchanged.

- **Title:** Consolidate publish orchestration surfaces [Impact: 5/5, Effort: 5/5]
  - Problem fixed: Publish workflow logic appears across publish orchestrator, publish queue/readiness, shared publish helpers, publish generator, and WordPress service paths.
  - Why implement: Reduces duplicate validation and side-effect sequencing.
  - Tradeoffs / risks: Broad workflow refactor with state and WordPress side effects.
  - Acceptance Criteria:
    - One canonical publish workflow owns state transitions and side-effect sequencing.
    - Queue/readiness/batch variants call the canonical workflow or are explicitly read-only.
    - Tests cover validation block, successful publish, duplicate publish, partial WordPress failure, and retry behavior.

---

#### 4. PDF and Visual-Heuristics Simplification

- **Title:** Reduce PDF visual heuristics facade export surface [Impact: 4/5, Effort: 4/5]
  - Problem fixed: The visual heuristics facade re-exports many private helpers, making the compatibility surface large.
  - Why implement: Shrinks private-helper coupling and makes semantic ownership clearer.
  - Tradeoffs / risks: Tests and internal callers may currently rely on compatibility exports.
  - Acceptance Criteria:
    - Public facade exports only stable operations needed by external callers.
    - Internal callers import semantic owner modules directly where appropriate.
    - Compatibility exports are removed only after tests prove no external dependency.

- **Title:** Preserve PDF service as one canonical external/library boundary while reducing internals [Impact: 4/5, Effort: 4/5]
  - Problem fixed: PDF internals are already split into many private capability modules; further splits should reduce coupling, not just file size.
  - Why implement: Prevents both monolith growth and fragmentation.
  - Tradeoffs / risks: Requires architecture review if three or more peer modules are introduced.
  - Acceptance Criteria:
    - Any PDF simplification keeps `pdf_service.py` as the canonical boundary.
    - New private modules have semantic ownership and no pass-through-only wrappers.
    - Real PDF fixture outputs remain equivalent or approved deltas are documented.

---

#### 5. WordPress and Frontend Simplification

- **Title:** Split or simplify the large WordPress shortcode class by semantic shortcode ownership [Impact: 4/5, Effort: 4/5]
  - Problem fixed: The shortcode class owns many archive and rendering surfaces, including legacy Signal and Briefing archive renderers.
  - Why implement: Reduces PHP god-class risk and improves runtime testability.
  - Tradeoffs / risks: Requires WordPress runtime harness coverage and compatibility preservation.
  - Acceptance Criteria:
    - Shortcode handlers are grouped by semantic public surface, not arbitrary file size.
    - Shared view-model logic moves to existing builder classes where appropriate.
    - Runtime tests prove current shortcode output remains compatible.

## Backlog Decision Register

This register governs promotion from the migrated intake archive. A proposal is not active work until current behavior is revalidated, a baseline is measured, and the proposal is added to the active backlog with an owner and review date.

### Permanent Exclusions

- **Cross-publisher metric normalization:** never normalize metrics across differing report definitions, publishers, geographies, or methodologies. Cross-report work may compare themes, evidence direction, assumptions, methodologies, audience implications, and convergent/divergent conclusions only.
- **Public progressive enrichment:** never publish incomplete pages for later caption, signal, social, or validation enrichment. Draft-first generation is allowed only in local preview, WordPress draft status, or an operator-only preview URL.
- **Autonomous identity generation:** never infer or invent job title, seniority, company size, revenue, department, industry, or organization type. Host-specific option mapping is allowed only for configured, verified identity facts.
- **Automatic lower private-API promotion thresholds:** retain conservative global thresholds. Any exception requires manual approval, publisher scope, expiry, tested fallback route, artifact validation, and automatic rollback on drift.
- **Public pipeline-diagnostics panel:** publish compact methodology and evidence state only. OCR, model regeneration, crop, vector-store, and validation diagnostics remain operator-only.

### Deferred Until Operating Evidence Requires It

| Proposal | Revisit only when |
| --- | --- |
| Full report-generation DAG scheduler | Profiling shows material idle dependency time that simpler parallel execution cannot remove. |
| Streaming Drive prefetch queue | Large batches regularly wait on Drive while processing capacity is available. |
| Live adaptive concurrency | Sustained multi-worker runs show provider throttling, SQLite contention, or browser saturation. |
| Multi-provider failover | Provider outages cause a measurable share of failed runs or a service-level commitment requires it. |
| Same-publisher warm browser workers | Same-publisher batch volume justifies process and session-isolation risk. |
| Generic pipeline-wide scheduler | Work beyond mailbox acquisition has material, sustained deferred-work volume. |
| Transactional publish outbox | Partial WordPress failures and publish retries become recurrent operational problems. |
| LinkedIn persona variants | An active distribution workflow measures the value of multiple variants. |
| Signals and Briefings expansion | Report discovery and detail usage show demand for recurring synthesis products. |

### Required Narrow Scope

- **Idempotency:** cover externally visible or non-transactional side effects—WordPress posts/media, Drive uploads, publisher-form submissions, mail-delivery requests, route promotion, and external vector-store creation. Rely on transactions, upserts, and atomic replacement for deterministic internal writes.
- **Crop profiles:** prefer measured, expiry-dated layout-family profiles such as `dark_slide`, `boxed_stat_card`, or `dense_table`. Add a publisher-specific profile only after retained failures prove a deterministic global rule cannot solve the layout; keep the fallback path.
- **Crop benchmarks:** block deterministic rejection defects, clipped edges, major contamination, minimum resolution, and a curated human-reviewed golden set. Keep unstable computer-vision metrics diagnostic until they demonstrate stable predictive value.
- **Code hygiene:** retain architecture-boundary checks, Ruff, mypy on critical packages, coverage, focused mutation tests, long-file warnings, and secret/dependency scanning. Do not add broad governance dashboards or universal changed-file mutation requirements without a demonstrated quality gap.

### Autonomous Publishing Guardrail

Supervisor workflows may start, resume, retry, repair, validate, render, create a draft, hold, and notify. They must not make the final public-publish decision until a retained production corpus demonstrates safe claims, no internal-ID leakage, stable crop acceptance and WordPress updates, duplicate suppression, reliable rollback, and consistent editorial quality. Initial automation ends in `draft` or `review_required`.

## Current-State Evidence

- Active-backlog revalidation on 2026-07-11 checked all 37 active items against the current checkout, including README change evidence, implementation/test surfaces, CI configuration, and the current WordPress theme/plugin source. No active item met all of its acceptance criteria. Partially landed foundations were narrowed in place: public-advisory rendering/benchmarking, crop-QA sidecars, workflow-control intent/preflight profiles, supervisor plans, model-call replay bundles, release-evidence review, public-intelligence metadata, and LLM-usage medians.
- CI currently runs formatting, risk classification, split-symbol linking, typing, architecture import, forbidden patching, repository hygiene, quality ledger, remediation runbook, backlog source, contract schema snapshot, WordPress subproject, default pytest with coverage, coverage gate, mutation gate, quality non-regression, prompt fixture corpus regression, and release evidence manifest archival/freshness gates through `.github/workflows/ci.yml`.
- Durable LLM usage accounting now keeps `state/llm_usage.sqlite` as the canonical source. Every twentieth normalized task event schedules an asynchronous median projection, while every twentieth canonical event incrementally advances JSONL/daily compatibility exports from the persisted last canonical event ID; source-ledger rebuild remains available for a missing or repaired checkpoint. Live verification on 2026-07-12 established a baseline at 413 events / canonical ID 448, then seven real OpenAI calls advanced the checkpoint to 420 events / ID 456. Export and source ID sets matched exactly, reconciliation passed, and a follow-up projection processed zero rows.
- On 2026-07-12, canonical accounting gained atomic call-ordinal allocation, deterministic SQLite-to-JSONL/daily projections, durable projection checkpoints, repairable reconciliation, normalized path resolution, bounded terminal-outcome taxonomy, and deterministic browser-writer shutdown accounting. A real OpenAI JSON smoke call passed in 3.34s; subsequent reconciliation of 324 retained canonical events matched the export exactly at 944,640 input and 243,719 output tokens with no repair required. Full regression verification passed at 3,753 tests / 25 deselected.
- Prompt dry-run validation and fixture-corpus regression are landed through `src/contracts/prompts.py`, `src/services/prompt_service.py`, `scripts/ci/check_prompt_fixture_regression.py`, `tests/test_prompt_dry_run_validation.py`, and `tests/test_prompt_fixture_corpus_regression.py`.
- OCR confidence gating and native-confidence-based OCR fallback controls are landed in `src/config/app.yaml`, `src/generators/report_source_generator.py`, and the quality ledger.
- Publisher discovery route memory, deferred recovery, direct-detail handling, KPI guardrail logging, and default-on rollout controls are landed. There is no active "publisher discovery rollout" backlog item unless a new measured gap is opened.
- Targeted validation regeneration and claim/evidence binding are landed through `src/generators/report_regeneration_generator.py`, `src/generators/validation/*`, and README validation docs.
- Idempotency service support is live in `src/services/idempotency_service.py` and backs publish, report-download, and publisher-inventory write paths documented in `README.md`.
- Candidate extraction already performs binary page triage and shared page-artifact/fingerprint caching through `src/services/_pdf/figures.py`, `src/services/_pdf/page_artifacts.py`, and `src/services/_pdf/fingerprint_cache.py`.
- PDF visual candidate extraction now uses indexed per-page relationships plus a lazy kept-candidate y-band overlap index behind the existing `pdf_service.collect_candidates` boundary. Side-by-side live existing-PDF verification on 2026-06-28 preserved candidate signatures on Capgemini, IAS, and Julius Baer benchmark PDFs and reduced aggregate median single-worker candidate extraction from 42.483s on `main` to 41.561s on the branch; per-PDF medians were 5.677s to 5.300s, 16.891s to 17.054s, and 19.915s to 19.207s.
- PDF candidate extraction performance/equivalence is now a repeatable gate through `scripts/quality/pdf_candidate_benchmark.py`, `scripts/ci/check_pdf_candidate_benchmark.py`, `.github/workflows/ci.yml`, and `docs/quality/pdf_candidate_extraction_benchmark_baseline.json`. A strict live run on 2026-06-28 against existing Capgemini, IAS, and Julius Baer benchmark PDFs preserved all candidate signatures/counts/degraded-page counts with no warnings; observed medians were 5.255s, 16.787s, and 20.055s versus baselines of 5.300s, 17.054s, and 19.207s.
- PDF crop/refine artifact equivalence and cost are now covered by `scripts/quality/pdf_crop_refine_benchmark.py`, `scripts/ci/check_pdf_crop_refine_benchmark.py`, `.github/workflows/ci.yml`, and `docs/quality/pdf_crop_refine_benchmark_baseline.json`. A live existing-artifact run on 2026-06-28 preserved candidate-pack signatures, crop-refine decision signatures, crop artifact hashes/counts, cached refine-decision counts, and estimated two-phase page model-call counts for IAS, Julius Baer, and Worldpanel outputs; observed medians were 0.028s, 0.077s, and 0.028s versus baselines of 0.030s, 0.076s, and 0.026s.
- PDF benchmark trend reporting is now covered by `scripts/quality/pdf_benchmark_trends.py`, `scripts/ci/check_pdf_benchmark_trends.py`, `.github/workflows/ci.yml`, and README release-gate docs. A live run on 2026-06-28 consumed existing candidate and crop-refine benchmark JSON outputs without rerunning extraction, appended bounded local history under `out/`, and passed with no warnings. A four-run replay over already-produced benchmark outputs showed candidate recent medians down 4.3%, 4.6%, and 0.7% versus the older run, crop/refine estimated model-call counts unchanged at 2, 10, and 2, and crop/refine runtime drift contained at +1.1%, +3.9%, and +0.7%.
- PDF benchmark trend evidence is now surfaced in `scripts/quality/run_health_scorecard.py` through optional retained candidate, crop/refine, and trend JSON inputs. A live scorecard run on 2026-06-28 consumed `out/pdf_candidate_benchmark_scorecard_live.json`, `out/pdf_crop_refine_benchmark_scorecard_live.json`, and `out/pdf_benchmark_trends_scorecard_live.json` without rerunning PDF extraction, wrote `out/run_health_scorecard_pdf_benchmark_live.json`, and reported complete passing evidence with 3 candidate rows, 3 crop/refine rows, and 9 trend rows. Candidate medians were 2.371s, 7.748s, and 9.512s versus baselines of 5.300s, 17.054s, and 19.207s; crop/refine medians were 0.0136s, 0.0353s, and 0.0155s versus baselines of 0.0303s, 0.0760s, and 0.0261s; estimated model-call counts stayed unchanged at 2, 10, and 2. A missing-evidence live scorecard run exited nonzero and marked PDF benchmark evidence incomplete.
- Release evidence bundle manifests are now produced by `scripts/quality/release_evidence_manifest.py` and documented in README release review flow. A live run on 2026-06-28 consumed existing retained `coverage.xml`, `mutation_results.json`, PDF candidate benchmark JSON, PDF crop/refine benchmark JSON, PDF trend JSON, and PDF health scorecard JSON without rerunning those gates, wrote `out/release_evidence_manifest_live.json`, recorded commit SHA, producer commands, schema versions, byte counts, SHA-256 hashes, timestamps, and pass/fail status for 6 artifacts, and passed with no issues. A missing-artifact live run wrote `out/release_evidence_manifest_missing_live.json`, reported `artifact_missing`, and exited nonzero.
- Release evidence manifest CI archival and freshness enforcement is now wired through `.github/workflows/ci.yml` and `scripts/quality/release_evidence_manifest.py`. CI records `RELEASE_EVIDENCE_STARTED_AT` before coverage generation, builds `out/run_health_scorecard_ci.json`, runs the manifest with `--fresh-after` and `--require-head-commit` after coverage, mutation, PDF benchmark, trend, health scorecard, and prompt gates, and uploads the manifest plus listed artifacts as the `release-evidence-bundle` artifact. A live run on 2026-06-28 consumed existing retained artifacts, wrote `out/release_evidence_manifest_freshness_live.json`, validated 6 artifact paths/schema versions/statuses/modification timestamps against `HEAD`, and passed with no issues; stale and commit-mismatch live runs wrote failure manifests and exited nonzero with `artifact_stale` and `commit_sha_mismatch`.
- Vector-store cleanup is no longer backlog: `src/services/vector_store_service.py` exposes delete/prune operations, `src/orchestrators/vector_store_retention_orchestrator.py` runs retention cleanup, and README documents `analysis.vector_store_retention_days`.
- Direct file-I/O boundary drift outside services is now guarded across generators, orchestrators, utilities, `_cli`, and `src/ui`. Remaining CLI/UI/orchestrator direct reads, existence checks, and path-kind probes were routed through `file_service` contracts, `FileStatResponse` now reports `is_file`/`is_dir`, and the role-I/O CI wrapper fails on new unwaived drift. A live report-download run on 2026-06-28 against the existing Payments NZ direct PDF completed as `pdf_download / downloaded`, wrote an 800,251-byte PDF through the branch runtime, recorded the source row and value score, and emitted service-owned file hash logs; the Drive-required variant reached live Google Drive write preflight and failed on the account's storage-quota policy before download.
- Full report-generation semantic checkpoint resume is live for `source_prepared`, `selection_complete`, `analysis_complete`, `render_complete`, and `latest_safe`. Checkpoints now carry artifact integrity metadata for existing file artifacts, `selection_complete` persists vector-store indexing state, direct corrupt/missing/hash-mismatched checkpoint resumes fail with non-retryable `AppError`s, and `latest_safe` selects the newest checkpoint whose artifacts validate. A live IAS existing-PDF run on 2026-06-28 completed fresh generation in 582.003s, then resumed successfully from `source_prepared` in 165.630s, `selection_complete` in 317.949s after a transient model-output retry, `analysis_complete` in 0.820s, `render_complete` in 0.040s, and `latest_safe` in 0.058s.
- Typed retry-decision normalization is live through `src/contracts/retry_decision.py` and `src/orchestrators/retry_orchestrator.py`. Existing retry wrappers now emit `RetryDecision` fields for `retry`, `defer`, `abort`, and `user_action_required` while preserving legacy attempt fields and bounded backoff/jitter. Verification on 2026-06-28 covered transient provider errors, validation-repair retries, DB locks, missing credentials, exhausted attempts, non-retryable contract failures, generic exceptions, negative jitter, contract round-trips, schema snapshots, full pytest with coverage, mutation gate including `retry_orchestrator.py` at 6/6 killed, quality regression, a live existing-PDF candidate extraction producing 22 candidates, a live `render_complete` report-pipeline resume returning `processed`, and a live existing-PDF vector-backed Responses run that created/uploaded/attached/indexed `out/9/Q4_2025_Quarterly-Trends-Report.pdf`, recovered from the SDK `seed` parameter incompatibility, returned strict JSON with `evidence_found=true`, and completed in 24.916s.
- Pipeline preflight before expensive report work is live through `src/contracts/pipeline_preflight.py` and `src/orchestrators/pipeline_preflight_orchestrator.py`. `run_report_pipeline` now runs a typed preflight before model client construction and blocks expensive side effects with `AppError(code="pipeline_preflight_blocked")` when prerequisites fail. The preflight checks writable output/cache/state/report paths, OpenAI model credentials, required prompt namespaces, optional live Drive write readiness with OAuth refresh remediation, browser readiness, and WordPress publish target readiness through the canonical service boundaries. Live verification on 2026-06-29 loaded the project config and publish settings, checked 19 prerequisites, found 0 blockers and 0 warnings, refreshed Drive OAuth credentials automatically, and allowed expensive work only after preflight passed.
- Retry-decision telemetry and policy tuning reports are live through `src/contracts/retry_telemetry.py`, `src/orchestrators/retry_telemetry_orchestrator.py`, `scripts/quality/retry_decision_telemetry.py`, and the run health scorecard. A live structured retry-boundary run on 2026-06-29 produced 2 retry decisions, reported a successful-after-retry rate of 1.0, retry-exhaustion rate of 0.0, 1 credential-action avoided-call estimate, and attached the same telemetry to `out/live_retry_health_scorecard_success_20260629.json` with no scorecard warnings.
- New control-plane interconnection gates cover pipeline preflight and retry telemetry through `scripts/ci/check_coverage.py`, `scripts/ci/run_mutation_gate.py`, and focused tests. Verification on 2026-06-29 showed `src/control-plane` coverage at 94.05% against the new 85% gate, targeted control-plane mutation at 12/12 killed across preflight and retry telemetry, focused control-plane tests at 31 passed, and the full non-integration suite at 3320 passed.
- Workflow-aware control-plane contracts are live through `src/contracts/workflow_control.py`, `src/orchestrators/workflow_control_orchestrator.py`, and `config_service.load_workflow_control_settings(...)`. YAML under `workflow_control` now defines preflight profiles for report generation, publisher inventory, report download, cross-report analysis, publishing, UI replay, WordPress sync, and browser acquisition; a report-generation DAG/state-machine; workflow/step retry policies; operational-memory controls; and adaptive concurrency bounds for model, PDF, browser, Drive, and WordPress work. `run_report_pipeline(..., auto_resume_from_latest_safe=True)` automatically selects `latest_safe` when no explicit resume stage is supplied, and workflow-control retry resolution logs the policy ID/version. Live verification on 2026-07-04 ran all eight workflow-aware preflight profiles with live endpoint probes enabled, passing 58 checks with 0 blockers and 0 warnings; loaded operational memory from 200 real report-source observations plus retry telemetry; selected adaptive concurrency decisions for all five resource classes; preserved a terminal Capgemini checkpoint validation error without redoing model work in 0.317s; and resumed an existing processed IAS report through automatic `latest_safe` selection in 0.058s versus the earlier 582.003s fresh IAS generation evidence.
- Control-plane interconnection gates now include workflow control. Verification on 2026-07-04 showed `src/control-plane` coverage at 95.66%, mutation at 18/18 killed across preflight, retry telemetry, and workflow control, focused workflow-control/report-pipeline tests passing, and the full default suite at 3402 passed / 25 deselected.
- Workflow-control default-path wiring now includes typed preflight remediation artifacts, `RunIntent` resolution, publish confidence-gate decisions, persisted workflow-control observations in the state database, model-call audit/replay bundle contracts, deterministic pre-LLM quality gates, adaptive concurrency resolution for model/PDF/browser/Drive/WordPress resources, CLI ingest/publish workflow-control resolution plus feedback writes, and UI background-run workflow-control payload enrichment. Focused verification on 2026-07-04 covered workflow-control, state-service migration/persistence, direct and wrapped LLM audit logging/replay, UI launch wiring, and CLI ingest/publish wiring at 76 passed. Live verification resolved `publish ready reports` to `publishing`, passed publish preflight with 0 blockers, ran a real `gpt-5-mini` JSON call with provider request ID and 111 tokens, confirmed `llm_model_call_audit` logging, completed `python -m src.cli publish-wp --limit 0` in 10.623s with 0 posts published, persisted a `publishing/wordpress_publish` feedback observation, selected adaptive concurrency for all five resource classes, and resolved the real UI `ui_run_replay` payload to `ui_replay`.
- Explicit report-generation client bundles, typed checkpoint artifact registries, and UI-run failure classifications are live. `run_report_pipeline` now passes `ReportGenerationClientBundle` instead of reflecting report-function signatures, checkpoints persist typed artifact refs with hashes and required/optional semantics, resume validates registry entries while preserving legacy checkpoint compatibility, and UI poll/dead-letter paths expose recommended next actions. Verification on 2026-06-29 covered focused red/green tests, contract round trips for 1,368 dataclasses, full default pytest with coverage at 3,345 passed / 25 deselected, coverage gate at 83.59% global and 95.55% control-plane, mutation gate with `report_pipeline_orchestrator.py` at 3/3 killed, and quality non-regression. Live existing-PDF runs with real model/API calls wrote registries for source/selection/analysis/render checkpoints and validated `latest_safe` resume in 0.144s after a 523.947s fresh run and 0.082s after a 501.629s fresh run; live UI worker failure classification persisted an `auto_triaged` dead-letter action with `mark_permanent` recommendation for an invalid report-download payload.
- Mailbox-backed gated-report acquisition is live through `src/contracts/mailbox_acquisition.py`, `src/services/mailbox_acquisition_service.py`, `src/generators/mail_report_acquisition_generator.py`, `src/orchestrators/mail_report_acquisition_orchestrator.py`, `config_service.load_mailbox_acquisition_settings(...)`, and `python -m src.cli poll-mail-report`. The local mailbox provider is IMAP, credentials resolve from `.env`, delayed delivery exits as retryable `mail_report_not_arrived_yet`, and selected mail links re-enter the existing report-download workflow instead of creating a second downloader. Live verification on 2026-07-04 confirmed the original Gmail-configured path failed with insufficient OAuth scopes, the corrected IMAP path searched the mailbox directly, a zero-timeout delayed-mail run returned retryable `mail_report_not_arrived_yet` after one real poll, and a temp-database route canary covered direct PDF, HTTP PDF, report-page PDF-link, onsite, tracker, email-form, and listing-hub acquisition families with 5 of 7 acquired artifacts and 2 of 7 correctly classified as email-required without browser spend. A database-derived 10-publisher email-route matrix on 2026-07-04 produced 4 verified downloads, 4 `blocked_unknown_required_enum` outcomes, 1 `blocked_captcha`, and 1 stale-process email confirmation that required rerun; a fresh BigCommerce rerun with the IMAP mailbox completed `email_requested` plus mailbox download on the first poll, producing a 3,068,372-byte verified PDF. Live verification on 2026-07-05 added per-run mailbox poll bounds, confirmed cross-publisher mailbox-link rejection on a GWI rerun that ignored BigCommerce and SensorTower deliveries, prevented unconfirmed `email_required` outcomes from creating mailbox requests, tolerated Drive preflight cleanup failures after write access was proven, and completed a second BigCommerce mailbox acquisition on the first poll with a 9,341,114-byte PDF plus Drive upload. A second 20-run publisher set on 2026-07-05/2026-07-06 produced 11 direct PDF downloads, 1 onsite capture, and 7 correctly gated `email_required` outcomes; one initial browser-timeout failure was rerun successfully as `email_required`, and no publisher exceeded three mail-delivered reports.
- Event-driven mailbox delivery requests are live through the report-download workflow, state schema version 7, workflow-control observations, delivery-intent matching, mailbox preflight, attachment/ZIP-PDF materialization, incremental seen-message tracking, and typed browser identity consent policy in `src/config/browser_download_identity.yaml`. Focused verification covered durable request idempotency, attachment-first acquisition without browser follow-up, ZIP PDF materialization, mailbox preflight before email-form submission, consent-policy config loading, and CLI option wiring.
- LLM OpenRouter failover, public metadata governance, executive artifact enrichment, metric-spine editorial propagation, workflow-control mailbox dispatch, mailbox candidate suppression, route-memory promotion, capability maps, and autonomous smoke coverage are live. Verification on 2026-07-08 covered 1,620 affected contract/orchestrator/generator/service tests, prompt dry-run validation, contract schema snapshots, formatting, `docs/quality/capability_maps.json`, a fresh autonomous mailbox happy-path smoke with 1 due request processed / 1 succeeded / route memory promoted, an idempotent replay with 0 duplicate requests processed and route memory retained, a live OpenRouter fallback JSON call with provider decision `openrouter_fallback` and 161 total tokens, and a retained real-artifact advisory smoke over 2 existing report-analysis roots with no invented metrics.
- Prompt/resume/acquisition speed work on 2026-07-08 is live: prompt partials and schema snippets, scored insight fields, critique-first severity-aware regeneration, latest-safe ingest resume, fast-first vector-store polling, parallel table/chart ranking, md5 vector-store reuse, Drive/cache prefetch before report workers, artifact-level acquisition cache, route-family browser prompts, and deterministic pre-LLM form autofill. Verification covered focused regression tests, prompt fixture-corpus regression, Ruff on changed Python, artifact-cache/pre-LLM/prefetch tests, and a live existing IAS checkpoint resume returning `processed` in 0.005s with zero model/API calls.
- A 20-publisher live acquisition run on 2026-07-06 used `reports@marketbearing.eu` for delivery, verified ad hoc publisher Drive folder creation, blocked public-search drift after exact execution URLs, preferred complete on-site report captures over optional enum blockers, and tightened mailbox candidate selection so SATISFYD, Mimecast, and Sprinklr rejected unrelated Contentsquare delivery links with `candidate_count=0` while a Contentsquare-owned mailbox delivery still produced 12 eligible publisher-affine candidates.
- The LLM boundary now records primary/fallback provider decisions and supports deterministic over-budget context compaction for JSON chat request contracts, retaining metric/quote/claim/citation/evidence/validation anchors and logging avoided input tokens/cost. `budget_decision="not_configured"` remains in the wrapper; dynamic budget-aware model routing and live spend policy remain open.
- Public report rendering now exposes `executive_advisory`, strongest `metric_spine` entries, readable claim-support labels, and `so_what`/`now_what` without leaking canonical claim IDs or raw evidence IDs; rendered HTML carries `editorial_contract_version=public-report-editorial-v1`, and publish-time editorial checks emit stable rule IDs/remediation for generic phrasing and internal-reference leakage before WordPress side effects. Crop output now includes typed per-candidate outcomes keyed by candidate ID, `publication_strict` is the canonical user-facing crop path for selected/fallback/candidate-pack crops, and accepted figure assets carry crop QA score, defects, sidecar path, quality profile, and rejection reason. `CROP_REGION_ARTIFACT_VERSION=1.1` makes strict-crop cache acceptance depend on an accepted QA sidecar, returning rejected cache entries as typed outcomes with no publishable path and regenerating missing/invalid diagnostics; existing report-card updates now retain `ml_public_intelligence=1` whenever the retained body still contains the public intelligence panel, while ineligible bodies remain `0`. Live verification on 2026-07-11 reran 3 retained Algolia candidates twice: 2 accepted crops had stable paths, 1 `chart_axis_or_label_clipped` crop stayed rejected with an empty path on both runs.
- `src/orchestrators/publish_queue_orchestrator.py` still builds a read-only publish snapshot. It does not enqueue durable publish jobs or a transactional outbox.
- Claim-level embedding persistence is live: `claim_embeddings` stores durable vectors/provider metadata/status/error taxonomy linked to `report_claims.claim_uid` and `vector_projection_queue.entity_uid`, and `claim_embedding_orchestrator` owns pending/stale embedding workflow execution.
- Cross-report Briefing and grounded Signal publish paths now reuse persisted claim embeddings for bounded semantic evidence preselection through `analytics_store_service.read_claim_embeddings`, while falling back to deterministic lexical/category ordering when embeddings are absent or stale. Durable Signal candidate extraction, ingestion-time Signal artifact-pack generation, separate Signal-store persistence, grouping, readback, and publish reuse are landed through `src/contracts/signal_candidates.py`, `src/generators/signal_candidate_generator.py`, `src/generators/report_signal_artifact_generator.py`, `src/orchestrators/signal_candidate_orchestrator.py`, `src/orchestrators/report_generation_orchestrator.py`, and `src/services/analytics_store_service.py`.
- The bundled WordPress plugin registers `ml_report`, `ml_signal`, and `ml_briefing` with REST enabled. Live hosted WordPress REST exposure for `ml_briefing` and `ml_signal` was verified on 2026-06-28 with `Wordpress/scripts/verify-publish-entity-rest.py` using existing generated Briefing and Signal artifacts; readback confirmed draft post IDs 1728 and 1729, post type, slug, title, route template, status, and metadata.
- Report post-type drift is closed: README and README_WORDPRESS document canonical report publishing to `ml_report`, `src/config/app.yaml` and `src/config/app.example.yaml` default `publish.wp.post_type` to `ml_report`, the plugin registers `ml_report` with REST base `ml_report`, and legacy core `post` report/digest compatibility is documented as migration-only behavior. Live hosted WordPress verification on 2026-06-28 published an existing generated report artifact (`out/activate-2025-ecommerce-pdf.html`) as draft `ml_report` post ID 1739 and read it back from `/wp-json/wp/v2/ml_report/1739` with type `ml_report`, slug `live-report-post-type-verification-20260628`, status `draft`, and `/reports/%pagename%/` permalink template.
- Native WordPress categories are now the canonical public Topic surface with governed topic semantics. `WordPressTaxonomyTerm` carries description, definition, inclusion rules, exclusion rules, and semantics version; publish/category generators and publish preflight write those fields through the WordPress taxonomy service; the service performs authenticated REST readback and fails with `wp_taxonomy_semantics_readback_mismatch` when semantic meta is missing; the bundled plugin registers `ml_topic_definition`, `ml_topic_include_when`, `ml_topic_exclude_when`, and `ml_topic_schema_version` term meta for category REST exposure; and the topic directory/category archive templates render approved term semantics. Live hosted WordPress verification on 2026-06-30 wrote/read back the existing `digital_payments` Topic as category term ID 116 with description plus all four `ml_topic_*` meta keys.
- Live WordPress entity REST verification is now a staging release gate. `Wordpress/scripts/verify-publish-entity-rest.py` verifies `ml_report`, `ml_briefing`, and `ml_signal` publish/readback from existing generated artifacts, `scripts/ci/check_wordpress_staging_rest_gate.py` runs the verifier when staging WordPress env vars are enabled, CI archives sanitized JSON evidence, and README documents required env vars, artifact paths, and draft cleanup by slug prefix. Live hosted WordPress verification on 2026-06-30 created/read back draft IDs 1746 (`ml_report`), 1747 (`ml_briefing`), and 1748 (`ml_signal`) with route templates, status, and metadata readback intact.
- Canonical Topic semantics now feed category-fit validation and persisted evidence-routing audit fields. Category-fit candidates record semantic rule status, supporting/rejecting rules, and typed remediation signals; selected weak assignments are flagged as `topic_semantics_ambiguous`, exclusion conflicts are rejected, and context-category-fit payloads persist the semantic audit. Live existing-artifact verification on 2026-07-02 used the Julius Baer report analysis artifacts with a real OpenAI call and surfaced the selected Macroeconomics assignment as ambiguous instead of silently treating a weak semantic fit as fully validated.
- Registry-backed report-card publication-date remediation is live through typed repair contracts, generator-owned normalization, UI failure classification for `card_publication_date_invalid`, and render-time fail-closed date sourcing. Repairs read artifact registry refs for `doc_map`, `artifacts`, `validation`, and `rendered_html`; source-supported dates or audited operator overrides are accepted, while absent registry evidence fails closed. Live existing-checkpoint verification on 2026-07-02 reached `report_card_publication_date_absent` without rerunning upstream model work, proving missing dates are no longer invented from filesystem modified times.
- Public-site SEO, social metadata, and hosted performance baseline gates are live through `marketlense-core` 1.6.9 metadata rendering, `scripts/quality/public_site_seo_performance.py`, `scripts/ci/check_public_site_seo_performance.py`, `config/public_site_baselines.yaml`, and README release instructions. Live hosted verification on 2026-07-02 passed across homepage, reports, briefings, signals, methodology, contact, and submit pages with no missing metadata and no baseline violations; representative measured maxima were 4.300s response start, 15.972s DOM complete, 28 discovered requests, and 1,602,978 bytes page weight.
- WordPress design token drift remains: README documents `settings.layout.wideSize` as `82rem`, while `Wordpress/wp-content/themes/marketlense/theme.json` currently uses `84rem`.
- Live visual QA on 2026-06-30 against `http://marketlense.medianewsonline.com/` found public-site launch blockers and premium-quality gaps: HTTPS failed for the tested hostname, `/publisher/not-extracted/` returned a fatal WordPress error with a PHP stack trace and server paths, "Not extracted" appeared as a public publisher, contact/submission CTAs looped without an intake form, mobile search results had horizontal overflow, and generated/OCR artifacts leaked into public report cards and exhibit captions.

## Closed or Removed From Active Backlog

- OCR confidence gating and native-confidence-based OCR fallback controls.
- Prompt dry-run namespace validation and prompt-fixture corpus regression baseline.
- Targeted artifact regeneration for mapped validation failures, including deterministic TOC repair.
- Claim/evidence span binding and validation-level evidence normalization.
- Core publisher-discovery memory, deferred recovery, direct-detail routing, and KPI rollout controls.
- Report-store, config-service, OpenAI-service, PDF-service, browser-download, report-download, cross-report-input, and report-generation dependency facade splits.
- UI-run dead-letter workflow, replay manifests, and operator triage surfaces.
- Vector-store delete/prune lifecycle and retention orchestration.
- Durable Signal candidate extraction, clustering, storage, readback, and publish reuse.
- Ingestion-time grounded Signal artifacts, separate Signal-store persistence, and publish workflow reuse from the Signal base.
- Claim-level embedding persistence beyond `vector_projection_queue`, including durable vector records, provider/model metadata, status/error taxonomy, idempotent/stale-aware workflow execution, and local claim/report/topic readback.
- Briefing and Signal evidence preselection using persisted claim embeddings, including bounded semantic claim selection, stale/no-embedding fallback, structured selection summaries, idempotency material updates, and local live-corpus prompt-size verification.
- Live WordPress REST exposure and draft readback for Report, Briefing, and Signal publish entities on the hosted site.
- Report post-type and entity naming drift between README, config, WordPress plugin behavior, and public copy.
- Bounded Streamlit log reads and grouped directory-count walks through `file_service`.
- Measured PDF table/visual candidate hot-path optimization behind the canonical `pdf_service` boundary, including lazy indexed visual overlap checks and live existing-PDF equivalence/timing evidence.
- PDF candidate extraction performance/equivalence regression gate, including committed dense-PDF baseline signatures, CI/release wrapper, live existing-PDF verification, and README refresh instructions.
- PDF crop/refine artifact equivalence and cost benchmark gate, including existing generated artifact hashes, cached crop-refine decision signatures, estimated two-phase page model-call counts, CI/release wrapper, live existing-artifact verification, and README refresh instructions.
- PDF benchmark trend reporting across candidate and crop-refine gates, including bounded local history, sustained runtime/model-call regression detection, CI/release wrapper, live existing-output verification, and README retained-history guidance.
- PDF benchmark trend evidence in release and health scorecards, including retained candidate/crop-refine/trend JSON inputs, incomplete-evidence failure reporting, live scorecard verification, and README operator flow.
- Release evidence bundle manifest for retained quality-gate artifacts, including commit/command/path/schema/timestamp/hash/status recording, missing/invalid/schema-drift failure reporting, live retained-artifact verification, and README archive flow.
- Release evidence manifest CI archival and freshness gates, including `HEAD` commit checks, artifact modified-time checks, CI health scorecard generation, `release-evidence-bundle` upload, live freshness verification, and README local-vs-CI retention flow.
- Release evidence review summaries and waiver governance, including deterministic Markdown/JSON review outputs, owner/expiry/justification waiver validation, CI approval gating, live clean/stale/waived manifest verification, and README operator review and waiver-retirement flow.
- Remaining direct file-I/O leaks outside services and the expanded I/O boundary gate, including generator/orchestrator/utility/CLI/UI AST coverage, service-backed CLI/UI/orchestrator file probes, `FileStatResponse` path-kind metadata, contract schema refresh, focused regression coverage, and live report-download verification.
- Full report-generation restart support for every persisted semantic checkpoint, including artifact-integrity validation, vector indexing state persistence at `selection_complete`, `source_prepared`/`selection_complete`/`analysis_complete`/`render_complete`/`latest_safe` runtime resume support, typed non-retryable failures for invalid checkpoint/artifact paths, focused regression coverage, and live IAS existing-PDF verification.
- Automatic preflight and credential remediation before expensive pipeline work, including typed preflight reports, Drive OAuth refresh remediation, WordPress publish-target readiness, prompt namespace validation, report-pipeline blocking before model-client construction, focused regression coverage, raised control-plane coverage/mutation gates, and live project-config verification.
- Retry-decision telemetry and policy tuning reports, including deterministic grouped telemetry, scorecard attachment, retry-exhaustion threshold warnings, focused regression coverage, targeted mutation coverage, and live structured retry-boundary verification.
- Raised mutation and coverage gates for new control-plane interconnection logic, including an 85% `src/control-plane` coverage slice and targeted mutation entries for preflight and retry telemetry.
- Generic "add more CI" wording. Active CI work must target specific drift that current gates do not catch.
- Empty audit sections from earlier consolidated TODO versions.

## Near-Term Launch Plan

### Phase 1: Highest-Leverage Controls

- Add pipeline planning and preflight so the system can choose safe next actions with less user direction.
- Real-time spend guardrails at run/day/publisher scopes with explicit override flow.
- Budget-aware model routing with deterministic compaction.
- Durable publish snapshot decision: real jobs/outbox or explicit readiness-snapshot naming.

### Phase 2: Intelligence Reuse and Public Entity Alignment

- Semantic evidence preselection benchmark and tuning.
- WordPress render-time intelligence synthesis replacement with approved projections.
- Public rendering adoption for executive advisory and metric-spine payloads, insight scoring, and editorial contract versioning.
- Public-site launch trust hardening, intake flows, and premium presentation QA.

### Phase 3: Resilience and Performance

- Normalize retry/defer decisions, add UI-run failure classification, and add typed artifact registry validation.
- Release evidence review summaries and waiver governance.
- Contract compatibility matrix.
- Role-mixing/monolith-growth CI enforcement.
- End-to-end trace read model.
- Browser route-budget telemetry auto-tuning and warm same-publisher worker-pool rollout, using route-family budget logs, terminal evidence, and session-reuse ledgers to reduce batch browser wall time without cross-publisher leakage.
- Generate local and CI quality-gate manifests from `docs/quality/architecture_policy.yaml`, with drift tests for workflow commands, artifacts, and waiver metadata.
- Split the three expiring long-test allowlist modules before 2026-08-31 while preserving public pytest facades and current assertions.

---

## Merged Simplification Backlog Context

The active simplification tasks are listed in section 8 above. The retained rules, audit evidence, and historical launch notes below provide supporting context only.

### Migration Source

Migrated from `simplification.md`.

### Original Simplification Backlog Context

Last audited: 2026-06-15

This file captures the top simplification, decomplexification, reuse, and removal opportunities found in the current repository state. It intentionally mirrors the concise backlog style of `CONSOLIDATED_TODO.md`: ordered by leverage, measurable before implementation, and constrained by the architectural rules in `AGENTS.md`.

This is an analysis backlog, not an implementation approval. Before any item starts, the owner must confirm current behavior, define a baseline metric or regression fixture, and choose a movement-only or behavior-changing path explicitly.

### Backlog Rules

- Treat this file as a simplification intake list, not a second product backlog.
- Promote items into `CONSOLIDATED_TODO.md` only when they become active implementation work.
- Remove or close an item when current code proves it is already resolved.
- Merge overlapping simplification work into one scoped change instead of creating parallel refactors.
- Before implementation starts, every prioritized item must have an owner, baseline metric, target metric, affected tests, and review/expiry date.
- Keep changes compliant with `AGENTS.md`: no placeholder logic, no role mixing, no prompt text in code, no private-helper monkeypatching, and no new deployable boundary without architecture review.
- For movement-only refactors, preserve public imports through the existing facade unless an explicit public migration is approved.

Scoring:

- `Impact`: `1` low leverage, `5` highest leverage across reliability, quality, cost, speed, or architecture.
- `Effort`: `1` localized change, `5` broad refactor/migration with cross-module coordination.

### Current-State Evidence

- `llm_service.py` is the sole OpenAI, OpenRouter, generic LLM-policy, and vector-store provider boundary; the legacy `openai_service.py` facade has been removed.
- Model-client construction is centralized at orchestrator/service-factory boundaries and injected into model-backed generators.
- Large orchestrators, publish workflow surfaces, PDF facade exports, and WordPress render-time intelligence remain broad behavior-preserving refactors.
- Cross-report contract shared vocabulary now belongs to the `_cross_report_analysis` package owner, and `src/contracts/cross_report_analysis.py` remains the documented public contract surface.

### Priority Order

1. Canonical service-boundary simplification.
2. Generator and orchestrator role-boundary cleanup.
3. Low-risk helper reuse and duplicate removal.
4. PDF/visual heuristics compatibility-surface reduction.
5. WordPress and CI/process simplification.

### 2026-06-14 Verification Evidence

- Full functional suite: `3113 passed, 23 deselected`.
- Coverage: 83.11% global, 84.85% orchestrators, 87.27% generators, and 82.41% services.
- Mutation gate passed; the changed LLM vector-store target killed its sampled mutant.
- Architecture imports, service-boundary mapping, refactor movement evidence, forbidden patching, formatting, typing, and split-symbol gates passed.
- First-party test and script files contain no modules over 1,000 lines.
- Live OpenAI strict-JSON and OCR calls succeeded through `llm_service`; the OCR run used an existing project PDF and returned provider request metadata.
- A live persisted vector-store status call succeeded through `llm_service`.
- A live OpenRouter completion succeeded through `llm_service`, and the affected browser-download route completed with a structured `email_required` outcome after using the route's normal execution budget.
- After removing the legacy facade, fresh live OpenAI strict-JSON, existing-PDF OCR, persisted vector-store status, OpenRouter completion, and Consumer Edge browser-download checks all succeeded through `llm_service`.
- Existing HTML cache loaded through the typed cache service; template-bundle hashing was deterministic.
- Existing 18,900,061-byte generated image was prepared as a 298,814-byte upload payload, a 98.4% reduction.
- Real PDF candidate extraction processed an existing 1,159,172-byte PDF, produced three candidates with zero degraded pages, and produced byte-identical JSON on consecutive warm runs.
- WordPress provisioning ran successfully against the configured site; canonical and compatibility CLI dry runs then passed after argument-forwarding and import-path regressions were fixed.
- Investigation-only items were closed with retained-path evidence in `docs/quality/simplification-audit-2026-06-14.md`.
- The quality-regression gate's code coverage, mutation, and candidate metrics passed. Its unrelated docpack schema check remains red because existing golden artifacts predate required `cover_semantics` and `card_tldr_compact` fields; those fixtures and schemas were not changed or synthesized.

### 2026-06-15 Retry-Ownership Verification Evidence

- LLM services now perform exactly one provider attempt; OpenAI and OpenRouter SDK retries are explicitly disabled with `max_retries=0`.
- Orchestrators are the sole retry/backoff owner. Focused tests prove a retryable service error propagates after one call and an orchestrator performs the bounded second attempt.
- Nonzero `ingest.llm` retry, delay, backoff, or jitter settings fail configuration loading with typed `llm_service_retry_config_forbidden`.
- Known GPT-5 Responses API parameter incompatibilities are omitted before the first request; unknown unsupported parameters fail once as typed non-retryable bad requests.
- Full functional suite: `3113 passed, 23 deselected`; coverage passed at 83.13% global, 84.85% orchestrators, 87.27% generators, and 82.45% services.
- Mutation, formatting, typing, architecture imports, forbidden patching, repository hygiene, contract schema, and prompt fixture regression gates passed.
- Fresh live calls passed for OpenAI strict JSON, OCR on the existing Bain PDF, persisted vector-store status, vector-backed GPT-5 response, and OpenRouter completion.
- The Consumer Edge browser-download feature completed through the real OpenRouter/browser path as `email_delivery / email_required` with typed `blocked_unknown_required_enum`; its OpenRouter construction log recorded `max_retries=0`.
- The pre-existing quality-regression comparator remains red because its February baseline still names removed `openai_service.py` and committed golden artifact fixtures predate required `cover_semantics` and `card_tldr_compact` fields. No fixtures were synthesized or changed.

---

### 2026-06-16 Model-Client Boundary Verification Evidence

- Generators no longer import `llm_service` provider-policy construction helpers; `tests/test_model_client_injection_boundaries.py` enforces the boundary.
- Orchestrators and service-factory paths now build scoped model clients for report generation, report pipeline execution, cross-report synthesis, recategorization, publisher inventory screening, OCR fallback, and figure captions, then inject those clients into generators.
- Focused regression suite passed: `237 passed`.
- Live verification used existing project PDFs and golden report-analysis artifacts: full report generation produced HTML, OCR fallback produced a one-page OCR PDF, and cross-report synthesis produced a validated artifact with 8 sections.

---

### Near-Term Launch Plan

### Phase 1: Boundary Corrections

- Audit top-level service proliferation and demote internal capabilities.

### Phase 2: Larger Workflow Simplification

- Consolidate publish orchestration surfaces.
- Reduce PDF visual heuristics compatibility exports.
- Simplify WordPress shortcode surfaces.

### Closed or Removed From Simplification Intake

- Implemented items are removed from this file after verification and closure in the consolidated backlog.
- Centralized model-client construction outside generators by moving scoped client construction to orchestrators/service-factory boundaries, adding a generator-boundary test, and verifying with focused tests plus live report-generation, OCR, and cross-report runs.
- Reduced cross-report contract fragmentation by deleting the private one-off `src/contracts/_cross_report_analysis/common.py` owner, moving shared vocabulary into `src/contracts/_cross_report_analysis/__init__.py`, preserving the public `src/contracts/cross_report_analysis.py` facade, and verifying with contract tests, schema/architecture gates, mutation gate, full regression suite, and a live model-backed cross-report generation run.
- Clarified report pipeline entrypoints by documenting the canonical batch, single-file, report-pipeline, report-generation, report-analysis, and `analysis_complete` restart entrypoints; removing the redundant ingest-level `report_generation_orchestrator` injection; and adding ownership tests for routing, direct stage invocation, and documentation. Verification used focused orchestrator tests plus a live existing-PDF report pipeline run and semantic restart canary.

## Migrated x100 Intake Archive

Migrated on 2026-07-11 from `x100tasks.md`. These are intake proposals, not implementation approval. The active priorities and decision register above take precedence; each proposal requires revalidation, a measured baseline, and explicit promotion before work begins.

### 1. Public Trust and Output Sharpness

- **Title:** Add retained-artifact strategic insight and editorial quality benchmarks [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Strategic insight fields are generated, but retained real artifacts do not yet benchmark role diversity, duplicated insight overlap, `so_what`/`now_what` quality, metric calibration, evidence linkage, caveats, and generic phrasing.
  - Why implement: The system needs output-quality regression evidence over real generated artifacts, not only prompt renderability and schema validity.
  - Tradeoffs / risks: Benchmarks must avoid brittle text snapshots and use semantic, contract-grounded assertions.
  - Acceptance Criteria:
    - A retained-artifact benchmark reports insight diversity, coverage-role balance, duplicate-overlap warnings, evidence-link completeness, metric support, caveat quality, and banned/generic phrasing.
    - The benchmark emits JSON/Markdown evidence suitable for release review.
    - Failures include artifact ID, field path, rule ID, and suggested remediation.

- **Title:** Expose readable public evidence spans for high-impact claims [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Internal evidence IDs are auditable but not useful to public readers.
  - Why implement: Claims feel verifiable when users can expand source excerpts, source/page labels, and limitations.
  - Tradeoffs / risks: Public citations must redact internal paths, avoid leaking raw artifact IDs, and respect source context.
  - Acceptance Criteria:
    - Claims, metrics, quotes, recommendations, and risks render readable evidence labels and source/page context.
    - Internal evidence IDs remain available for audit but are not the public presentation layer.
    - Public rendering tests prove no raw IDs, paths, or extraction fragments leak.

- **Title:** Upgrade report cards and exhibit titles to premium editorial copy [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Cards and visual labels can look automated through weak TLDRs, raw fragments, repeated summaries, or generic figure names.
  - Why implement: Cards and exhibits are the primary discovery and credibility surfaces.
  - Tradeoffs / risks: Card copy must be concise and source-backed without duplicating full summaries.
  - Acceptance Criteria:
    - Report cards include concise analyst-grade summaries, key takeaways, valid covers, and clean metadata.
    - Figure assets include human-readable exhibit title, why-this-matters, source context, public confidence, ranking rationale, metric callouts, linked claims, and proof statements when available.
    - Tests reject raw extraction prefixes, OCR fragments, `F1`, `Additional figure`, duplicate boilerplate, placeholders, generic figure labels, and internal-looking identifiers.

- **Title:** Add a source-quality and methodology trust panel [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Users cannot easily see how a page was generated, validated, constrained, or why a source is high/medium/low value.
  - Why implement: Transparent methodology and source-quality rationale make generated intelligence more defensible.
  - Tradeoffs / risks: The panel must not expose secrets, internal paths, raw logs, or unstable implementation details.
  - Acceptance Criteria:
    - Report pages can render extraction method, OCR use, validation state, abstentions, warnings, limitations, and source-quality component rationales.
    - Missing diagnostics render neutral UI or admin diagnostics, not fabricated quality claims.
    - Tests cover redaction, missing-data handling, and public copy constraints.

- **Title:** Build related intelligence navigation from approved projections [Impact: 4/5, Effort: 4/5]
  - Problem fixed: Report pages can feel isolated from Signals, Briefings, Topics, Publishers, Figures, Regions, Time Periods, and related reports.
  - Why implement: The public site should behave like an intelligence portal, not a flat WordPress list.
  - Tradeoffs / risks: WordPress must render approved projections and must not synthesize intelligence from runtime post counts or taxonomy queries.
  - Acceptance Criteria:
    - Related Reports, Briefings, Signals, Topics, Publishers, Figures, Regions, and Time Periods are derived from validated artifacts and metadata projections.
    - Missing projections fail closed with neutral UI or admin diagnostics.
    - Tests prove no strategic claim is generated solely from WordPress runtime queries.

- **Title:** Stop WordPress runtime synthesis of intelligence claims [Impact: 5/5, Effort: 4/5]
  - Problem fixed: WordPress runtime code can still derive weekly signals, strategic themes, freshness-style movement, and publisher authority from post counts, taxonomy counts, and dates.
  - Why implement: Analytical claims must come from approved Python projections and artifacts so they remain reproducible and evidence-governed.
  - Tradeoffs / risks: Missing projections need neutral UI/admin diagnostics so public pages do not look broken or fabricate intelligence.
  - Acceptance Criteria:
    - Homepage, signal, briefing, archive, and publisher intelligence modules read approved projection data only.
    - Runtime post/taxonomy counts may support navigation counts but not strategic or authority claims.
    - Tests prove missing projections fail closed and no intelligence claim is generated solely from WordPress runtime queries.

- **Title:** Add deterministic related Reports and Briefings blocks [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Public report pages do not yet have complete deterministic related-Briefings and related-Reports blocks as defined in the user-facing guide.
  - Why implement: Related-content modules turn isolated reports into a research portal and use the entity model already present for Reports, Signals, Briefings, Topics, Publishers, and Figures.
  - Tradeoffs / risks: Relationships must come from approved projections and validated artifacts, not runtime WordPress inference.
  - Acceptance Criteria:
    - Report pages render related Reports and Briefings when approved relationships are recoverable.
    - Relationship payloads include rationale/source metadata safe for public display.
    - Missing relationships render no filler and no synthetic recommendation.

- **Title:** Harden archive/search facets, mobile workflows, CTAs, and public performance [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Search, archive, intake, and mobile/performance issues can make the public product feel unfinished even when report content is strong.
  - Why implement: Discovery and intake workflows are part of output quality.
  - Tradeoffs / risks: Frontend changes need screenshot coverage and must preserve canonical URLs/social metadata.
  - Acceptance Criteria:
    - Archives support validated facets such as report type, key-figure availability, visual evidence count, source-quality band, methodology availability, validation status, and signal support.
    - Briefing, correction, and report/source submission CTAs resolve to real intake flows with validation and confirmation states.
    - Mobile/tablet/desktop smoke screenshots cover homepage, search, archive, report detail, contact, and submit pages with no overflow or clipped controls.
    - Performance gates track response start, DOM complete, request count, page weight, canonical URLs, Open Graph, and Twitter metadata.

- **Title:** Harden hosted public-site trust surface [Impact: 5/5, Effort: 3/5]
  - Problem fixed: The root audit still lists HTTPS, sitemap canonicalization, safe 404/500 behavior, stack-trace/path leakage, branded failure pages, hosted latency, and legacy polluted content verification as open product-trust gaps.
  - Why implement: Public trust fails if generated content is strong but the hosted site exposes infrastructure errors, unsafe failure pages, or stale polluted projections.
  - Tradeoffs / risks: Hosted fixes must preserve canonical URLs, metadata, and deployment rollback safety.
  - Acceptance Criteria:
    - Hosted smoke checks cover HTTPS, canonical sitemap URLs, branded 404/500 pages, no PHP/server path leakage, representative public pages, metadata/social tags, request count, page weight, response-start, and DOM-complete targets.
    - Legacy polluted publisher/card/exhibit records have a re-projection or verification path.
    - Failures withhold publish or produce explicit remediation evidence.

---

### 2. Visual Evidence and Crop Acceptance Quality

- **Title:** Add bounded multimodal final-crop QA escalation outside the PDF service [Impact: 4/5, Effort: 4/5]
  - Problem fixed: Low-confidence `.qa.json` sidecars are not escalated to a canonical multimodal boundary for accept/repair/reject decisions.
  - Why implement: Deterministic QA should handle clear cases, while ambiguous final crops can be checked by a bounded model-backed generator/orchestrator path without putting model calls inside the PDF service.
  - Tradeoffs / risks: Escalation must be optional by profile, budgeted, logged, and routed through services/generators/orchestrators according to role boundaries.
  - Acceptance Criteria:
    - Low-confidence or borderline strict-crop sidecars can trigger bounded multimodal QA through the canonical model service boundary.
    - The model returns accept, repair, or reject with defect labels and evidence-backed rationale.
    - Orchestrator policy controls budget, retry, and fallback behavior; PDF service remains free of model calls.

- **Title:** Expand crop benchmarks from candidate signatures to rendered visual metrics [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Existing crop/candidate benchmarks can pass while rendered public crop quality regresses.
  - Why implement: The crop-quality standard is the final PNG and HTML presentation, not only candidate count, bbox signature, or runtime.
  - Tradeoffs / risks: Golden fixtures must be curated and stable enough for CI/release evidence without overfitting one rendering algorithm.
  - Acceptance Criteria:
    - A curated golden crop corpus covers difficult real reports, dense tables, dark slides, colored cards, multi-panel pages, small footnotes, and nearby decorative images.
    - Benchmarks report golden bbox IoU, perceptual image diff, whitespace percentage, clipped text count, contamination count, OCR completeness ratio, and minimum readable text height.
    - Release evidence includes benchmark deltas and retained HTML visual smoke screenshots for representative reports.

- **Title:** Add publisher/style crop profiles and HTML visual smoke tests [Impact: 4/5, Effort: 4/5]
  - Problem fixed: Recurring publisher layouts and final HTML presentation can still regress after crop selection succeeds.
  - Why implement: Publisher-specific layout memory and browser screenshots protect the actual public presentation.
  - Tradeoffs / risks: Profiles must not become brittle special cases that bypass global crop acceptance rules.
  - Acceptance Criteria:
    - Publisher/style profiles store preferred padding, title/source/note positions, card-background handling, theme behavior, and multi-panel spacing heuristics.
    - HTML smoke tests assert images are not blurry at display size, do not overflow, captions align, margins look consistent, and images are not unreadable thumbnails.
    - Profile decisions are logged and benchmarked against non-profile fallback behavior.

---

### 3. Prompt and Artifact Contract Hardening

- **Title:** Make visual ranking editorial as well as visual-quality based [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Selected charts can be visually dense but not the most useful evidence for the page.
  - Why implement: Figures should support the report thesis, standalone usefulness, executive readability, social usefulness, and summary/insight relevance.
  - Tradeoffs / risks: Editorial ranking must not bypass visual QA or select low-quality crops.
  - Acceptance Criteria:
    - `rank_candidates` includes editorial dimensions for thesis support, standalone usefulness, executive readability, differentiated data, non-duplication, social usefulness, and evidence relevance.
    - Visual-quality and editorial-quality scores are both logged and available for selection decisions.
    - Tests prove low-quality visuals cannot win solely on editorial usefulness.

- **Title:** Generate LinkedIn post variants by persona with evidence ledgers [Impact: 3/5, Effort: 3/5]
  - Problem fixed: A single social post variant limits reuse and can miss audience framing.
  - Why implement: Persona variants make report output more useful for promotion while preserving evidence discipline.
  - Tradeoffs / risks: Social copy is high risk for unsupported claims and generic language.
  - Acceptance Criteria:
    - LinkedIn output includes executive insight, operator practical, and data-led variants with hook, body, optional bullets, hashtags, evidence ledger, and unsupported-claim risk flag.
    - Banned-pattern and claim-ledger checks apply to every variant.
    - Tests reject unsupported hooks and generic first sentences.

- **Title:** Add safe comparative positioning for cross-report synthesis [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Multi-report output needs useful comparison without unsafe metric normalization.
  - Why implement: Cross-report synthesis can compare themes, assumptions, evidence direction, methodology, and audience implications while preserving data integrity.
  - Tradeoffs / risks: Raw metric magnitudes must not be compared across publishers unless normalized by source evidence and explicitly allowed.
  - Acceptance Criteria:
    - Cross-report prompts allow comparisons on themes, assumptions, evidence direction, publisher focus, methodology differences, audience implications, and convergent/divergent claims.
    - Validators reject unsupported cross-publisher metric normalization.
    - Fixture tests cover convergence, divergence, and limitation language.

- **Title:** Build golden-output prompt evaluations [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Prompt regression currently protects renderability and costs more than qualitative output quality.
  - Why implement: Golden-output checks catch generic, unsupported, schema-weak, or low-value artifacts.
  - Tradeoffs / risks: Golden checks must be deterministic and avoid brittle wording expectations.
  - Acceptance Criteria:
    - Prompt fixtures assert no generic hooks, every metric has unit/timeframe when available, every artifact claim has evidence, summaries avoid unsupported extrapolation, captions include business implication, expert comments do not restate insights, and cross-report synthesis distinguishes convergence/divergence/limitations.
    - Golden-output failures emit clear rule IDs and affected artifact fields.
    - CI or local quality gates include bounded prompt-quality evaluation.

---

### 4. Speed and Throughput With Explicit Modes

- **Title:** Add a formal `fast_ingest` profile [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Operators lack an explicit time-to-first-report mode that preserves full editorial mode separately.
  - Why implement: Fast draft output should defer expensive non-critical stages without silently lowering default quality.
  - Tradeoffs / risks: Fast mode must be logged and visible so draft artifacts are not mistaken for full editorial output.
  - Acceptance Criteria:
    - `fast_ingest` profile explicitly disables or defers figure captions, deep validation regeneration, crop-refine LLM, signal artifacts, public-site checks, and expensive grounding where configured.
    - Fast/default/full profiles are versioned and loaded through config/workflow-control.
    - Logs expose active profile, skipped stages, deferred stages, cache hits/misses, and quality tradeoffs.

- **Title:** Lazily construct LLM/model clients by reached stage [Impact: 3/5, Effort: 2/5]
  - Problem fixed: Multiple scoped clients can be constructed before the pipeline knows which scopes are needed.
  - Why implement: Lazy construction reduces startup overhead and avoids unnecessary provider setup in skipped stages.
  - Tradeoffs / risks: Dependency injection boundaries must remain explicit and generators must not construct clients.
  - Acceptance Criteria:
    - OCR, validation, regeneration, caption, and artifact clients are constructed only when their stage is reached.
    - Logs show client construction by role/stage.
    - Tests prove skipped stages do not initialize unused model clients.

- **Title:** Model report generation as a DAG scheduler [Impact: 5/5, Effort: 5/5]
  - Problem fixed: Some independent work waits unnecessarily behind vector indexing or serial stage order.
  - Why implement: A DAG can run non-dependent source prep, vector indexing, figure selection, preview rendering, taxonomy/evidence/artifacts, and render work under safe dependencies.
  - Tradeoffs / risks: This is a control-plane refactor and must preserve domain behavior, retries, idempotency, logs, and checkpoints.
  - Acceptance Criteria:
    - Stage dependencies are explicit typed data, not implicit branch order.
    - Non-vector-dependent nodes can run while vector indexing is pending.
    - Pipeline tests prove state transitions, retry counts, checkpoint semantics, and idempotency remain unchanged or approved.

- **Title:** Add deterministic ranking and crop-refine shortcuts [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Strong candidates can still incur ranking and crop-refine model calls.
  - Why implement: Obvious-pass/obvious-reject paths reduce latency and cost while preserving full mode.
  - Tradeoffs / risks: Shortcuts must not silently degrade visual or editorial quality.
  - Acceptance Criteria:
    - Ranking LLM is bypassed when deterministic scoring yields enough strong table/chart candidates.
    - `rank_max_candidates` is adaptive by profile and escalates only when no acceptable figures are found.
    - Fast mode uses one-pass crop refinement or deterministic bbox expansion, and high-confidence candidates can skip crop-refine LLM.

- **Title:** Convert Drive prefetch from stage barrier to streaming queue [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Drive cache-prefetch exists but completes the full selected batch before report processing starts.
  - Why implement: A bounded producer/consumer queue lets report generation begin on ready PDFs while later files continue downloading and hashing.
  - Tradeoffs / risks: Queueing must preserve idempotency, backpressure, Drive/PDF/LLM concurrency limits, and retry/defer semantics.
  - Acceptance Criteria:
    - Prefetch producer lists, downloads, validates, hashes, and emits ready-file records into a bounded queue.
    - Report-generation consumers process ready files under separate I/O, PDF, and LLM concurrency caps.
    - Tests cover duplicate suppression, failed download defer, queue backpressure, and stable finalization.

- **Title:** Reuse initial native text and add worker-safe PDF context pooling [Impact: 3/5, Effort: 3/5]
  - Problem fixed: Parallel source preparation can submit `_load_text` again, and within-file parallelism disables shared PDF context rather than using safe per-worker contexts.
  - Why implement: Reusing text and managed PDF contexts reduces local CPU/I/O without changing output semantics.
  - Tradeoffs / risks: PyMuPDF handles must not be shared unsafely across threads, and OCR-changed PDFs must invalidate reused text.
  - Acceptance Criteria:
    - Source prep reuses the initial native text response/status when the analysis PDF is unchanged.
    - Per-worker PDF contexts or a bounded context pool provide deterministic cleanup and no cross-thread unsafe handle sharing.
    - Tests cover OCR invalidation, parallel source prep, and context cleanup on failure.

- **Title:** Apply adaptive concurrency decisions to live worker limits [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Workflow-control can resolve adaptive concurrency, but selected limits are not yet applied to ingest, report, evidence, artifact, or browser worker windows.
  - Why implement: Adaptive concurrency only improves throughput and stability when runtime worker pools consume its decisions.
  - Tradeoffs / risks: Limit changes should occur at safe batch/window boundaries and preserve provider/API caps.
  - Acceptance Criteria:
    - Batch boundaries feed observations into adaptive concurrency resolution.
    - Selected limits are applied to the next bounded execution window for relevant resource classes.
    - Logs show prior limit, selected limit, reason, observed pressure, and safety caps.

- **Title:** Unify rendered-page acquisition behind one PDF render cache boundary [Impact: 4/5, Effort: 4/5]
  - Problem fixed: PDF parsing caches and rendered-artifact caches remain split, and there is no single rendered-page service used by every PDF stage.
  - Why implement: A canonical render cache reduces duplicate rendering and makes cache invalidation/versioning easier to reason about.
  - Tradeoffs / risks: Existing fingerprint sidecars and page-artifact caches must be preserved or migrated without changing outputs.
  - Acceptance Criteria:
    - Rendered page acquisition is served by one service boundary keyed by PDF md5, page, DPI, render variant, parser/settings fingerprints, and artifact version.
    - Candidate extraction, previews, crop-refine pages, and final crop rendering use the same boundary where compatible.
    - Equivalence tests prove rendered outputs and cache invalidation remain correct.

- **Title:** Publish draft HTML first and enrich later [Impact: 4/5, Effort: 4/5]
  - Problem fixed: Report publication waits for every enrichment module even when a useful draft page could exist sooner.
  - Why implement: Draft-first output improves time-to-value while preserving full editorial mode.
  - Tradeoffs / risks: Draft state must be explicit and public policy must decide whether drafts are visible, private, or preview-only.
  - Acceptance Criteria:
    - Draft pages include metadata, summary, topics, key findings, and available figures.
    - Later enrichment can add captions, srcsets, signal artifacts, LinkedIn variants, performance checks, and full validation.
    - Tests cover draft state, enrichment transition, publish gating, and no silent downgrade of full mode.

---

### 5. Browser-Use Speed and Cost

- **Title:** Add a deterministic executor for normal route playbooks [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Normal route playbooks are selected and sent to prompts, but only private-API evidence has deterministic replay.
  - Why implement: Known open/click/fill/select/submit/verify steps should run before invoking the LLM for recurring browser routes.
  - Tradeoffs / risks: Drift must fall back to browser-use with evidence rather than silently failing or corrupting route memory.
  - Acceptance Criteria:
    - Playbook executor supports deterministic DOM actions with CSS/text/role selectors and confidence scoring.
    - Executor runs before browser-use for eligible playbooks and records avoided LLM/browser steps.
    - Drift evidence is persisted for playbook repair and fallback uses the normal acquisition path.

- **Title:** Add trusted-publisher private-API promotion overrides [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Global private-API promotion thresholds remain conservative even for stable publishers where fewer canary observations may be enough.
  - Why implement: Publisher-scoped thresholds shorten the learning loop while preserving global safety.
  - Tradeoffs / risks: Lower thresholds require stricter validation and must not become a broad default.
  - Acceptance Criteria:
    - Publisher-scoped threshold overrides can define lower success/source counts with owner, reason, and expiry.
    - Low-threshold promotion requires same-host, expected status, required markers, verified artifact, and fallback route preservation.
    - Promotion decisions log publisher override, validation evidence, and rollback path.

- **Title:** Add HTTP-only static DOM scan before browser preflight [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Bounded browser preflight still launches a browser for pages where static HTML/scripts/meta tags may reveal PDF candidates.
  - Why implement: Static extraction can find many report assets before any browser startup.
  - Tradeoffs / risks: Static candidates must be validated by MIME/type and file signature before acceptance.
  - Acceptance Criteria:
    - HTTP scan extracts PDF/document candidates from anchors, scripts, JSON, JSON-LD, meta tags, OpenGraph tags, canonical URLs, and embedded `.pdf` strings.
    - Candidates are validated by response status, MIME/type, file signature, and publisher/report scope.
    - Browser preflight runs only when static extraction is inconclusive.

- **Title:** Narrow browser preflight eligibility and reuse state on escalation [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Browser preflight still runs for low-yield route families and still stops its browser before full-agent escalation, causing double launch.
  - Why implement: Cheaper escalation reduces 10-24 second bounded-browser paths and repeated startup/navigation costs.
  - Tradeoffs / risks: Reused browser/page state must remain scoped, deterministic, and cleaned up reliably on failure.
  - Acceptance Criteria:
    - Preflight eligibility uses route family, publisher success history, static evidence, and listing/email-gate low-yield policies.
    - Escalation can reuse preflight browser/page, cookies, local storage, current URL, and downloaded-candidate context.
    - Tests cover preflight skip, escalation reuse, cleanup on failure, and no cross-publisher leakage.

- **Title:** Reduce browser prompt playbook payload [Impact: 4/5, Effort: 2/5]
  - Problem fixed: Prompt preparation can still serialize up to three playbooks with multiple step and trap lines.
  - Why implement: Sending only the winning playbook by default lowers token cost and reduces agent confusion.
  - Tradeoffs / risks: Alternative playbooks should still be available for low-confidence route selection.
  - Acceptance Criteria:
    - Route prompts include only the winning playbook by default.
    - Alternative playbooks are included only when selection confidence is low or drift evidence requires them.
    - Full playbook YAML remains outside the prompt and prompt hashes capture the compact payload.

- **Title:** Add live terminal watchers for browser-use early stop [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Current terminal salvage handles some timeout/blocker cases but does not continuously watch downloads, network events, confirmation text, or blocker quorum during normal runs.
  - Why implement: Stopping as soon as terminal evidence appears avoids extra LLM/action steps after success or known failure.
  - Tradeoffs / risks: Watchers must avoid false positives and route terminal evidence through normal artifact finalization.
  - Acceptance Criteria:
    - Runtime watches download directory, network PDF/document URLs, email/request confirmations, form disappearance, terminal pages, and known blockers.
    - Terminal evidence signals agent stop and emits typed success/blocker outcomes.
    - Tests cover valid artifact, email confirmation, blocker quorum, terminal page, and non-terminal false-positive text.

- **Title:** Canary-enable same-publisher session reuse and warm workers for bounded batches [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Session reuse and warm worker pool infrastructure exist but remain opt-in or disabled by default.
  - Why implement: Warm batch execution avoids repeated profile, cookie-banner, subprocess, and browser startup costs.
  - Tradeoffs / risks: Rollout must prevent cross-publisher leakage and restart workers under run-count, idle, or memory limits.
  - Acceptance Criteria:
    - Safe same-publisher session reuse can be enabled for bounded batch acquisition profiles with TTL and host scope.
    - Warm worker pool can be canary-enabled for same-publisher batches with one-shot subprocess fallback.
    - Telemetry reports reuse outcomes, avoided startups, worker restarts, memory pressure, and failure fallback counts.

- **Title:** Add conditional browser evidence and blocker forensics policies [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Known successful routes and expected blockers can still capture heavy screenshots, HTML, assets, network resources, copied artifacts, and detailed logs.
  - Why implement: Verified repeat successes and remembered blockers should be cheap while novel failures still retain forensic detail.
  - Tradeoffs / risks: Sampling and drift detection must preserve enough evidence to debug regressions.
  - Acceptance Criteria:
    - Known verified successes store minimal evidence: artifact hash, artifact URL, route ID, validation status, final URL, and sampled audit flag.
    - Full evidence is retained for new publishers, new routes, failed runs, sampled audits, drift, parser errors, and suspected regressions.
    - Expected CAPTCHA, 403, static archive, business-email rejection, and remembered blockers default to metadata-only forensics with typed blocker codes.

- **Title:** Add route-specific worker timeout buffers [Impact: 3/5, Effort: 2/5]
  - Problem fixed: Route-specific agent budgets exist, but the one-shot worker still adds a fixed outer timeout buffer.
  - Why implement: Per-route worker buffers fail stuck runs faster and free capacity sooner.
  - Tradeoffs / risks: The outer envelope must still leave enough time for terminal salvage and artifact finalization.
  - Acceptance Criteria:
    - Worker timeout buffer is resolved by route family and terminal-salvage policy.
    - Known impossible routes fail fast with typed blocker outcomes.
    - Tests assert route-specific outer timeout calculation and salvage-before-timeout behavior.

- **Title:** Add browser acquisition avoided-spend benchmark [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Operational memory and cache features exist, but there is no read-only benchmark quantifying avoided browser launches, model calls, runtime, retries, and cost.
  - Why implement: Browser-use x100 progress should be measured by how often runs avoid full agent work.
  - Tradeoffs / risks: Benchmark must be read-only and must not mutate route memory, artifacts, or publisher state.
  - Acceptance Criteria:
    - Benchmark reports exact-route reuse, publisher-policy reuse, mailbox-promoted memory, artifact-cache hits, deterministic autofill, warm-worker reuse, avoided launches, avoided model calls, latency savings, and cost per acquired report.
    - Results are grouped by publisher, route family, and outcome.
    - JSON/Markdown evidence can be retained in release or quality review artifacts.

---

### 6. Autonomous Operation Through Existing Orchestrators

- **Title:** Build a single autonomous run supervisor [Impact: 5/5, Effort: 5/5]
  - Problem fixed: Operators still choose between ingest, publish, download, mailbox poll, or UI replay entrypoints.
  - Why implement: One supervisor can plan, resume, retry, repair, validate, render, create a draft, hold, dead-letter, or notify safely.
  - Tradeoffs / risks: The supervisor must not duplicate generator domain logic or service I/O, and it must not autonomously make the final public-publish decision.
  - Acceptance Criteria:
    - Supervisor consumes state, checkpoints, preflight reports, retry telemetry, validation failures, idempotency records, publish readiness, and health scorecards.
    - It emits typed supervisor decisions before each side effect and ends publishing workflows in `draft` or `review_required` status.
    - Public auto-publish remains disabled until a retained corpus demonstrates safe claims, no internal-ID leakage, stable crop acceptance, stable WordPress updates, duplicate suppression, rollback, and consistent editorial quality.
    - Execution routes through existing orchestrators and canonical services only.

- **Title:** Add a read-only `PipelinePlan` before execution [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Operators request implementation flags instead of intent and side-effect visibility.
  - Why implement: A no-side-effect plan makes autonomous runs inspectable and safer.
  - Tradeoffs / risks: Plan generation must not pre-create side effects or perform expensive work.
  - Acceptance Criteria:
    - `autopilot --plan-only` or equivalent produces typed steps, skipped work, blockers, credentials, side effects, checkpoints, idempotency keys, and expected artifacts.
    - Plans cover ready, partial, failed, missing-credential, and publish-only states.
    - Plan execution uses existing orchestrators without duplicating domain logic.

- **Title:** Make workflow-control mandatory execution authority [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Workflow-control can resolve metadata, but paths may still bypass policy gates.
  - Why implement: Autonomy needs one authority for intent, retry policy, preflight profile, publish policy, pre-LLM gates, operational memory, and concurrency.
  - Tradeoffs / risks: Existing CLI/UI paths must be migrated carefully to avoid behavior drift.
  - Acceptance Criteria:
    - No CLI/UI autonomous path bypasses workflow-control gates.
    - Every workflow logs resolved intent, retry policy, side-effect plan, budget profile, resume stage, and blockers.
    - Tests cover direct CLI, UI replay, supervisor, and publish-ready paths.

- **Title:** Implement durable autonomous dead letters and scheduled actions [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Failures and deferred work are not consistently managed as pipeline-wide autonomous work items.
  - Why implement: Temporary rate limits, endpoint instability, mailbox delays, credential refresh windows, and terminal failures should recover or escalate without manual reruns.
  - Tradeoffs / risks: Duplicate failure loops must be suppressed and state migrations must be backwards compatible.
  - Acceptance Criteria:
    - `autonomous_dead_letters` records run ID, workflow, step, AppError taxonomy, retry decision, checkpoint stage, input checksum, artifact refs, remediation code, and runbook link.
    - `scheduled_actions` records workflow, step, payload reference, earliest/latest run time, retry decision, blocker code, dependency, and attempt budget.
    - Tests cover transient retry cooldown, permanent dead-letter, duplicate loop suppression, and user-action-required scheduling.

- **Title:** Expand due-work scheduling beyond mailbox delivery [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Mailbox delivery has durable due-request scheduling, but model limits, endpoint outages, credential blockers, validation repair, publishing, and other workflows lack a generic scheduler.
  - Why implement: Autonomy needs one deferred-work mechanism rather than one-off queues per workflow.
  - Tradeoffs / risks: Existing mailbox scheduling should be reused or adapted, not duplicated.
  - Acceptance Criteria:
    - Generic scheduled actions cover retryable, deferred, and user-action-required work outside mailbox delivery.
    - Scheduler can dispatch through existing orchestrators with attempt budgets and loop prevention.
    - Tests cover mailbox due work, credential blockers, validation repair, publish defer, and retryable endpoint failure.

- **Title:** Create durable publish jobs and a transactional outbox [Impact: 5/5, Effort: 5/5]
  - Problem fixed: A read-only publish snapshot cannot manage durable autonomous publication and retries.
  - Why implement: Publish intents and WordPress side effects need transactional durability, idempotency, retry, and dead-letter handling.
  - Tradeoffs / risks: If the current snapshot remains read-only, it must be renamed rather than treated as a queue.
  - Acceptance Criteria:
    - `publish_jobs` stores publish intents and lifecycle state.
    - `publish_outbox` atomically records WordPress side-effect intents.
    - Jobs can be retried, dead-lettered, and idempotently delivered without corrupting publish state on partial WordPress failure.

- **Title:** Expand idempotency metadata to every external side effect [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Autonomous reruns are unsafe if any ambiguous write can duplicate external side effects.
  - Why implement: Idempotency is the foundation for safe retry, resume, and publish automation.
  - Tradeoffs / risks: Side-effect registry must not create pass-through abstractions or duplicate service boundaries.
  - Acceptance Criteria:
    - Side-effect registry maps OpenAI/vector writes, Drive uploads, WordPress media/posts, report-store mutations, state transitions, cost ledger writes, archive writes, route playbook promotion, and browser identity updates to owner, scope, logical key, checksum inputs, and artifact refs.
    - CI fails new unwaived side effects without idempotency metadata.
    - Tests prove duplicate suppression and checksum mismatch behavior.

- **Title:** Add real-time spend guardrails and budget-aware model routing [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Autonomous execution needs pre-call cost/time/token controls, not only post-run reporting.
  - Why implement: Safe unattended operation requires bounded spend decisions and deterministic compaction.
  - Tradeoffs / risks: Budget decisions must be explicit outcomes rather than silent quality reductions.
  - Acceptance Criteria:
    - `RunBudget` covers run/day/publisher scopes for USD, model calls, tokens, wall time, retries, browser launches, Drive writes, WordPress writes, and PDFs per batch.
    - Expensive actions check budget before execution and produce warn, pause, defer, stop, or override outcomes.
    - Model routing policy maps task family and difficulty to model tier, max input budget, fallback tier, quality threshold, and deterministic compaction strategy.

- **Title:** Roll deterministic context compaction across eligible model-call families [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Context compaction exists for JSON prompt requests but is disabled by default and not consistently applied across evidence, artifact, validation, OCR/image, or vector-backed call families.
  - Why implement: Budget-aware autonomy needs deterministic prompt-size control before model calls, with retained anchors and reproducible logs.
  - Tradeoffs / risks: Compaction must preserve metrics, quotes, claims, citations, evidence, validation anchors, sources, figures, tables, and page references.
  - Acceptance Criteria:
    - Eligible model-call families declare compaction policy, max tokens/cost thresholds, preserved anchors, and fallback behavior.
    - Logs record compaction trigger, retained anchors, dropped sections, avoided tokens, and estimated avoided cost.
    - Regression tests compare evidence retention on fixed corpora.

- **Title:** Add provider failover behind the single LLM contract [Impact: 4/5, Effort: 4/5]
  - Problem fixed: Provider failure can block autonomous runs when a policy-approved fallback could succeed.
  - Why implement: Resilience belongs behind the canonical LLM boundary with orchestrator-visible decisions.
  - Tradeoffs / risks: Failover must be bounded, policy-driven, normalized, and not visible as provider-specific payloads to generators.
  - Acceptance Criteria:
    - Provider-specific responses normalize into the stable typed LLM response contract.
    - Failover is bounded, logged, retry-policy aware, and orchestrator-visible.
    - Tests cover primary success, fallback success, fallback exhaustion, provider mismatch validation, and non-retryable contract failures.

- **Title:** Promote health scorecards and public-site trust checks into autonomous gates [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Scorecards and smoke checks exist but should directly drive publish, repair, retry, hold, and notification decisions.
  - Why implement: Autonomous publishing must not ship broken or low-trust public pages.
  - Tradeoffs / risks: Thresholds must be calibrated to catch real failures without causing noisy holds.
  - Acceptance Criteria:
    - Every autonomous workflow writes a health scorecard consumed before publish or retry.
    - Public-site trust checks cover HTTPS, canonical sitemap URLs, 404/500 behavior, no path/PHP leakage, representative pages, metadata/social tags, request count, and page weight.
    - Failed checks withhold, roll back, or route pages to remediation with retained screenshots/evidence.

- **Title:** Expand autonomous happy-path smoke to full report lifecycle [Impact: 4/5, Effort: 4/5]
  - Problem fixed: The autonomous smoke suite currently covers mailbox acquisition, but not full report generation, crash resume, validation repair, health gating, or WordPress hold/draft/publish policy.
  - Why implement: A pipeline-wide supervisor needs non-live proof over the whole autonomous lifecycle before it can be trusted.
  - Tradeoffs / risks: Tests must fake only external boundaries and use real SQLite, checkpoints, idempotency, supervisor decisions, and scorecards.
  - Acceptance Criteria:
    - Smoke suite covers fresh run planning, fake Drive input, fake LLM responses, report generation, checkpoint crash/resume, validation repair, health gating, publish hold/draft/publish, mailbox due work, and duplicate suppression.
    - External systems are faked at service boundaries.
    - The suite emits retained scorecard and remediation-summary evidence.

- **Title:** Generate capability maps and autonomous release/remediation summaries [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Future agents need deterministic ownership and run outcome summaries without log archaeology.
  - Why implement: Capability maps and summaries reduce operational confusion and make autonomous runs reviewable.
  - Tradeoffs / risks: Generated docs must come from code/config and should fail stale, not become manually edited drift.
  - Acceptance Criteria:
    - `docs/generated/capability_map.md` covers external system to service boundary, workflow to orchestrator/generator/service/contracts, artifact to prompt/schema/generator/validator, state table to owner, side effect to idempotency scope, and failure code to runbook/remediation.
    - Autonomous summaries include what ran, changed, skipped, failed, auto-fixed, deferred, required credentials, published, and held from publish.
    - CI fails stale generated maps or missing required ownership metadata.

---

### 7. Code Hygiene and Executable Enforcement

- **Title:** Complete root tool manifest consolidation [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Root `pyproject.toml` now carries tool config, but `pytest.ini`, `mypy.ini`, explicit `mypy.ini` usage, and dependency metadata outside `[project]` still fragment the tool manifest.
  - Why implement: Tooling should have one source of truth so local runs, CI, and agents do not diverge on hidden defaults.
  - Tradeoffs / risks: Migration must preserve existing commands and avoid broad formatting or dependency churn.
  - Acceptance Criteria:
    - Remaining pytest, mypy, coverage, Ruff, and packaging/dependency configuration is either moved into `pyproject.toml` or explicitly documented as intentionally separate.
    - CI/local scripts stop hard-coding stale config-file paths where unnecessary.
    - Focused config tests or command checks prove behavior is unchanged.

- **Title:** Add root pre-commit hooks [Impact: 4/5, Effort: 2/5]
  - Problem fixed: Pre-commit exists only in vendored/browser-use context, not as a root project standard.
  - Why implement: Most simple hygiene defects should be blocked before CI.
  - Tradeoffs / risks: Hooks must be fast enough for daily use and align with CI.
  - Acceptance Criteria:
    - Root hooks cover Ruff format, Ruff lint, mypy changed files or scoped typing, secret scanning, YAML/JSON validation, no-large-files, and line-ending normalization.
    - Hook commands share the same configuration as CI/local gates.
    - README documents setup and bypass policy for rare cases.

- **Title:** Create one declarative quality-gate source for local and CI [Impact: 5/5, Effort: 4/5]
  - Problem fixed: `run_quality_gate.py` and GitHub Actions can drift because gates are separately hard-coded.
  - Why implement: One gate manifest makes local and CI behavior converge.
  - Tradeoffs / risks: Gate generation must preserve ordering, environment assumptions, and artifact retention.
  - Acceptance Criteria:
    - `quality_gates.yaml` or equivalent declares gate order, commands, required artifacts, live/non-live status, and waiver rules.
    - Local quality command and CI consume the same source.
    - Tests fail if generated/local/CI gate definitions drift.

- **Title:** Complete staged mypy strictness and full Ruff rollout [Impact: 4/5, Effort: 4/5]
  - Problem fixed: The mypy baseline is burned down, but active settings still allow broad missing imports, disabled return-any warnings, follow-imports skipping, and limited Ruff enforcement.
  - Why implement: Type and lint debt should stay burned down through staged strictness, not just a zero baseline snapshot.
  - Tradeoffs / risks: Strictness must be introduced by package tier to avoid noisy unrelated rewrites.
  - Acceptance Criteria:
    - Contracts, services, generators, orchestrators, UI, and CLI have staged mypy strictness targets with owner/expiry for remaining exceptions.
    - Ruff lint enforcement expands beyond changed-file `F` checks toward the policy rule set.
    - CI reports strictness progress and fails new unwaived violations in critical packages.

- **Title:** Expand repository entropy and long-file hygiene checks [Impact: 3/5, Effort: 3/5]
  - Problem fixed: Hygiene scanning has allowlist ownership/expiry, but duplicate-file, orphan-script, stale-doc, unused-fixture, root-clutter, vendored-drift, and full long-file inventory gates remain incomplete.
  - Why implement: Repo entropy raises the cost for future agents and hides genuine implementation risk.
  - Tradeoffs / risks: Checks need explicit allowlists for retained evidence, caches, fixtures, and vendored code.
  - Acceptance Criteria:
    - Hygiene checks report duplicate files, orphan scripts, stale docs, unused fixtures, root clutter, vendored drift, expired allowlists, and long-file inventory.
    - Findings include owner, path, reason, expiry/waiver status, and severity.
    - Main CI or release evidence includes the hygiene report with bounded noise.

- **Title:** Complete movement-only publish and ingest orchestrator decomposition [Impact: 5/5, Effort: 5/5]
  - Problem fixed: `publish_orchestrator.py` remains the principal publishing hotspot, and `ingest_orchestrator.py` still owns substantial state filtering, Drive materialization, worker coordination, cursor policy, and finalization behavior.
  - Why implement: These coordinators are high-risk control-plane surfaces that need semantic private owners without changing public behavior.
  - Tradeoffs / risks: This must be movement-only unless behavior changes are explicitly approved; retry behavior, ordering, idempotency, logs, and side effects must be preserved.
  - Acceptance Criteria:
    - `publish_orchestrator.py` remains the canonical public facade while semantic private owners absorb publish package validation, cross-report workflow, term resolution, state transitions, idempotency, and readiness assembly as appropriate.
    - `ingest_orchestrator.py` keeps `run_ingest` as the public entrypoint while remaining stable capabilities move into private owners.
    - Movement evidence and focused tests prove public imports, retry counts, cursor behavior, state transitions, logs, and external side effects are unchanged.

- **Title:** Add changed-critical-file mutation selection [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Mutation thresholds are policy-backed, but target inventory and caps remain manually hard-coded and changed critical modules are not automatically required to have mutation coverage or waivers.
  - Why implement: Changed critical control-plane and generator code should be hard to fake by default.
  - Tradeoffs / risks: Mutation runtime must stay bounded with clear target selection and waiver rules.
  - Acceptance Criteria:
    - Changed critical files in generators, orchestrators, services, contracts, and control-plane packages are discovered automatically.
    - Each changed critical file has mutation coverage or an explicit owner/reason/expiry waiver.
    - CI reports selected targets, skipped targets, survivor counts, and waiver status.

- **Title:** Add import-graph ownership reports and facade-thickness limits [Impact: 4/5, Effort: 4/5]
  - Problem fixed: Coupling drift and over-thick facades can hide behind compatibility layers.
  - Why implement: Boundary and indirection health should be visible before it becomes structural debt.
  - Tradeoffs / risks: Facade limits must preserve legitimate compatibility facades and semantic public boundaries.
  - Acceptance Criteria:
    - PR artifacts report fan-in, fan-out, private module leakage, cross-context imports, avoided/detected cycles, and new dependency edges.
    - Facade gates enforce max facade-owned logic, max private imports unless justified, no forwarding-only wrapper chains beyond one compatibility layer, and module docstrings explaining semantic ownership.
    - Violations require explicit waiver or refactor.

- **Title:** Create code hygiene scorecards for PRs and releases [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Hygiene trends are hard to review without a single artifact.
  - Why implement: Scorecards turn type debt, coverage, mutation, boundary violations, allowlist expiry, and dependency drift into visible release evidence.
  - Tradeoffs / risks: Scorecards should report deltas clearly and avoid becoming noisy dashboards.
  - Acceptance Criteria:
    - `code_hygiene_scorecard.json` and `code_hygiene_scorecard.md` include type debt count, expired baseline count, package coverage, mutation score by target, long-file inventory, import cycles, boundary violations, allowlist expiry, dependency drift, dead-code findings, facade warnings, and root clutter.
    - PR/release evidence includes scorecards.
    - Configured regressions fail gates or require explicit waiver with owner and expiry.
