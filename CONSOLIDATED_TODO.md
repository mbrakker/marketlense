# Consolidated TODO — canonical MarketLense backlog

**Last structural consolidation:** 2026-10-11. **Status baseline:** 2026-10-08, as recorded in the archived register; D13 was added as a deferred P2 follow-up on 2026-10-11 (neither date implies a new source, deployment, test, or cohort audit). **Consolidation source HEAD:** `b0f1249f014c270dfd85fa6d7fad9cf71035cb90`. **E17 scope added:** 2026-10-11 based on code inspection and the retained 2026-10-06 provider profile; no new report execution is implied. **E18 scope added:** 2026-10-11 as an unverified four-stage stability proposal; no new model run or quality result is implied.

This is the **single authoritative status and outcome register**. The five [workstream specifications](docs/backlog/) contain full implementation and Luna guidance, and the [technical proposal index](docs/backlog/proposal-index.md) maps all proposals to one existing owner. Full unchanged backups: [original backlog](docs/backlog/archive/CONSOLIDATED_TODO-20261011-preconsolidation.md) and [original 100-improvement catalogue](docs/backlog/archive/10improvements-20261011-preconsolidation.md). The root [10improvements.md](10improvements.md) is now a compatibility pointer, not a competing backlog.

## Operating rules

- Every canonical ID appears **once** below; only this register determines `Active`, `Closed`, `Deferred`, or `Excluded`. Current status must never be inferred from a technical proposal.
- Every Active ID has exactly one owner specification and its own **Luna prompt**, baseline, implementation sequence and outcome-level acceptance. Implement one verified slice at a time; the linked technical prompts are not permission to reopen closed outcomes or broaden scope.
- Before changes, inspect current HEAD, source boundaries, contracts, relevant `AGENTS.md`, and retained evidence; historical hypotheses and dates must not be presented as fresh verification.
- Evidence for closure belongs in existing `docs/quality/`, `docs/CTO_evidence/` or git history and must name the exact producer SHA/cohort. Do not mark an outcome Closed because one technical slice landed.
- Prefer root-cause fixes and reuse over extra abstractions or validators. Preserve quality, provenance, bounds, safety and publication approval. Follow global `AGENTS.md` for all implementations.

## Execution focus

The register's five workstreams remain the prioritisation lanes, **not** a newly audited ranking. Initial decisions should be evidence-driven: A21 first-attempt reliability, A18/A19 discovery and verified acquisition, E15 semantic crop acceptance, P6 human editorial acceptance, E16 methodology/applicability, and P16/P17 decision-grade composition. Confirm the actual blocker and applicable prerequisites on current HEAD before selecting a slice. No technical proposal is automatically authorised or considered incomplete merely by appearing in the index. E17 is a separately prioritised P1 token/cache-economics outcome: implement its measurement slice first, while preserving the higher-priority correctness and autonomous-MVP gates. E18 is a P1 first-pass analytical-stability outcome: diagnose repeated-run and fixed-input validator variation before authorising its subsequent behavioral stages; reuse A21/E13/E16/P17 evidence and owners.

