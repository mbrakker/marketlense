# Consolidated TODO

Last audited: 2026-09-04
Audit basis: repository `main` at `28ad708f3bc3badf568c5f8e31f8c9d94df52775`, current first-party implementation, WordPress theme/plugin code, and retained hosted-site evidence. Hosted-only completion criteria remain open unless a current deployed smoke/readback proves them; the temporary HTTP sandbox is not treated as a production-hosting defect.

This is the repository's single, source-neutral work register. Every canonical task ID appears once in the Unified Work Register. Historical evidence may explain a closure, but it must not redefine current status.

## How to Use This Backlog

- The Unified Work Register is the canonical status source. `Active` items have current baseline and measurable completion checks below; `Deferred`, `Closed`, and `Excluded` items remain visible in the register.
- Activate work only when the outcome and completion evidence are clear enough to execute. A separate issue/plan, named owner, target date, or review date is optional unless the work itself requires one; do not create process records solely to satisfy the backlog.
- One item owns one outcome. Merge overlapping requests into the existing owner rather than creating parallel tasks.
- Every implementation follows `AGENTS.md`: preserve role boundaries, use typed contracts, avoid placeholders/private-helper patching, and verify behavior at the real boundary.
- Quantitative current-state claims must cite or name retained evidence with an exact producer SHA/date when they are used for release or closure decisions.
- Close an item only when every stated completion check is met. Keep closure evidence concise here and retain detailed artifacts in `docs/quality/`, `docs/CTO_evidence/`, release evidence, or git history.

| Priority | Execution lane | Goal |
| --- | --- | --- |
| 1 | Autonomous safety and cost control | Make unattended runs inspectable, bounded, and recoverable. |
| 2 | Public trust and publishing | Make the public site accurate, safe, responsive, and ready for operator review. |
| 3 | Evidence quality and reuse | Turn retained evidence, embeddings, lineage, and crop QA into measurable decisions. |
| 4 | Release integrity | Make release evidence and architecture enforcement visible and reliable. |
| 5 | Boundary simplification | Reduce real control-plane and service complexity without behavior drift. |

## Unified Work Register

