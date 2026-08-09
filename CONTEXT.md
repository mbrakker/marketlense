# MarketLense Project Context

> **Purpose:** durable, non-chronological project-state summary for humans and AI agents.
> **Snapshot date:** 2026-08-07.
> **Repository reviewed:** `mbrakker/marketlense` `main` at `8ff7ec21b510c78565d0b28aa26d440c79f7d8c5`.
> **Scope:** decisions, confirmed facts, current status, unresolved work, operating constraints, and important artifacts synthesized from the current repository, the Market Lense Notion workspace, and project conversations.
>
> This file is orientation context, not a replacement for executable policy, canonical workflow documentation, or the active backlog.

## 1. Source-of-truth precedence

When sources disagree, use this order:

1. **Current code, tests, schemas, generated capability references, and executable CI/policy at the current repository HEAD.**
2. **`CONSOLIDATED_TODO.md`** for current work status. It is the repository's sole active prioritized work register.
3. **Canonical current-reference documents under `docs/` and `README_WORDPRESS.md`.**
4. **Notion** for product intent, editorial rules, entity definitions, design rationale, runbooks, and planning context. Notion status statements are not automatically current.
5. **Project conversations** for owner decisions, priorities, constraints, and exploratory ideas not yet promoted into code/docs/backlog.
6. Historical plans, archived specs, old TODOs, and point-in-time reviews explain prior decisions but do not override current state.

### Known documentation freshness issue

The Notion homepage and “16 — Latest Repo Alignment Assessment” still contain a July 5, 2026 implementation snapshot that lists hard budget gates, durable publish jobs, mailbox worker/scheduler, and deferred-mail pipeline resume as missing. Current repository evidence materially supersedes that snapshot: durable workflow queues, mailbox-delivery queue handling, a one-shot workflow supervisor, broad budget authority, queue-backed publication, and deferred-work recovery infrastructure now exist. Treat the July 5 readiness score/status as historical.

`CONSOLIDATED_TODO.md` was last audited 2026-07-26. Repository HEAD is 2026-08-04, so active backlog items should be re-audited before being declared closed, but they remain the canonical work register until explicitly updated.

## 2. What MarketLense is

MarketLense is a **report-intelligence pipeline and publishing system** that discovers and acquires industry research, converts source material into structured evidence and validated editorial artifacts, reuses that evidence for Signals and multi-report Briefings, and publishes approved output to a public WordPress intelligence portal.

The target domain includes ecommerce, marketplaces, Amazon, retail media, digital marketing, retail, consumer behavior, advertising/media, technology, payments, logistics, data/platforms, and adjacent market-intelligence domains.

The strategic product is **not**:

- a generic report archive;
- an AI-summary blog;
- a content-marketing site;
- a statistical benchmarking engine that synthesizes normalized metrics across incompatible publishers;
- a WordPress application that generates intelligence at request/render time.

The intended product is an **institutional intelligence index** that turns each processed report into a reusable evidence asset and lets readers understand both individual reports and cross-source market developments.

### Primary public entity model

Canonical primary navigation:

`Reports | Topics | Signals | Briefings | Publishers`

Secondary/trust discovery direction:

`Figures | Regions | Time Periods | Methodology`

Operator-facing concepts include Sources, Runs, Validation/Publish Readiness, workflow queues/remediation, and Cost.

### Internal project name vs public brand

- Repository/system name: **MarketLense / Market Lense**.
- Current WordPress front-end documentation and wordmark use the **Market Bearing / MarketBearing** public brand.
- Do not casually rename internal contracts, CLI namespaces, WordPress `ml_*` identifiers, or repository structures as part of visual-brand work.

## 3. Non-negotiable product and engineering decisions

### Product/editorial