| Workstream | Owning specification |
| --- | --- |
| Autonomy / reliability | [A outcomes](docs/backlog/A-autonomy.md) |
| Publishing / editorial | [P outcomes](docs/backlog/P-publication.md) |
| Evidence / analytics | [E outcomes](docs/backlog/E-evidence.md) |
| Engineering / release | [R outcomes](docs/backlog/R-engineering.md) |
| Simplification | [S outcomes](docs/backlog/S-simplification.md) |

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
| Active | A8 | [Compare retained model-call replay bundles](docs/backlog/A-autonomy.md#a8-compare-retained-model-call-replay-bundles) | Build a deterministic, zero-provider comparison outcome for retained replay bundles. |
| Closed | A9 | Canonical report-source identity and publication provenance | Immutable source observations, deterministic resolution, safe projection, and render-only invalidation are implemented. |
| Closed | A10 | Budget-deferred-work recovery and operator requeue | Three proof-bound recovery adapters are enabled; unsupported work remains held. |
| Closed | A11 | Ledger-driven recurring-failure prevention and operator prioritization | Deterministic remediation-opportunity grouping exists and unregistered execution remains held. |
| Closed | A12 | Complete configured model-pricing coverage for spend budgets | Versioned approved pricing, cached-input billing, attribution, and hold-before-I/O behavior are implemented. |
| Closed | A13 | Former recovery/backlog source item | Historical recovery ownership was merged into A10; backlog-source integrity is enforced separately by CI tests. |
| Closed | A14 | Build retained route-economics calibration and proposal tooling | Read-only compatible-cohort route economics and thresholded operator proposals/abstentions are implemented; A19 owns mechanism-level telemetry improvements. |
| Active | A15 | [Complete explicit model-policy coverage and policy-effectiveness evidence](docs/backlog/A-autonomy.md#a15-complete-explicit-model-policy-coverage-and-policy-effectiveness-evidence) | Prove fallback reachability, remove live compatibility-default calls and extend existing effectiveness evidence. |
| Closed | A16 | Durable corpus rehabilitation campaign execution | Review-gated retained-evidence campaigns enqueue idempotent repair work without public writes. |
| Active | A17 | [Calibrate deterministic admission thresholds from retained preflight funnels](docs/backlog/A-autonomy.md#a17-calibrate-deterministic-admission-thresholds-from-retained-preflight-funnels) | Produce read-only compatible-cohort threshold proposals without automatic admission changes. |
| Active | A18 | [Harden discovery recall and authoritative acquisition handoff](docs/backlog/A-autonomy.md#a18-harden-discovery-recall-and-authoritative-acquisition-handoff) | Establish ground-truth recall, reversible candidate state, executable recovery, and a lossless authoritative qualification handoff. |
| Active | A19 | [Harden acquisition routes, terminal semantics, and artifact verification](docs/backlog/A-autonomy.md#a19-harden-acquisition-routes-terminal-semantics-and-artifact-verification) | ZIP limits and read-only UID-based IMAP identity have scoped fixes; cross-route verified-artifact semantics, truthful form/mail state and economics still require proof. |
| Active | A20 | [Prove clean-room capability readiness before first external work](docs/backlog/A-autonomy.md#a20-prove-clean-room-capability-readiness-before-first-external-work) | Turn profile intent into a complete, redacted capability/dependency proof with exact remediation before any costly or mutating operation. |
| Active | A21 | [Establish a representative first-attempt end-to-end reliability SLO](docs/backlog/A-autonomy.md#a21-establish-a-representative-first-attempt-end-to-end-reliability-slo) | Recent validation, cache, queue/outbox and Signal integrity fixes require one current-HEAD first-attempt cohort and sandbox replay; opt-in auto-approval also requires release-safety reconciliation. |
| Closed | P0 | Public editorial remediation and sandbox end-to-end baseline | The baseline remediation/publish path was proven on a bounded sandbox cohort; successor public outcomes are owned by P2-P10/P12-P15. |
| Closed | P1 | Publish snapshot naming and synchronous idempotent publishing | Public/UI terminology uses Publish Readiness; synchronous review-gated idempotent publishing is preserved. |
| Active | P2 | [Harden bounded WordPress public-observability events](docs/backlog/P-publication.md#p2-harden-bounded-wordpress-public-observability-events) | Define and enforce a bounded/redacted PHP event contract for intake and public-render boundaries; R6 owns aggregate reduction telemetry. |
| Deferred | P3 | Production HTTPS and canonical transport | Activate with production-host migration. Current sandbox HTTP is intentional; do not spend MVP effort retrofitting temporary hosting. |
| Active | P4 | [Close public briefing, correction, and submission intake](docs/backlog/P-publication.md#p4-close-public-briefing-correction-and-submission-intake) | WordPress-native intake exists; close with P2-compliant events and current hosted smoke of validation, persistence, and confirmation. |
| Active | P5 | [Validate and close responsive search and navigation](docs/backlog/P-publication.md#p5-validate-and-close-responsive-search-and-navigation) | Mobile navigation/search/filter implementation exists; remaining work is hosted visual/accessibility verification and regression evidence. |
| Active | P6 | [Complete blind human editorial acceptance](docs/backlog/P-publication.md#p6-complete-blind-human-editorial-acceptance) | Automated readiness is implemented; close against the retained multi-batch human-review protocol rather than a superseded 30×3 rubric. |
| Active | P7 | [Fix public performance measurement and reach hosted targets](docs/backlog/P-publication.md#p7-fix-public-performance-measurement-and-reach-hosted-targets) | Correct the measurement contract first, then optimize against explicit targets without metadata/content regression. |
| Active | P8 | [Complete concise public evidence, methodology, and related-content surfaces](docs/backlog/P-publication.md#p8-complete-concise-public-evidence-methodology-and-related-content-surfaces) | Public evidence/discovery outcome. |
| Closed | P9 | Retained public-advisory benchmark | Saved baseline comparison and grounded repair proposal/abstention output are implemented. |
| Active | P10 | [Operate correlated public-render failure telemetry](docs/backlog/P-publication.md#p10-operate-correlated-public-render-failure-telemetry) | Hosted aggregation/alerting outcome; safe render boundary itself is implemented. |
| Closed | P11 | Establish verified acquisition-to-ingest file/identity handoff | Canonical retained-file, MD5, source-identity, and idempotent ingest handoff were proven; A19 owns stronger cross-route structural artifact acceptance. |
| Closed | P12 | Release-locked sandbox publish canary | Historical isolated three-report canary at release SHA `6999c85f69fdf9ac23780b1abff0b06adf1c4979` retained authenticated readback and zero-write replay; not proof for later HEADs. |
| Closed | P13 | Make WordPress file-ID lookup independently authoritative | Authenticated immutable file-ID lookup reuses matching posts, fails closed on ambiguity, and preserves no-write reuse. |
| Closed | P14 | Retain isolated live proof of strict cohort-manifest publication binding | The recorded isolated release cohort bound only admitted members and replayed without WordPress writes; later releases require separate proof. |
| Closed | P15 | Operate canonical publish-readiness telemetry and refresh planning | Typed deterministic refresh plans route only proven minimum recovery work. |
| Active | P16 | [Build a decision-grade consulting synthesis artifact](docs/backlog/P-publication.md#p16-build-a-decision-grade-consulting-synthesis-artifact) | Create one evidence-bound decision model that makes implications, options, trade-offs, risks, unknowns, and conditional actions coherent across public surfaces. |
| Active | P17 | [Compose adaptive, non-repetitive visual report stories](docs/backlog/P-publication.md#p17-compose-adaptive-non-repetitive-visual-report-stories) | Replace one fixed content sequence with a bounded composition plan that gives each source a clear narrative and uses only E15-approved visuals. |
| Closed | E1 | Claim-embedding freshness, retention, and cost controls | Due-work selection, leases, budgets/retries, health telemetry, and live bounded embedding proof are implemented. |
| Closed | E2 | Retained-artifact benchmark | Briefing/Signal prompt-token deltas, overlap/source coverage, and no-vector fallback are measured. |
| Closed | E3 | Lineage-driven minimum regeneration | Deterministic minimum regeneration authority and render-only enforcement are implemented. |
| Closed | E4 | Executable retained PDF benchmark corpus in CI | Hash-pinned deterministic regression corpus is CI-gated; E15 owns independent human semantic crop acceptance. |
| Closed | E5 | Crop-QA scorecards and selection telemetry | Retained crop-QA sidecars support operator-only quality/clipping/storage scorecards. |
| Active | E6 | [Retain a hash-pinned claim-embedding benchmark export](docs/backlog/E-evidence.md#e6-retain-a-hash-pinned-claim-embedding-benchmark-export) | Persist approved vectors for reproducible zero-provider semantic benchmarking. |
| Closed | E7 | Planner-enforced artifact-family reuse | Retained render/crop/checkpoint/publication reuse is planner-enforced with plan/actual reconciliation; report-card replay checks content/source/region/style identity and all three assets before reuse. |
| Closed | E8 | Use canonical source identity to suppress duplicate research work | Exact identity/content-hash package reuse is implemented with retained evidence. |
| Closed | E9 | Materialize prompt-family outputs and route only required model calls | Registered-family pre-call reuse includes editorial-plan identity repair; complete small quote-candidate pools materialize deterministically without a model call, incomplete pools are held, and ambiguous or larger pools retain semantic selection. A21 owns broader interruption/first-attempt proof and E12 category-only checkpoints. |
| Active | E10 | [Attest active model-pricing rates before they become stale](docs/backlog/E-evidence.md#e10-attest-active-model-pricing-rates-before-they-become-stale) | Keep cost attribution and spend enforcement trustworthy as provider pricing changes. |
| Closed | E11 | Measure and optimize structured-output recovery effectiveness | Historical isolated three-report cohort retained 100% first-pass structured validity, zero repair cost/tokens and active downstream gates; not universal current semantic/editorial success. |
| Active | E12 | [Persist pre-category editorial context checkpoints](docs/backlog/E-evidence.md#e12-persist-pre-category-editorial-context-checkpoints) | Extend typed recovery to genuinely category-only retries. |
| Active | E13 | [Measure candidate-regeneration promotion effectiveness](docs/backlog/E-evidence.md#e13-measure-candidate-regeneration-promotion-effectiveness) | Atomic/adaptive foundations exist; prove strict frozen-corpus effectiveness, scope/evidence safety and complete compatible attribution. |
| Active | E14 | [Calibrate category-fit coverage from retained outcomes](docs/backlog/E-evidence.md#e14-calibrate-category-fit-coverage-from-retained-outcomes) | Turn retained category-fit decisions into grounded mapping/prompt proposals. |
| Active | E15 | [Make publication crops visually complete and repairable](docs/backlog/E-evidence.md#e15-make-publication-crops-visually-complete-and-repairable) | Affine coordinate and invalid-bbox guards have scoped fixes; semantic completeness, directional repair, publication-DPI consistency and human-labelled production acceptance remain unproved. |
| Active | E16 | [Make methodology, applicability, and uncertainty decision-grade](docs/backlog/E-evidence.md#e16-make-methodology-applicability-and-uncertainty-decision-grade) | Convert loose methods/limitations text into source-linked evidence-strength facts that constrain claims and support executive interpretation. |
| Active | E17 | [Reduce LLM input, output, and cache cost without quality regression](docs/backlog/E-evidence.md#e17-reduce-llm-input-output-and-cache-cost-without-quality-regression) | Stage measurement, grounding response efficiency, source-preserving prompt projections, provider-cache policy and evidence-gated consolidation; prove lower total cost without quality/reliability regression on frozen five reports. |
| Active | E18 | [Stabilize LLM report analysis and first-pass validation](docs/backlog/E-evidence.md#e18-stabilize-llm-report-analysis-and-first-pass-validation) | Four sequential stages: pin repeated-generation and fixed-input validator baseline; address proven factual drift; stabilize insight selection; fix proven semantic-verdict/repair instability and verify frozen-five quality, first-pass readiness, speed and cost. |
| Active | R1 | [Publish release-evidence reviews where reviewers work](docs/backlog/R-engineering.md#r1-publish-release-evidence-reviews-where-reviewers-work) | Link exact-tested-HEAD evidence/approval to the PR/release surface and declare runtime-corpus representativeness. |
| Active | R2 | [Enforce role boundaries, direct-I/O discipline, and controlled module growth](docs/backlog/R-engineering.md#r2-enforce-role-boundaries-direct-io-discipline-and-controlled-module-growth) | Close targeted boundary-coverage and expiring-waiver gaps without generic governance noise. |
| Active | R3 | [Restore service quality coverage above the retained baseline](docs/backlog/R-engineering.md#r3-restore-service-quality-coverage-above-the-retained-baseline) | Add behavior-focused service coverage and refresh the baseline only from a passing exact-commit run. |
| Closed | R4 | Publication usage/projection reconciliation guard | Missing/invalid/materially lagged usage/projection evidence stops public writes without rebuilding. |
| Closed | R5 | Hash-verified dependency lock artifacts | Native Ubuntu CPython 3.12 wheelhouse and offline hash-locked install are verified. |
| Active | R6 | [Review bounded-log reduction telemetry and remediate recurring callers](docs/backlog/R-engineering.md#r6-review-bounded-log-reduction-telemetry-and-remediate-recurring-callers) | Aggregate reduction attempts and convert recurring oversized callers into bounded remediation. |
| Active | R7 | [Prove recoverable backups and full-state disaster restoration](docs/backlog/R-engineering.md#r7-prove-recoverable-backups-and-full-state-disaster-restoration) | Back up the mutually dependent stores/artifacts consistently and prove isolated restoration, integrity, lineage, and safe resume against explicit recovery objectives. |
| Closed | S1 | Canonical service-boundary audit | CI-enforced service-boundary audit preserves approved external-effect ownership. |
| Closed | S2 | Publish/ingest facade audit | CI-enforced facade/decomposition coverage preserves routing, retries, state, and external-effect contracts. |
| Active | S3 | [Simplify the PDF visual-heuristics boundary](docs/backlog/S-simplification.md#s3-simplify-the-pdf-visual-heuristics-boundary) | Only address measured remaining coupling behind the canonical PDF boundary. |
| Active | S4 | [Give WordPress shortcodes semantic ownership](docs/backlog/S-simplification.md#s4-give-wordpress-shortcodes-semantic-ownership) | Split the catch-all shortcode owner into coherent feature families without output/hook changes. |
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
| Deferred | D13 | [Evaluate direct OpenAI Responses migration](docs/backlog/R-engineering.md#d13-openai-responses-migration) | P2: selectively A/B direct OpenAI text/JSON generation against current Chat Completions on the frozen five-report cohort; migrate only with non-regressing quality/reliability and demonstrated overall benefit. Keep OpenRouter; test reasoning-context reuse separately. |
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

**Register counts:** 31 Active, 44 Closed, 13 Deferred, 3 Excluded (91 total). The 2026-10-08 baseline contained 89 items; D13 (Deferred) and E17 (Active) were added on 2026-10-11. E17 is an optimisation plan grounded in inspected code and historical provider profiles, **not** a completed implementation, new cohort audit, or verified savings.


## Active Backlog

Navigation-only sections for compatibility with existing backlog-source checks. Full implementation and acceptance criteria live in linked workstream specifications. Status authority remains the Unified Work Register.

#### A8. Compare retained model-call replay bundles

[Full A8 specification](docs/backlog/A-autonomy.md#a8-compare-retained-model-call-replay-bundles).

#### A15. Complete explicit model-policy coverage and policy-effectiveness evidence

[Full A15 specification](docs/backlog/A-autonomy.md#a15-complete-explicit-model-policy-coverage-and-policy-effectiveness-evidence).

#### A17. Calibrate deterministic admission thresholds from retained preflight funnels

[Full A17 specification](docs/backlog/A-autonomy.md#a17-calibrate-deterministic-admission-thresholds-from-retained-preflight-funnels).

#### A18. Harden discovery recall and authoritative acquisition handoff

[Full A18 specification](docs/backlog/A-autonomy.md#a18-harden-discovery-recall-and-authoritative-acquisition-handoff).

#### A19. Harden acquisition routes, terminal semantics, and artifact verification

[Full A19 specification](docs/backlog/A-autonomy.md#a19-harden-acquisition-routes-terminal-semantics-and-artifact-verification).

#### A20. Prove clean-room capability readiness before first external work

[Full A20 specification](docs/backlog/A-autonomy.md#a20-prove-clean-room-capability-readiness-before-first-external-work).

#### A21. Establish a representative first-attempt end-to-end reliability SLO

[Full A21 specification](docs/backlog/A-autonomy.md#a21-establish-a-representative-first-attempt-end-to-end-reliability-slo).

#### P2. Harden bounded WordPress public-observability events

[Full P2 specification](docs/backlog/P-publication.md#p2-harden-bounded-wordpress-public-observability-events).

#### P4. Close public briefing, correction, and submission intake

[Full P4 specification](docs/backlog/P-publication.md#p4-close-public-briefing-correction-and-submission-intake).

#### P5. Validate and close responsive search and navigation

[Full P5 specification](docs/backlog/P-publication.md#p5-validate-and-close-responsive-search-and-navigation).

#### P6. Complete blind human editorial acceptance

[Full P6 specification](docs/backlog/P-publication.md#p6-complete-blind-human-editorial-acceptance).

#### P7. Fix public performance measurement and reach hosted targets

[Full P7 specification](docs/backlog/P-publication.md#p7-fix-public-performance-measurement-and-reach-hosted-targets).

#### P8. Complete concise public evidence, methodology, and related-content surfaces

[Full P8 specification](docs/backlog/P-publication.md#p8-complete-concise-public-evidence-methodology-and-related-content-surfaces).

#### P10. Operate correlated public-render failure telemetry

[Full P10 specification](docs/backlog/P-publication.md#p10-operate-correlated-public-render-failure-telemetry).

#### P16. Build a decision-grade consulting synthesis artifact

[Full P16 specification](docs/backlog/P-publication.md#p16-build-a-decision-grade-consulting-synthesis-artifact).

#### P17. Compose adaptive, non-repetitive visual report stories

[Full P17 specification](docs/backlog/P-publication.md#p17-compose-adaptive-non-repetitive-visual-report-stories).

#### E6. Retain a hash-pinned claim-embedding benchmark export

[Full E6 specification](docs/backlog/E-evidence.md#e6-retain-a-hash-pinned-claim-embedding-benchmark-export).

#### E10. Attest active model-pricing rates before they become stale

[Full E10 specification](docs/backlog/E-evidence.md#e10-attest-active-model-pricing-rates-before-they-become-stale).

#### E12. Persist pre-category editorial context checkpoints

[Full E12 specification](docs/backlog/E-evidence.md#e12-persist-pre-category-editorial-context-checkpoints).

#### E13. Measure candidate-regeneration promotion effectiveness

[Full E13 specification](docs/backlog/E-evidence.md#e13-measure-candidate-regeneration-promotion-effectiveness).

#### E14. Calibrate category-fit coverage from retained outcomes

[Full E14 specification](docs/backlog/E-evidence.md#e14-calibrate-category-fit-coverage-from-retained-outcomes).

#### E15. Make publication crops visually complete and repairable

[Full E15 specification](docs/backlog/E-evidence.md#e15-make-publication-crops-visually-complete-and-repairable).

#### E16. Make methodology, applicability, and uncertainty decision-grade

[Full E16 specification](docs/backlog/E-evidence.md#e16-make-methodology-applicability-and-uncertainty-decision-grade).

#### E17. Reduce LLM input, output, and cache cost without quality regression

[Full E17 specification](docs/backlog/E-evidence.md#e17-reduce-llm-input-output-and-cache-cost-without-quality-regression).

#### E18. Stabilize LLM report analysis and first-pass validation

[Full E18 specification](docs/backlog/E-evidence.md#e18-stabilize-llm-report-analysis-and-first-pass-validation).

#### R1. Publish release-evidence reviews where reviewers work

[Full R1 specification](docs/backlog/R-engineering.md#r1-publish-release-evidence-reviews-where-reviewers-work).

#### R2. Enforce role boundaries, direct-I/O discipline, and controlled module growth

[Full R2 specification](docs/backlog/R-engineering.md#r2-enforce-role-boundaries-direct-io-discipline-and-controlled-module-growth).

#### R3. Restore service quality coverage above the retained baseline

[Full R3 specification](docs/backlog/R-engineering.md#r3-restore-service-quality-coverage-above-the-retained-baseline).

#### R6. Review bounded-log reduction telemetry and remediate recurring callers

[Full R6 specification](docs/backlog/R-engineering.md#r6-review-bounded-log-reduction-telemetry-and-remediate-recurring-callers).

#### R7. Prove recoverable backups and full-state disaster restoration

[Full R7 specification](docs/backlog/R-engineering.md#r7-prove-recoverable-backups-and-full-state-disaster-restoration).

#### S3. Simplify the PDF visual-heuristics boundary

[Full S3 specification](docs/backlog/S-simplification.md#s3-simplify-the-pdf-visual-heuristics-boundary).

#### S4. Give WordPress shortcodes semantic ownership

[Full S4 specification](docs/backlog/S-simplification.md#s4-give-wordpress-shortcodes-semantic-ownership).

## Deferred and excluded work

The authoritative statuses and short reasons remain above; the [original register](docs/backlog/archive/CONSOLIDATED_TODO-20261011-preconsolidation.md) preserves the full historical context. Do not activate intentionally deferred DAG scheduling, temporary-sandbox HTTPS migration, speculative provider failover or generic infrastructure work without a measured MVP need. [D13](docs/backlog/R-engineering.md#d13-openai-responses-migration) is a P2 evidence-gated endpoint comparison, not authorization to change the production default or to build stateful reasoning chains. Exclusions remain prohibited behavior, not queued tasks.

## Autonomous-MVP completion and publication safeguards

- A21 must show representative, fixed-cohort first-attempt readiness and controlled sandbox readback/replay on one exact HEAD. Follow P6 human editorial acceptance and E15 independent semantic-crop acceptance.
- Continue to distinguish an immutable `awaiting_review` package from release permission. Default is manual approval. The explicit `autonomous_mvp` approval overlay is **not** evidence that unattended public publication is safe.
- A18 and A19 must prove discoverable eligible report coverage, trustworthy report/request identity, verified acquired artifacts, finite failures, and recoverability. R7 is the separate full-state disaster-recovery outcome.
- Preserve source-grounded claims, method/period/cohort qualification, cost and retry budgets, idempotent public writes, and the intentional sandbox HTTP policy until production-host migration.

## Retained guardrails and dated evidence

- Never normalize cross-publisher metrics with incompatible definitions, geography, methodology, or time period.
- Never publish incomplete public pages for later enrichment; preview/draft is allowed only outside the public release surface.
- Never invent identity attributes for acquisition forms; map only configured, verified values.
- Never lower private-API promotion thresholds automatically.
- Never publish OCR, model, crop, vector, validation, filesystem, stack-trace, or other operator diagnostics as public product content.
- WordPress remains a rendering/publication boundary for intelligence; do not move report intelligence generation into the theme/plugin.

### Non-negotiable publishing guardrail

**Implemented behaviour versus release permission:** Base configuration requires manual approval. The explicitly selected `autonomous_mvp` overlay enables checksum-bound, policy-gated approval of clean report/briefing packages through the existing ledger, outbox, WordPress idempotency and readback (`87add22f`); the current Signal candidate path is manually held by its override marker. This implementation is **not** evidence that P6 editorial acceptance, E15 visual acceptance or A21 full-graph first-attempt/readback proof are complete. Unattended public production writes remain a release hold until source safety, no internal-ID leakage, crop completeness, editorial quality, duplicate suppression, recovery/rollback and reliable WordPress readback have been independently demonstrated and explicitly approved. Sandbox-only canaries are not blanket production authorization.

### Current-state evidence (as of the source register's 2026-10-08 reconciliation)

- Canonical workflow-control, budgets, recovery, model-policy routing, source identity, artifact lineage, publish readiness, and idempotent WordPress publication boundaries are implemented with retained evidence. Manual approval remains the base default; the explicit `autonomous_mvp` overlay adds gated automatic approval, not a waiver of unresolved public release-quality gates.
- WordPress has baseline public render safety, private inbox persistence, responsive navigation/search/filter implementation, and authenticated draft/readback support. P2 still requires a bounded/redacted PHP event contract; P4/P5/P10 retain specific implementation/interaction and hosted operational proof gaps rather than requiring these baseline capabilities to be rebuilt.
- `sync-wordpress-intelligence` has retained evidence for **64 public content entities** — 47 reports, 5 briefings, and 12 signals — **plus 29 publishers**. Do not describe that as 64 total entities.
- HTTPS on the temporary sandbox is intentionally deferred to production-host migration under P3; it is not counted as an autonomous-MVP implementation blocker.
- P6 is an editorial human-acceptance outcome, not an automated-gate implementation gap.
- P7 is not closeable until its measurement semantics distinguish HTTP probe timing from real browser DOM/load timing and report baseline regression separately from target attainment.
- CI covers formatting, typing, architecture/import checks, forbidden patching, hygiene, coverage, mutation, prompt regression, release-evidence archival, PDF candidate/crop/trend gates, public report-quality gates, and WordPress staging verification when configured.
- Current preflight, browser-doctor, synthetic smoke, queue recovery, exact-HEAD canaries, and editorial cohorts provide valuable partial proofs, but no single profile-derived doctor or representative first-attempt SLO yet proves that a clean installation can complete the selected workflow without operator repair.
- Existing reports have strong evidence, summary, insight, counter-signal, and expert-commentary capabilities, but decision logic, methodology applicability, narrative composition, and visual selection are not yet governed by one typed consultancy-grade story model.
- Durable process recovery does not yet amount to disaster recovery: the mutually dependent databases, artifact trees, lineage, queues, and idempotency records lack a retained consistent backup/restore drill.