| Status | ID | Work item | Current outcome / merge target |
| --- | --- | --- | --- |
| Closed | A1 | Single autonomous supervisor, read-only `PipelinePlan`, and mandatory workflow-control authority | Plan authorization is enforced by CLI/UI control payloads; retained plan run and regression evidence passed. |
| Closed | A2 | Configured run profiles | Seven typed profiles resolve identically through plan, CLI, and UI. |
| Closed | A3 | Workflow-wide remediation-ledger rollout | The 31-workflow coverage matrix, bounded fail-closed reaper, read-only soak, and strict retained evidence passed. |
| Closed | A4 | Quarantine irreparably malformed Drive PDFs | `pdf-integrity-v1`, durable quarantine, and retained-file revalidation are implemented. |
| Closed | A5 | Terminal blocker and avoided-browser-spend route policy | Proven terminal blockers stop unnecessary browser escalation and retain avoided-work evidence. |
| Closed | A6 | Budget-manager closeout and operational proof | Live governed Drive/vector/LLM calls recorded actual use and subsequent calls were stopped before provider I/O at budget limits. |
| Closed | A7 | Budget-aware model routing, compaction, and failure-class fallback | Explicit route policy, anchor-preserving compaction, same-provider fallback, and retained-corpus gates are implemented. |
| Active | A8 | Compare retained model-call replay bundles | Build a deterministic, zero-provider comparison outcome for retained replay bundles. |
| Closed | A9 | Canonical report-source identity and publication provenance | Immutable source observations, deterministic resolution, safe projection, and render-only invalidation are implemented. |
| Closed | A10 | Budget-deferred-work recovery and operator requeue | Three proof-bound recovery adapters are enabled; unsupported work remains held. |
| Closed | A11 | Ledger-driven recurring-failure prevention and operator prioritization | Deterministic remediation-opportunity grouping exists and unregistered execution remains held. |
| Closed | A12 | Complete configured model-pricing coverage for spend budgets | Versioned approved pricing, cached-input billing, attribution, and hold-before-I/O behavior are implemented. |
| Closed | A13 | Former recovery/backlog source item | Historical recovery ownership was merged into A10; backlog-source integrity is enforced separately by CI tests. |
| Closed | A14 | Build retained route-economics calibration and proposal tooling | Read-only compatible-cohort route economics and thresholded operator proposals/abstentions are implemented; A19 owns mechanism-level telemetry improvements. |
| Active | A15 | Complete explicit model-policy coverage and policy-effectiveness evidence | Retire remaining compatibility fallback and retain decision-useful compatible evidence. |
| Closed | A16 | Durable corpus rehabilitation campaign execution | Review-gated retained-evidence campaigns enqueue idempotent repair work without public writes. |
| Active | A17 | Calibrate deterministic admission thresholds from retained preflight funnels | Produce read-only compatible-cohort threshold proposals without automatic admission changes. |
| Active | A18 | Harden discovery recall and authoritative acquisition handoff | Establish ground-truth recall, reversible candidate state, executable recovery, and a lossless authoritative qualification handoff. |
| Active | A19 | Harden acquisition routes, terminal semantics, and artifact verification | Make every route converge on consistent verified-artifact semantics, correct mailbox/onsite state, bounded recovery, and mechanism-level economics. |
| Closed | P0 | Public editorial remediation and sandbox end-to-end baseline | The baseline remediation/publish path was proven on a bounded sandbox cohort; successor public outcomes are owned by P2-P10/P12-P15. |
| Closed | P1 | Publish snapshot naming and synchronous idempotent publishing | Public/UI terminology uses Publish Readiness; synchronous review-gated idempotent publishing is preserved. |
| Active | P2 | Harden bounded WordPress public-observability events | Define and enforce a bounded/redacted PHP event contract for intake and public-render boundaries; R6 owns aggregate reduction telemetry. |
| Deferred | P3 | Production HTTPS and canonical transport | Activate with production-host migration. Current sandbox HTTP is intentional; do not spend MVP effort retrofitting temporary hosting. |
| Active | P4 | Close public briefing, correction, and submission intake | WordPress-native intake exists; close with P2-compliant events and current hosted smoke of validation, persistence, and confirmation. |
| Active | P5 | Validate and close responsive search and navigation | Mobile navigation/search/filter implementation exists; remaining work is hosted visual/accessibility verification and regression evidence. |
| Active | P6 | Complete blind human editorial acceptance | Automated readiness is implemented; close against the retained multi-batch human-review protocol rather than a superseded 30×3 rubric. |
| Active | P7 | Fix public performance measurement and reach hosted targets | Correct the measurement contract first, then optimize against explicit targets without metadata/content regression. |
| Active | P8 | Complete concise public evidence, methodology, and related-content surfaces | Public evidence/discovery outcome. |
| Closed | P9 | Retained public-advisory benchmark | Saved baseline comparison and grounded repair proposal/abstention output are implemented. |
| Active | P10 | Operate correlated public-render failure telemetry | Hosted aggregation/alerting outcome; safe render boundary itself is implemented. |
| Closed | P11 | Establish verified acquisition-to-ingest file/identity handoff | Canonical retained-file, MD5, source-identity, and idempotent ingest handoff were proven; A19 owns stronger cross-route structural artifact acceptance. |
| Closed | P12 | Release-locked sandbox publish canary | Exact-HEAD isolated three-report cohort published with authenticated readback and zero-write replay. |
| Closed | P13 | Make WordPress file-ID lookup independently authoritative | Authenticated immutable file-ID lookup reuses matching posts, fails closed on ambiguity, and preserves no-write reuse. |
| Closed | P14 | Retain isolated live proof of strict cohort-manifest publication binding | The isolated cohort bound only admitted members and replayed with no WordPress writes. |
| Closed | P15 | Operate canonical publish-readiness telemetry and refresh planning | Typed deterministic refresh plans route only proven minimum recovery work. |
| Closed | E1 | Claim-embedding freshness, retention, and cost controls | Due-work selection, leases, budgets/retries, health telemetry, and live bounded embedding proof are implemented. |
| Closed | E2 | Retained-artifact benchmark | Briefing/Signal prompt-token deltas, overlap/source coverage, and no-vector fallback are measured. |
| Closed | E3 | Lineage-driven minimum regeneration | Deterministic minimum regeneration authority and render-only enforcement are implemented. |
| Closed | E4 | Executable retained PDF benchmark corpus in CI | Retained corpus is hash-pinned and CI-gated. |
| Closed | E5 | Crop-QA scorecards and selection telemetry | Retained crop-QA sidecars support operator-only quality/clipping/storage scorecards. |
| Active | E6 | Retain a hash-pinned claim-embedding benchmark export | Persist approved vectors for reproducible zero-provider semantic benchmarking. |
| Closed | E7 | Planner-enforced artifact-family reuse | Retained render/crop/checkpoint/publication reuse is planner-enforced with plan/actual reconciliation. |
| Closed | E8 | Use canonical source identity to suppress duplicate research work | Exact identity/content-hash package reuse is implemented with retained evidence. |
| Closed | E9 | Materialize prompt-family outputs and route only required model calls | Primary model families use fail-closed pre-call provenance reuse. |
| Active | E10 | Attest active model-pricing rates before they become stale | Keep cost attribution and spend enforcement trustworthy as provider pricing changes. |
| Closed | E11 | Measure and optimize structured-output recovery effectiveness | Fresh isolated cohort retained 100% first-pass structured validity with zero repair cost/tokens while downstream gates remained active. |
| Active | E12 | Persist pre-category editorial context checkpoints | Extend typed recovery to genuinely category-only retries. |
| Active | E13 | Measure candidate-regeneration promotion effectiveness | Compare compatible candidate cohorts and reduce repeated unsuccessful repair spend. |
| Active | E14 | Calibrate category-fit coverage from retained outcomes | Turn retained category-fit decisions into grounded mapping/prompt proposals. |
| Active | R1 | Publish release-evidence reviews where reviewers work | Link exact-tested-HEAD evidence/approval to the PR/release surface and declare runtime-corpus representativeness. |
| Active | R2 | Enforce role boundaries, direct-I/O discipline, and controlled module growth | Close targeted boundary-coverage and expiring-waiver gaps without generic governance noise. |
| Active | R3 | Restore service quality coverage above the retained baseline | Add behavior-focused service coverage and refresh the baseline only from a passing exact-commit run. |
| Closed | R4 | Publication usage/projection reconciliation guard | Missing/invalid/materially lagged usage/projection evidence stops public writes without rebuilding. |
| Closed | R5 | Hash-verified dependency lock artifacts | Native Ubuntu CPython 3.12 wheelhouse and offline hash-locked install are verified. |
| Active | R6 | Review bounded-log reduction telemetry and remediate recurring callers | Aggregate reduction attempts and convert recurring oversized callers into bounded remediation. |
| Closed | S1 | Canonical service-boundary audit | CI-enforced service-boundary audit preserves approved external-effect ownership. |
| Closed | S2 | Publish/ingest facade audit | CI-enforced facade/decomposition coverage preserves routing, retries, state, and external-effect contracts. |
| Active | S3 | Simplify the PDF visual-heuristics boundary | Only address measured remaining coupling behind the canonical PDF boundary. |
| Active | S4 | Give WordPress shortcodes semantic ownership | Split the catch-all shortcode owner into coherent feature families without output/hook changes. |
| Deferred | D1 | Full report-generation DAG scheduler | Revisit only if profiling shows material idle dependency time beyond simple parallelism. |
| Deferred | D2 | Streaming Drive prefetch queue and worker-safe PDF context pooling | Revisit if batches materially wait on Drive while workers are idle. |
| Deferred | D3 | Adaptive concurrency and route-specific worker buffers | Revisit on sustained throttling, SQLite contention, or browser saturation. |
| Deferred | D4 | Multi-provider failover | Revisit when outage volume or an SLA justifies the complexity. |
| Deferred | D5 | Same-publisher warm workers/session reuse | Revisit when same-publisher volume justifies session-isolation risk. |
| Deferred | D6 | Arbitrary generic DAG or due-work scheduler | Typed durable workflow queues own current work; keep a user-configurable generic scheduler deferred. |
| Closed | D7 | Complete queue-backed publication coverage and live recovery proof | Critical publication queues have canonical handlers and retained controlled live evidence. |
| Deferred | D8 | LinkedIn persona variants and comparative positioning | Revisit when an active distribution workflow measures their value. |
| Deferred | D9 | Golden-output prompt evaluation and broader prompt-family scoring | Revisit only when current fixtures fail to detect a measured quality regression. |
| Deferred | D10 | Browser executor/static-DOM/prompt-payload/route-playbook tuning | Revisit only from a measured acquisition gap; A18/A19 own current correctness work. |
| Deferred | D11 | Root pre-commit, declarative quality-gate manifest, stricter mypy/Ruff, and hygiene scorecards | Revisit when current CI evidence proves a specific enforcement gap. |
| Deferred | D12 | Governed staging WordPress publish/projection canary | Revisit when a non-public staging site and named human approver are available. |
| Closed | C1 | Cached-provider accounting reconciliation corpus | Real provider-hit and tamper-rejection fixtures are in the CI accounting path. |
| Closed | C2 | Bounded multimodal crop-QA escalation | Typed escalation generator and deterministic no-model default are implemented/tested. |
| Closed | C3 | Lazy model construction, ranking/crop shortcuts, prefetch, and route prompt improvements | Landed behind existing boundaries with retained regression evidence. |
| Closed | C4 | Capability maps and autonomous release/remediation summaries | Generated capability maps and autonomous smoke evidence exist. |
| Closed | C5 | Prompt partials/schema snippets and prompt fixture regression | Dry-run and corpus validation are implemented. |
| Closed | C6 | Establish baseline discovery/mailbox/signal/embedding persistence paths | Durable baseline paths exist; A18/A19 own discovery/acquisition correctness hardening rather than reopening this capability milestone. |
| Closed | C7 | Logging content-exposure controls | Python structured logging is bounded/redacted; P2 owns WordPress public-boundary events and R6 owns reduction telemetry. |
| Closed | C8 | CTO evidence-collector integrity | Snapshot, exact-HEAD, provenance, consistency, and inventory validation are implemented; R1 owns reviewer-surface/runtime-corpus expansion. |
| Excluded | X1 | Draft HTML published before enrichment | Public progressive enrichment is not permitted. |
| Excluded | X2 | Automatic lower private-API promotion thresholds | Conservative thresholds remain mandatory. |
| Excluded | X3 | Invented acquisition-form identity facts or public pipeline diagnostics | Map only verified identity facts; diagnostics remain operator-only. |