- **Evidence before prose.** Editorial output must be grounded in retained report evidence.
- **Use the extraction fully.** The WordPress/editorial layer should exploit the structured evidence, figures, charts, findings, source context, and related artifacts already produced rather than falling back to thin summaries.
- **Human-expert feel.** Public output should read like top-tier consultancy/editorial work: specific, decision-relevant, source-aware, and polished rather than visibly templated or machine-generated.
- **Do not expose pipeline mechanics unnecessarily.** Public users need source attribution, limitations, methodology, and trust signals—not internal evidence IDs, filesystem paths, raw OCR, operational diagnostics, model traces, or generation scaffolding.
- **Validation before publication.** Failed, stale, malformed, ungrounded, or incomplete customer-facing artifacts must not be published.
- **No progressive public enrichment.** Publishing draft/partial HTML first and enriching it later is explicitly excluded (`X1`).
- **WordPress is a rendering/publication layer.** Intelligence generation, grounding, evidence maps, semantic validation, category decisions, Signals, and Briefing synthesis belong in Python/backend workflows.
- **No cross-publisher metric normalization.** Preserve raw values, units, methodology, geography, scope, and caveats. Cross-report intelligence should cluster evidence/themes and describe convergence, tension, novelty, or implications—not compute synthetic averages from incompatible metrics.
- **Signals are editorial evidence patterns, not normalized metrics.** Signal strength can use evidence count, publisher diversity, recency, directional clarity, strategic relevance, novelty, methodology confidence, and bias risk without pretending to measure market truth.
- **Cross-report output is public as Briefings.** “Cross-report analysis” remains an internal capability name; public synthesis routes to Briefing artifacts/pages.
- **Publishers, Sources, and Reports are separate lifecycle entities.** A publisher is an organization, a source is an acquisition candidate/outcome, and a report is a validated source-backed intelligence artifact.

### Engineering

- **Modular monolith by default.** One deployable Python system with strict internal boundaries. New deployables/services need measured operational justification, not “future readiness.”
- Layer ownership is: `contracts <- services <- generators <- orchestrators <- CLI/UI`.
- Services own external I/O; generators own domain production; orchestrators own sequencing/retries/state/idempotency; utilities are deterministic helpers.
- **Deterministic before probabilistic.** Parse, normalize, deduplicate, validate, score, cache, and reuse deterministically before invoking an LLM.
- **Reuse before regeneration.** Valid hashes, lineage, checkpoints, persisted evidence, route memory, and idempotency state should prevent unnecessary external calls or full reprocessing.
- **Simplicity is a core design constraint.** Avoid overengineering rare edge cases, generic frameworks, speculative queues/services, and abstractions that only forward calls.
- **Retries belong to orchestrators.** Provider/service hidden retries are not the workflow retry strategy.
- **Typed contracts and fail-closed behavior** are required at persisted/external boundaries.
- **External side effects must be idempotent and reviewable.** Publication and other writes must be gated and read back where applicable.
- Prefer proven open-source components/practices when they materially improve speed, cost, reliability, or simplicity, but do not add dependencies or abstractions without current evidence of benefit.

## 4. Canonical entity and evidence model

### Publisher
Organization-level source-authority entity. Holds publisher profile/coverage information and relationships to reports/signals/briefings. Do not mix URL-level acquisition state into publisher identity.

### Source
Operator-facing acquisition candidate/outcome, normally keyed by canonicalized URL/source identity. Retains acquisition route, outcome, blockers, and provenance. A Source is not a Report until a verified artifact exists.

### Report
Atomic source-backed intelligence unit. Retains source attribution, report/publisher identity, geography/time period, topics/categories, evidence, validation, generated artifacts, lineage/checkpoints, and publication state.

### Topic
Stable editorial domain. Native WordPress categories are the canonical public Topic implementation. Topic assignment uses explicit definitions plus include/exclude semantics, not weak keyword/tag matching alone.

### Data Point / evidence
Internal metric/evidence record. Preserve raw value/text, unit, report, publisher, evidence/page context, confidence/validation, and provenance. Public “Figures” should eventually project approved data points without implying normalized comparability.

### Signal
Source-backed market movement/pattern/risk/opportunity supported by report/evidence references. Current backend and WordPress Signal workflows are implemented; richer temporal lifecycle/velocity remains a future product-system direction unless promoted into the active backlog.

### Briefing
Validated multi-report synthesis built from persisted projections/evidence. Current queue-driven Briefings use immutable/frozen source sets and preserve publisher diversity, uncertainty/divergence, and raw source-linked metrics.