## Active Backlog

The register currently contains **23 Active outcomes**. Their baseline/target below is authoritative; old historical descriptions do not override it.

### A18. Harden discovery recall and authoritative acquisition handoff

- **Baseline:** discovery has route memory, screening, landing verification, coverage regression checks, and recovery records, but early irreversible filtering and raw-snapshot delta semantics can hide false negatives; the durable handoff loses candidate acquisition evidence and acquisition can reclassify already-qualified reports.
- **Target:** discovery is high-recall, reversible, and authoritative for report qualification; acquisition receives the same typed evidence used by direct/audit execution and chooses *how* to acquire rather than re-deciding *whether* the source is a report.
- **Implementation order:**
  1. Retain a hash-pinned discovery gold corpus of roughly 15-20 representative publishers/known report URLs across static, paginated, JS, gated, multilingual, direct-PDF, and external/microsite cases.
  2. Convert the HTTP `0.60` threshold to ranking/triage for plausible candidates; deterministic hard rejection is only for indisputable junk.
  3. Persist candidate lifecycle state (`observed`, `screened`, `qualified`, `acquisition_attempted`, `acquired`) with decision/policy identity and re-screen rules.
  4. Execute deferred recovery through the existing durable queue/remediation boundary or stop labelling non-executable records `scheduled`.
  5. Preserve a typed qualified acquisition context (`canonical_url`, title, candidate PDF URL, source-page URLs, discovery provenance/confidence, route recommendation, qualification/policy identity) through the durable queue.
  6. Require bounded first-run completeness proof before a publisher snapshot becomes the long-lived baseline.