### Report Card / cover
Reusable public Report presentation contract with small/medium/large variants, complete TLDRs, deterministic semantic cover fingerprint, and three cover assets. WordPress fails closed on incomplete card contracts.

### Publish Readiness
Signed/hash-bound decision over the exact final rendered HTML and normalized WordPress projection. It is the canonical report publication gate, not a loose UI score.

### Workflow/operational entities
Durable SQLite-backed workflow jobs, outbox events, approvals, remediation records, budget-deferred work, validation-run manifests, usage/cost ledger records, source identity observations, mail-delivery state, and checkpoint/lineage records support autonomous operation without becoming public content objects.

## 5. Current architecture and end-to-end flow

### High-level lifecycle

`Discover -> Acquire -> Verify/Handoff -> Ingest -> Analyze -> Validate -> Render -> Project -> Enrich/Synthesize -> Readiness -> Review -> Publish -> Readback/Projection`

### Durable queue graph

The current queue platform is a single SQLite-backed, typed, at-least-once workflow system. Effective exactly-once outcomes are achieved through idempotency keys, hashes, readbacks, lineage checks, and unique outbox events—not by claiming exactly-once queue delivery.

Core graph:

`publisher_discovery -> report_acquisition -> mailbox_delivery/source_ingest -> report_selection -> report_analysis -> report_render -> analytics_projection -> claim_embedding / signal_candidate / briefing_opportunity -> generation -> cover_generation -> publication_readiness -> human approval -> wordpress_publish -> wordpress_projection`

Additional registered queues cover repair, revalidation, recategorization, vector retention, WordPress category updates, public-render repair, cost reconciliation, release evidence, and related governed work.

### One-shot workflow supervisor

`python -m src.cli supervise-workflows --once` composes existing queue/recovery operations under a singleton lease. It is deliberately **not an embedded scheduler or endless loop**. An external timer (cron/systemd/hosting scheduler) should invoke it only after queue/recovery evidence is acceptable. Default configuration remains conservative/feature-gated.

This is consistent with the project goal of autonomous operation without introducing an unnecessary distributed scheduler/broker at current scale.

## 6. Acquisition state

### Implemented routes/capabilities

- Direct report/PDF acquisition.
- Browser-assisted acquisition through the canonical browser service; Browser Use remains the vendored browser runtime/reference.
- Persisted route-memory/resource economics and bounded route suppression for repeated compatible terminal failures.
- Mailbox acquisition through Gmail and IMAP.
- Email-gated acquisition as durable workflow state rather than a terminal browser result.
- PDF attachments and PDFs inside ZIP attachments.
- Canonical acquisition-to-ingest handoff that revalidates local bytes/hash before enqueueing ingest.
- Canonical source identity/provenance that prevents mirror URLs from creating duplicate research work when the bytes are the same.
- Malformed PDF quarantine/revalidation path.
- Browser/mailbox/Drive/resource accounting and budget authority.

### Acquisition identity rule

The source identity is not the report ID. Verified bytes plus processing version drive ingest idempotency. Reused Drive IDs with changed bytes fail closed rather than silently rebinding a report.

### Browser direction from project discussions

The goal is to make browser flows faster, cheaper, and more reliable without replacing the established browser boundary merely for novelty. Harness-style or other OSS techniques are useful when they can be imported/adapted behind the current boundary with measurable benefit. Session reuse, generic executors, aggressive concurrency, and similar optimizations remain evidence-driven rather than default architecture.

## 7. Report processing and evidence reuse

### Current processing model

The report pipeline has explicit source, selection, analysis, validation, render, projection, and publication boundaries. Source artifact families include document/taxonomy/evidence and validation structures represented by schemas in `src/schemas`.

### Durable checkpoints

Current semantic checkpoints support reuse/resume around:

- `source_prepared`
- `selection_complete`
- `analysis_complete`
- `render_complete`
- `latest_safe`

Checkpoint reuse requires integrity/lineage validation. The design goal is to rerun only the affected family/stage rather than re-extracting/re-calling the entire report.

### Structured-output recovery