- **Completion evidence:** at least **97% report recall** on the fixed gold corpus with no material precision regression; mixed-delta/policy-change re-screen fixtures; one retained executed recovery; no hard-drop solely for missing English keywords/multilingual/external-host status; discovery-qualified sources reach route planning without the ad-hoc readiness classifier.

### A19. Harden acquisition routes, terminal semantics, and artifact verification

- **Baseline:** acquisition has a strong cheap-to-expensive ladder, deterministic browser/private-API/specialist capabilities, route memory and budgets, but route contracts are inconsistent: mailbox state/watermark semantics, structural verification, onsite non-PDF success, direct-PDF wrapper recovery, mailbox ZIP/link handling, route accounting, cache freshness, and durable archive completion can diverge.
- **Target:** every acquisition mechanism converges on one ingest-compatible verified-artifact definition and accurate terminal/resource semantics while preserving cheap-first routing and bounded provider use.
- **Implementation order:**
  1. Only verified `email_requested` may enqueue mailbox delivery; carry verified submission timing/request identity and split broad access blockers into actionable classes.
  2. Reuse `pdf-integrity-v1` before success/learning/cache/archive/ingest for HTTP, browser, mailbox/ZIP, cache, private-API and specialist PDF outputs. Distinguish local verification, durable archive, and acquisition completion.
  3. Permit one evidence-triggered browser recovery when an apparent direct PDF is actually an HTML/WAF/viewer wrapper; rank opaque/extensionless PDF candidates from DOM/MIME/source evidence before lexical hints.
  4. Gate pre-LLM form side effects on proven report-delivery evidence; keep deterministic playbooks/private APIs ahead of Browser Use where eligible.
  5. Make listing-hub recovery self-healing by persisting the resolved direct detail/download target.
  6. Use one onsite completeness evaluator; HTML/Markdown remain support artifacts while ingest is PDF-only; label Adobe text-only output explicitly and bound Issuu memory/concurrency.
  7. Make mailbox acquisition metadata-first, ZIP-bounded, candidate-specific in suppression, and capable of bounded fallback to lower-ranked valid links.
  8. Persist mechanism-level route/resource accounting (`planned_route_family`, `resolution_method`, route kind/outcome, browser/Agent/mailbox use, latency, cost/resources) for A14.
  9. Reserve budgets for actual HTTP/browser/model/form/mailbox/PDF/Drive side effects rather than one generic PDF-processing reservation.