Required report JSON families use centralized schema-constrained recovery. Invalid output is normalized/validated, deterministically repaired where possible, bounded model repair/regeneration may occur, and terminal failure/abstention remains explicit. Empty or malformed model output must not become a successful artifact.

### Grounding-safe regeneration

Regeneration uses candidate artifacts and audits before atomic promotion. Unsupported/hallucinated evidence references, numerical inconsistency, contradiction, missing material evidence, or failed grounding block promotion/publication.

### Visuals and charts

The pipeline extracts visual candidates, uses crop/refinement and QA logic, retains accepted visual/evidence linkage, and omits weak or unlinked cards instead of forcing poor charts into public pages. The public goal is **useful, legible, well-cropped evidence**, not maximizing image count.

### Future-proofing already required for cross-report use

Do not discard report-local structured evidence after publication. Retained claims/evidence, raw metrics, chart/crop artifacts, captions, recommendations, methodology/limitations, topic/category/geography/time metadata, source pages, claim embeddings, lineage, and projections are the reusable substrate for future Signals, Briefings, related-content links, retrieval, and graph-like experiences.

## 8. Editorial/public output standard

A strong report/intelligence page should use available evidence to provide, where supported:

- clear report identity and source/publisher context;
- executive/analyst summary;
- key findings and implications;
- covered topics;
- key figures/raw metrics with source context;
- important charts/tables/visual evidence;
- quotations only when properly sourced;
- limitations/methodology/caveats;
- related reports/topics/signals/briefings/publishers;
- derivative editorial material such as expert commentary and LinkedIn examples when grounded.

Public copy should avoid generic AI phrasing, mechanical labels, repeated boilerplate, visible truncation, filename-style titles, mojibake, unsupported recommendations, fake quotations, and vague “why it matters” filler.

The project does **not** require exposing every internal validation mechanism to the reader. Trust should be expressed through good sourcing, clear caveats, methodology, and coherent editorial quality, while internal IDs/diagnostics remain operator-only.

## 9. Cross-report intelligence decisions

### Implemented direction

Cross-report analysis is implemented as **Briefing generation from persisted report projections/evidence**. Queue-driven opportunities freeze source-content hashes before generation. Later source changes create later opportunities rather than mutating a running Briefing.

### Metric-normalization decision

Metric normalization is intentionally out of scope because cross-publisher definitions, samples, units, geographies, and methodologies make naive comparison misleading and operationally expensive. Preserve raw values and context.

Use cross-report evidence to detect:

- directional convergence;
- emerging themes;
- contradictions/tension;
- acceleration/intensity;
- strategic implications;
- blind spots;
- regional/channel divergence;
- capability gaps.

### Original “future cross-report article” chat idea vs current architecture

Project discussions proposed a topic-idea service, metadata filtering by categories/tags/geography/time, a dedicated article evidence/vector context, and grounded synthesis designed to avoid re-ingesting historical reports. The **goal remains valid**: future synthesis must reuse retained evidence and avoid full report reprocessing. The current implementation realizes this primarily through projections, frozen source manifests, claim embeddings, checkpoints, and the existing LLM/vector boundary. A separate per-article vector store is therefore **not a current architectural requirement** unless profiling demonstrates a real retrieval need.

### Dynamic report graph idea

A continuously updated graph of report interconnections was discussed for related-report links, Briefing/source selection, and signals. Treat this as an **exploratory product layer**, not a current committed storage architecture. If implemented, derive relationships from canonical persisted entities/evidence/projections rather than creating a second source of truth or requiring metric normalization.

## 10. WordPress/public portal state

### Boundary

WordPress publishes/render approved backend output; it must not analyze reports or synthesize intelligence at render time.

### Implemented public entities/surfaces

- Reports (`ml_report`)
- Briefings (`ml_briefing`)
- Signals (`ml_signal`)
- Topics through native WordPress categories
- Publisher directory/profiles
- Shared archive/search/filter/card components
- Methodology/trust presentation
- Public intake forms for briefing/correction/submission workflows in code, with hosted smoke still part of backlog closure

### Canonical card system

Reports and Briefings use shared size semantics and deterministic covers. Report cards expose complete text instead of CSS truncation. Existing posts can be updated in place through remediation/backfill paths.

### Public safety

Public rendering is bounded by a branded safe-error boundary with correlation IDs; implementation details stay in private structured events. Missing/invalid content should fail closed or show neutral institutional empty states rather than expose PHP/internal errors.

### Hosting constraint

The current WordPress sandbox is intentionally on **HTTP** as a temporary cost-saving/development setup. Do not overengineer permanent infrastructure around this sandbox. The final production project is intended to migrate to new hosting and must meet normal HTTPS/trust expectations there. Hosted HTTPS/sitemap trust remains represented by active backlog item `P3`; reconcile that item with the temporary-sandbox decision rather than forcing an unnecessary sandbox architecture migration.

## 11. Autonomous operation, cost, and reliability state

### Already implemented/closed foundations

According to the canonical backlog and current code, the following foundational items are no longer missing architecture concepts:

- typed workflow plans/control authority and configured run profiles (`A1`, `A2` closed);
- workflow-wide remediation ledger coverage (`A3` closed);
- malformed Drive PDF quarantine (`A4` closed);
- terminal blocker/avoided-browser-spend route policy (`A5` closed);
- budget-manager authority/operational proof (`A6` closed);
- budget-aware model routing/compaction/same-provider fallback (`A7` closed);
- canonical source identity/publication provenance (`A9` closed);
- recurring-failure opportunity reporting (`A11` closed);
- acquisition economics calibration (`A14` closed);
- corpus rehabilitation campaign flow (`A16` closed);
- canonical publish-readiness gate and grounding-safe regeneration work closed in the late-July implementation baseline;
- queue-backed publication/recovery coverage (`D7` closed);
- cached-provider accounting, crop-QA escalation, lazy model/ranking/crop shortcuts, prompt partials/fixtures, core discovery/mailbox/signal/embedding persistence, logging exposure controls, and CTO evidence integrity (`C1`–`C8` closed as recorded).

### Cost principles

- Cost must be attributable to provider/model/workflow/artifact/report where possible.
- Budget checks happen before expensive external operations where the canonical authority applies.
- Missing/unknown cost must stay “unknown,” not silently become zero.
- Model pricing can become stale; pricing attestation remains active work (`E10`).
- Reduce provider calls through deterministic compaction, persisted artifacts, checkpoints, route memory, prompt-family materialization, and targeted repair before changing the core model simply to chase cost.

## 12. Current unresolved work

The items below are **current backlog work**, grouped by outcome rather than chronology. Names/IDs come from `CONSOLIDATED_TODO.md`; consult that file for completion checks before implementation.

### A. Autonomous safety and cost control

- **A10 — Budget-deferred-work recovery and operator requeue:** complete safe, visible, idempotent recovery of budget-deferred work.
- **A8 — Compare retained model-call replay bundles:** make retained replay comparisons an operational regression outcome.
- **A15 — Complete explicit model-policy coverage and policy-effectiveness evidence:** extend hash-pinned policy and measured cost/quality evidence to all production model namespaces.
- **A17 — Calibrate deterministic admission thresholds from retained preflight funnels:** produce evidence-based threshold proposals without automatic source admission.

### B. Public trust, publishing, and hosted portal quality

- **P2 — Harden bounded public-observability events.**
- **P3 — Resolve hosted-site trust blockers:** HTTPS/transport/sitemap trust remains a hosting outcome; remember the current sandbox HTTP decision is temporary.
- **P10 — Operate correlated public-render failure telemetry.**
- **P12 — Release-locked sandbox publish canary:** repeatedly prove manifest-backed recovery and final sandbox publication on a small governed real-report cohort.
- **P14 — Restrict cohort-manifest publication to admitted artifacts.**
- **P15 — Operate canonical publish-readiness telemetry and refresh planning.**
- **P4 — Close public Briefing/correction/submission intake:** implementation exists; hosted smoke is still required for closure.
- **P5 — Finish responsive search and navigation.**
- **P6 — Raise report-card/evidence-exhibit editorial quality:** gate exists; blind human editorial acceptance remains.
- **P7 — Improve hosted public-site performance without contract loss.**
- **P8 — Complete concise public evidence, methodology, and related-content surfaces.**