- **Completion evidence:** old mail cannot satisfy a new request; `email_required` never polls; shared structural verifier rejects malformed PDFs on every route; onsite success produces a verified PDF; wrapper-PDF browser fallback is bounded; unrelated forms cannot be auto-submitted; listing-hub next run is direct; ZIP bombs/oversized archives are bounded; mechanism-level economics are retained; mutable cache freshness changes invalidate reuse; required archive failure remains recoverable pre-completion; route-specific budget tests match actual side effects.

### Remaining Active Outcomes

| ID | Current baseline | Target / completion proof |
| --- | --- | --- |
| A8 | Replay bundles exist; comparison is manual. | Deterministic bounded comparison of schema/prompt/evidence/output identities, including equivalent/changed/missing/malformed cases, with zero provider calls by default. |
| A15 | Production namespace inventory and `policy-effectiveness` exist; compatibility fallback/evidence gaps remain. | No reachable production namespace uses compatibility fallback; compatible retained/live cohorts report calls, validity, reuse, latency, tokens/cost and produce reviewable conclusions without autonomous policy changes. |
| A17 | Versioned admission decisions exist; no compatible-cohort calibration outcome. | Read-only funnel/counterfactual proposals gated by minimum sample/confidence; incompatible versions excluded; zero model/vector/external writes. |
| P2 | Python structured logging is bounded, but WordPress intake/render events are direct PHP JSON/error-log events with different semantics. | One WordPress-local bounded/redacted public-event contract; tests prove correlation/outcome survive while user text, paths, stack content and discarded values do not; R6 receives only bounded reduction metadata. |
| P4 | Briefing/correction/submission forms persist private WordPress records with nonce/honeypot/validation. | Use the P2-governed WordPress event contract; current hosted smoke proves each CTA, validation, spam/empty rejection, successful persistence, and confirmation/error state. |
| P5 | Mobile nav, header search, archive filters and responsive CSS exist. | Current hosted screenshots at phone/tablet/desktop show no overflow/clipping/overlap; keyboard/focus/open-close behavior is accessible across homepage, search, archive, detail, contact and submit. |
| P6 | Automated publish-readiness is strong; retained five-report human batches use a 10-point editorial matrix and some review fields remain incomplete. | Complete **three fixed five-report representative cohorts** with human reviewer attribution using the stable 10-point rubric (factual fidelity, evidence selection, analytical depth, specificity, commercial relevance, narrative structure, clarity, expert/human feel, completeness; LinkedIn separately; charts/tables excluded until their subproject). Close when all 15 have completed human decisions, aggregate weighted median is at least **85/100**, and no factual-fidelity score is below **8/10** without an explicit retained appeal/outlier disposition. |
| P7 | `public_site_seo_performance.py` currently times HTTP fetch/parse/resource HEAD probes as `dom_complete_ms` and gates on YAML `baseline`, while the YAML `target` is not the pass criterion. | First make metrics truthful: use real browser navigation timing for DOM/load metrics or rename the HTTP probe; baseline remains regression ceiling and target attainment is reported separately. Refresh the baseline review date only from a current hosted measurement. Then improve all seven public routes toward YAML targets without increasing page weight/request count or losing canonical/social/archive contracts. |
| P8 | Safe public projections exist; concise evidence/limitations/related-content contract remains incomplete. | Approved source/publisher/page/excerpt/limitation/original-link support; concise methodology; deterministic related report/briefing/topic/publisher links; fail closed/redact when approved data is absent. |
| P10 | Safe public render boundary and correlation IDs exist; hosted aggregation/alerting does not. | Hosted release evidence aggregates bounded failure counts/correlation IDs and distinguishes zero/expected-injected/unexpected failures without exposing private diagnostics. |
| E6 | A/B script deliberately does not retain vectors, so fixed-corpus semantic ranking cannot run provider-free. | Hash-pinned retention-governed export of approved vector IDs/content hashes/vectors; CI benchmark compares semantic coverage to lexical fallback with zero provider calls. |
| E10 | Cost routes fail closed on missing/stale/held rates; review/transition remains manual. | Read-only active/expiring/stale/held/missing rate check plus explicitly reviewed before/after rate-card transition; unknown/expired/held routes cannot bypass spend authority. |
| E12 | Taxonomy/evidence context is materialized within one pre-category execution boundary. | Versioned lineage-validated pre-category checkpoint; category-only recovery makes no source/vector/taxonomy/evidence provider call and records avoided tokens/cost. |
| E13 | Candidate audits retain promotion/rollback/lineage metadata; compatible-cohort effectiveness view is missing. | Read-only compatible cohort by repair target/issue/schema/policy/prompt with promotion/rollback, attempts, lineage failures, latency/tokens/cost; show at least one reviewable reduction in repeated failed repair work or improved promotion rate. |
| E14 | Category decisions retain deterministic/model outcomes but no operator cohort scorecard. | Read-only compatible-cohort selection/rescue/repair/latency/token/cost scorecard and bounded mapping/prompt proposals; demonstrate increased grounded coverage or reduced unnecessary repairs without automatic taxonomy changes. |
| R1 | CI creates bounded release review/job summary and archives evidence. | PR/release surface links exact-tested-HEAD bundle and final approval; runtime corpus carries declared representativeness; mismatch/unavailable/unwaived cases remain visible. |
| R2 | CI already enforces core architecture/import/I/O/policy rules. | Targeted missing service-boundary evidence fails unless covered by narrow owner/reason/expiry waiver; tests prove expiry and valid exceptions without adding broad governance noise. |
| R3 | Retained service coverage is 82.5763% with enforced 75% floor. | Behavior tests prioritize stateful/external failure paths; refresh the retained baseline only from passing exact-commit full CI with no regression in global/generator/orchestrator coverage. |
| R6 | `log_payload_reduced` exists; operator aggregation does not. | Release evidence groups count/module/event/attempted-size percentiles with zero-content samples; thresholded recurring callers get ownership/remediation without reconstructing discarded content. |
| S3 | PDF visual families are already decomposed behind compatibility facades. | Change only a measured remaining coupling; preserve canonical PDF external/library boundary, candidate/crop outputs, paths, cache semantics and benchmark signatures. |
| S4 | One shortcode class owns several unrelated public semantics. | Extract coherent shortcode families behind compatibility registration; public hooks/output remain unchanged and PHP/runtime tests cover each surface. |