### C. Evidence quality, reuse, and model efficiency

- **E6 — Retain a hash-pinned claim-embedding benchmark export.**
- **E10 — Attest active model-pricing rates before they become stale.**
- **E11 — Measure and optimize structured-output recovery effectiveness.**
- **E13 — Measure candidate-regeneration promotion effectiveness.**
- **E8 — Use canonical source identity to suppress duplicate research work.**
- **E9 — Materialize prompt-family outputs and route only required model calls.**
- **E12 — Persist pre-category editorial context checkpoints.**

### D. Release integrity and architecture enforcement

- **R1 — Publish release-evidence reviews where reviewers work.**
- **R2 — Enforce role boundaries, direct-I/O discipline, and controlled module growth.**
- **R3 — Restore service quality coverage above the retained baseline.**
- **R6 — Review bounded-log reduction telemetry and remediate recurring callers.**

### E. Boundary simplification

- **S3 — Simplify the PDF visual-heuristics boundary.**
- **S4 — Give WordPress shortcodes semantic ownership.**

### F. Product gaps that remain directionally important but are not automatically active engineering work

These are present in Notion/product discussions and should not be silently treated as already implemented or as higher priority than the canonical backlog:

- full public Figures/key-figure library and richer secondary Region/Time Period surfaces;
- Signal lifecycle/velocity history (`first_seen`, `last_seen`, strengthening/declining/disputed, etc.);
- unified hybrid/semantic search and evidence-backed answer mode;
- subscriptions/alerts/watchlists;
- richer dynamic entity/report graph;
- recurring Briefing schedules/editorial packaging beyond the current queue/opportunity model;
- OpenAI Batch API architecture from Notion page 14, unless/currently until repository evidence and backlog promote it as an active implementation path;
- external-search-first publisher discovery extensions beyond the currently implemented publisher inventory/discovery boundaries.

## 13. Explicitly deferred or excluded directions

Do not resurrect these as “obvious improvements” without new measured evidence.

### Deferred

- Generic/full report-generation DAG scheduler (`D1`).
- Streaming Drive prefetch + worker-safe PDF context pooling (`D2`).
- Broader adaptive concurrency/route-specific worker buffers (`D3`).
- Multi-provider failover (`D4`).
- Same-publisher warm workers/session reuse (`D5`).
- Arbitrary generic scheduler alongside the typed durable queue (`D6`).
- LinkedIn persona variants/comparative positioning (`D8`).
- Broader golden-output prompt scoring (`D9`).
- Browser executor/static DOM/prompt-payload/route-playbook tuning without measured gap (`D10`).
- Additional root pre-commit/declarative-gate/stricter-tooling ceremony without evidence (`D11`).
- Governed staging WordPress canary until a suitable staging target/approver exists (`D12`).

### Excluded

- **X1:** public draft HTML before enrichment/validation.
- **X2:** automatically lowering private-API promotion thresholds.
- **X3:** invented acquisition-form identity facts or public exposure of pipeline diagnostics.

## 14. Quality/release evidence state

- Repository HEAD reviewed for this context: `8ff7ec21b510c78565d0b28aa26d440c79f7d8c5`.
- The Aug 1 logical-error review found four reproducible issues (test cache expiry escaping to browser work; malformed publish-readiness nested surfaces; missing-side category consistency; malformed plural evidence references) and records them as remediated with regression coverage.
- Recent merged CI-fix PRs restored/aligned local quality-gate behavior with GitHub CI; PR #57 reports focused tests plus coverage, mutation, and quality-regression gates successful.
- CodeQL push/scheduled runs on current HEAD were successful in the reviewed GitHub Actions data.
- Do **not** infer from those facts that every live external workflow was re-run for this context snapshot. Hosted WordPress, credentials-dependent APIs, and real-provider canaries remain governed by their own evidence/tasks.

## 15. Important repository artifacts

### Entry points and governance

- `README.md` — stable repository orientation.
- `CONTEXT.md` — this non-chronological project-state orientation.
- `CONSOLIDATED_TODO.md` — **sole active prioritized work register**.
- `AGENTS.md` — mandatory engineering policy for coding agents.
- `docs/README.md` — canonical documentation inventory and status map.

### Product/editorial

- `docs/product/overview.md` — current product/entity model.
- `docs/product/editorial-output.md` — current public editorial semantics.
- `docs/product/report-lifecycle.md` — report lifecycle reference.
- `docs/quality/public-editorial-quality.md` — public editorial gate/rule inventory.
- `docs/brand-spec.md` — public brand specification.

### Architecture

- `docs/architecture/overview.md` — modular-monolith boundaries.
- `docs/architecture/data-and-artifact-model.md` — persistence, lineage, artifact principles.
- `docs/architecture/workflow-control.md` — planning, checkpoints, retries, remediation, deferred work, supervisor.
- `docs/architecture/asynchronous-workflow-queue.md` — durable queue graph, leases, approvals, outbox, workers.
- `docs/quality/architecture_policy.yaml` / `docs/quality/architecture-policy.md` — executable/human architecture rules.
- `docs/generated/capability-manifest.md` — source-derived inventory of services, orchestrators, CLI commands, and schemas.

### Workflows/operations

- `docs/workflows/report-acquisition.md` — current acquisition semantics and source identity handoff.
- `docs/workflows/report-processing.md` — report processing behavior.
- `docs/workflows/cross-report-analysis.md` — Briefing/cross-report workflow and no-normalization rule.
- `docs/workflows/publishing.md` — publish readiness, WordPress publishing, readback, approvals.
- `docs/ops/recovery.md` — queue/remediation/deferred-work recovery.
- `docs/ops/budget_authority_coverage.md` — current budget-authority coverage.
- `docs/ops/wordpress.md` — WordPress operations/deployment.
- `README_WORDPRESS.md` — current WordPress front-end contract and verification.

### Quality/evidence

- `docs/quality/testing.md` — testing and live-validation policy.
- `docs/quality/release-gates.md` — release gate definitions.
- `docs/quality/evidence.md` and `docs/CTO_evidence/` — retained completion/release evidence model.
- `docs/quality/logical-error-analysis-2026-08-01.md` — latest reviewed logical-error analysis at snapshot time.
- Retained crop/PDF/claim fixture corpora under `tests/fixtures/` — regression baselines.

### Browser runtime

- `tools/browser-use/` — vendored Browser Use reference/runtime source. It is not the canonical MarketLense workflow documentation; the MarketLense service boundary remains canonical.

## 16. Important Notion artifacts

Notion is the human product/strategy/runbook workspace. The most relevant pages are:

- **Market lense** — canonical workspace homepage/index.
- **01 — Project Charter and Final Goal** — product purpose, navigation, enterprise target state.
- **02 — Onboarding Guide** — contributor onboarding.
- **03 — Operating Runbook** — ingest/publish/source/cross-report operations.
- **04 — Product and Editorial Standard** — editorial acceptance and anti-patterns.
- **05 — Architecture and Engineering Constitution** — human architecture rules/rationale.
- **06 — Report Pipeline Documentation** — report lifecycle details.
- **07 — WordPress Portal Documentation** — portal IA and boundaries.
- **08 — Source and Publisher Management** — Publisher/Source/Report lifecycle distinction.
- **09 — Cross-Report Analysis Documentation** — synthesis model.
- **Signal Treatment Without Metric Normalization** — canonical editorial reasoning for Signals without synthetic metric normalization.
- **10 — Quality Gates and Release Governance** — release/quality controls.
- **11 — Backlog and Roadmap** — human roadmap summary; defer active status to repo TODO.
- **12 — Failure Runbooks** — operational failure procedures.
- **13 — Intelligence Entity and Navigation Model** — canonical entity definitions and public IA.
- **14 — OpenAI Batch API Cost Optimization** — design reference/proposal; not proof of current implementation.
- **15 — External Publisher Discovery Module** — design reference for external-search-first publisher discovery.
- **16 — Latest Repo Alignment Assessment** — **historical July 5 snapshot; implementation status is stale relative to current repo**.
- **17 — Email Acquisition and Deferred Delivery** — mailbox/deferred acquisition design/history.
- **18 — x100 Output Quality Improvements** and related prompt/user-facing/autonomy guides — improvement references, not substitutes for the active backlog.
- **REPORT SOURCES / REPORT DATABASE** — legacy/current planning/source workspaces; operational runtime state belongs in repo-managed SQLite/artifacts, not Notion.