## Deferred Work

Deferred means **not an MVP blocker under current evidence**. In particular, P3 is intentionally tied to production-host migration rather than the temporary HTTP sandbox. D10 remains deferred because A18/A19 own current browser/acquisition correctness and no separate tuning program should compete with them.

## Recently Closed / Retained Evidence

The Unified Work Register is the status authority. Detailed historical narratives are intentionally not duplicated here because they became stale and contradictory. Retained proof remains in `docs/quality/`, `docs/CTO_evidence/`, release evidence, and git history. Recent/high-value closure references include:

- **E11:** [`docs/quality/e11-structured-output-recovery-evidence-2026-08-28.md`](docs/quality/e11-structured-output-recovery-evidence-2026-08-28.md).
- **E9:** [`docs/quality/e9-prompt-family-reuse-evidence-2026-08-27.md`](docs/quality/e9-prompt-family-reuse-evidence-2026-08-27.md).
- **E8:** [`docs/quality/e8-source-reuse-evidence-2026-08-28.md`](docs/quality/e8-source-reuse-evidence-2026-08-28.md).
- **P12/P14:** [`docs/CTO_evidence/p12_p14_exact_head_canary_20260827.json`](docs/CTO_evidence/p12_p14_exact_head_canary_20260827.json).
- **P6 human-review evidence:** [`docs/quality/p6-editorial-acceptance.md`](docs/quality/p6-editorial-acceptance.md) remains Active evidence, not closure evidence.

## Guardrails

- Never normalize cross-publisher metrics with incompatible definitions, geography, methodology, or time period.
- Never publish incomplete public pages for later enrichment; preview/draft is allowed only outside the public release surface.
- Never invent identity attributes for acquisition forms; map only configured, verified values.
- Never lower private-API promotion thresholds automatically.
- Never publish OCR, model, crop, vector, validation, filesystem, stack-trace, or other operator diagnostics as public product content.
- WordPress remains a rendering/publication boundary for intelligence; do not move report intelligence generation into the theme/plugin.

### Non-negotiable publishing guardrail

Automation may plan, resume, retry, repair, validate, render, draft, hold, and notify. It must not public-auto-publish until retained evidence demonstrates safe claims, no internal-ID leakage, stable crop acceptance, stable WordPress updates, duplicate suppression, rollback, and consistent editorial quality.

## Current-State Evidence

- Canonical workflow-control, budgets, recovery, model-policy routing, source identity, artifact lineage, publish readiness, and idempotent WordPress publication boundaries are implemented with retained evidence.
- WordPress currently has baseline public render safety, private intake persistence, responsive navigation/search/filter implementation, and authenticated draft/readback support. P2/P4/P5/P10 own deployed operational proof rather than missing baseline implementation.
- `sync-wordpress-intelligence` has retained evidence for **64 public content entities** — 47 reports, 5 briefings, and 12 signals — **plus 29 publishers**. Do not describe that as 64 total entities.
- HTTPS on the temporary sandbox is intentionally deferred to production-host migration under P3; it is not counted as an autonomous-MVP implementation blocker.
- P6 is an editorial human-acceptance outcome, not an automated-gate implementation gap.
- P7 is not closeable until its measurement semantics distinguish HTTP probe timing from real browser DOM/load timing and report baseline regression separately from target attainment.
- CI covers formatting, typing, architecture/import checks, forbidden patching, hygiene, coverage, mutation, prompt regression, release-evidence archival, PDF candidate/crop/trend gates, public report-quality gates, and WordPress staging verification when configured.

## Audit Notes

- Full backlog/code/WordPress reconciliation performed on 2026-09-04 against exact repository HEAD `28ad708f3bc3badf568c5f8e31f8c9d94df52775`.
- The prior register reported 30 Active outcomes while containing 24 Active rows. P3 is now correctly Deferred for production-host migration, leaving **23 Active outcomes**.
- Historical canonical IDs that previously existed only in closure prose/context are restored to the Unified Work Register: A5, A12, A13, P0, P9, P11, E1, E2, E5, E7, R4, S1, S2, and D10.
- The obsolete statement that closed A3/A6 remained Active has been removed; E3 no longer delegates current work to already-closed E7.
- C6, P11, and A14 closure wording is narrowed to the capability/tooling actually proven so A18/A19 can own current production-hardening work without contradiction.
- Public-site states now distinguish implemented-but-unverified outcomes from missing implementation, and intentional sandbox HTTP from production transport requirements.