## 17. Project-conversation decisions and recurring owner priorities

Across project discussions, preserve these priorities when choosing between technically valid approaches:

- **Reach a fully autonomous MVP as quickly as possible.** Prefer completing and proving the existing control/queue/publishing path over adding broad new platforms.
- **Improve speed, cost, reliability, and output quality together.** Optimizations should not trade away evidence quality or release safety.
- **Keep the system simple.** Do not engineer elaborate solutions for rare, easily recoverable corner cases.
- **Maximize the quality of public report pages from existing extraction.** Important report evidence, charts, figures, examples, and derivative posting material should not be left unused merely because a thinner template is easier.
- **Cross-report analysis should avoid metric normalization** and should reuse already processed report evidence so historical reports do not need full re-ingestion.
- **Report charts/crops must look professionally selected and cropped.** Extraction quantity is subordinate to usable visual quality.
- **Email retrieval is a first-class acquisition route**, not a manual fallback.
- **Browser workflows are a major optimization target**, but improvements should reuse/adapt proven techniques and preserve the canonical boundary rather than trigger an unnecessary rewrite.
- **Testing/live runs should become faster** through safe parallelism, deterministic reuse, and focused gates without reducing meaningful coverage.
- **WordPress is currently a sandbox deployment.** Its temporary HTTP/hosting constraints should not dictate the final production architecture.
- **Premium/institutional visual design matters.** The public portal should feel like a research/intelligence product, not a generic AI blog.

## 18. Guidance for future AI/Codex/CTO work

Before proposing or implementing a significant change:

1. Read this file, `AGENTS.md`, `CONSOLIDATED_TODO.md`, and the relevant canonical doc pack.
2. Inspect current code/tests/configuration before trusting a Notion status statement or old chat proposal.
3. Classify a request as **current fact**, **committed decision**, **active backlog**, **deferred/excluded**, or **exploratory idea**.
4. Prefer closing an existing active outcome over creating a parallel mechanism.
5. Use persisted evidence/checkpoints/hashes before external calls or regeneration.
6. Keep WordPress render-only for intelligence.
7. Preserve raw metric context; do not normalize across publishers without an explicit new product decision and a defensible normalization capability.
8. Do not publish or expose unvalidated/partial artifacts.
9. Do not add a new service/process/database/broker just to look more scalable; use current SQLite/modular-monolith boundaries until measured evidence says they are insufficient.
10. For optimizations, report the expected and measured effect on latency, provider calls/tokens, cost, failure rate, and output quality where feasible.
11. For public/editorial changes, assess both automated gates and human editorial quality—the latter remains an explicit open acceptance area.
12. Update canonical documentation and the active backlog when a material status changes; do not leave Notion/repo status contradictions unresolved indefinitely.

## 19. Snapshot uncertainties / items requiring external verification

This context intentionally distinguishes confirmed repository state from external operational state. At snapshot time:

- The exact live hosted WordPress rendering/HTTPS/performance state was not revalidated as part of creating this file; use the hosted smoke/performance/canary tasks for that evidence.
- Credentials-dependent live APIs and full provider canaries were not executed for this documentation-only synthesis.
- Notion's July 5 readiness score should not be reused as a current numerical score.
- The active backlog has not been formally re-audited since July 26 despite Aug 1–4 remediation/CI commits; do not silently mark items closed from inference alone.
- Public Figures, Regions/Time Periods, richer Signal lifecycle, dynamic graph, answer-mode search, Batch API, and similar roadmap ideas should be treated as not-currently-confirmed unless current code/backlog evidence is found.

---

**Maintenance trigger:** update this file when a project-level decision changes, a major capability moves between implemented/active/deferred/excluded, the public entity model changes, the architecture/source-of-truth precedence changes, or a new repository/Notion artifact becomes canonical. Do not turn this file into a release chronology.