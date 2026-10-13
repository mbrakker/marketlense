# Consolidated TODO — canonical MarketLense backlog

**Last structural consolidation:** 2026-10-11. **Status baseline:** 2026-10-08, as recorded in the archived register; D13 was added as a deferred P2 follow-up on 2026-10-11 (neither date implies a new source, deployment, test, or cohort audit). **Consolidation source HEAD:** `b0f1249f014c270dfd85fa6d7fad9cf71035cb90`. **E17 scope added:** 2026-10-11 based on code inspection and the retained 2026-10-06 provider profile; no new report execution is implied. **E18 scope added:** 2026-10-11 as an unverified four-stage stability proposal; no new model run or quality result is implied. **R8 scope added:** 2026-10-11 from a targeted static Windows path audit, without native reproduction at proposal time. PATH-01, including its filename-collision correction, was implemented and verified on native Windows in producer commit `08756d0740023b1c480b7789c9359a1018780a9d`; PATH-02..06 remain open. **D14 scope added:** 2026-10-11 after shared-LLM-boundary inspection and current official subscription-usage documentation; neither OAuth eligibility nor model parity has been live-tested. **R9 scope added:** 2026-10-11 from successful GitHub Actions run timing evidence; R9.1/R9.2 and focused R9.3a/R9.3b are verified, while broader R9.3–R9.4 and the fivefold goal remain open.

This is the **single authoritative status and outcome register**. The five [workstream specifications](docs/backlog/) contain full implementation and Luna guidance, and the [technical proposal index](docs/backlog/proposal-index.md) maps all proposals to one existing owner. Full unchanged backups: [original backlog](docs/backlog/archive/CONSOLIDATED_TODO-20261011-preconsolidation.md) and [original 100-improvement catalogue](docs/backlog/archive/10improvements-20261011-preconsolidation.md). The root [10improvements.md](10improvements.md) is now a compatibility pointer, not a competing backlog.

## Operating rules

- Every canonical ID appears **once** below; only this register determines `Active`, `Closed`, `Deferred`, or `Excluded`. Current status must never be inferred from a technical proposal.
- Every Active ID has exactly one owner specification and its own **Luna prompt**, baseline, implementation sequence and outcome-level acceptance. Implement one verified slice at a time; the linked technical prompts are not permission to reopen closed outcomes or broaden scope.
- Before changes, inspect current HEAD, source boundaries, contracts, relevant `AGENTS.md`, and retained evidence; historical hypotheses and dates must not be presented as fresh verification.
- Evidence for closure belongs in existing `docs/quality/`, `docs/CTO_evidence/` or git history and must name the exact producer SHA/cohort. Do not mark an outcome Closed because one technical slice landed.
- Prefer root-cause fixes and reuse over extra abstractions or validators. Preserve quality, provenance, bounds, safety and publication approval. Follow global `AGENTS.md` for all implementations.

## Execution focus

The register's five workstreams remain the prioritisation lanes, **not** a newly audited ranking. Initial decisions should be evidence-driven: A21 first-attempt reliability, A18/A19 discovery and verified acquisition, E15 semantic crop acceptance, P6 human editorial acceptance, E16 methodology/applicability, and P16/P17 decision-grade composition. Confirm the actual blocker and applicable prerequisites on current HEAD before selecting a slice. No technical proposal is automatically authorised or considered incomplete merely by appearing in the index. E17 is a separately prioritised P1 token/cache-economics outcome: implement its measurement slice first, while preserving the higher-priority correctness and autonomous-MVP gates. E18 is a P1 first-pass analytical-stability outcome: diagnose repeated-run and fixed-input validator variation before authorising its subsequent behavioral stages; reuse A21/E13/E16/P17 evidence and owners. R8 is a P1 Windows-path reliability outcome with five P1 producer/consumer slices followed by one P2 residual audit; do not rewrite already-protected paths. R9 is a P1 CI wall-clock optimisation outcome; preserve full test, mutation, coverage and release-evidence gates while measuring achievable speedup.

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
| Active | A8 | [Compare retained model-call replay bundles](docs/backlog/A-autonomy.md#a8-compare-retained-model-call-replay-bundles) | Comparator/CLI slice and missing-expectation classification fix implemented in `20ac0f406ab14bd5c6cb78ace2a64f7fab3e132e`; evidence below. Keep the outcome Active pending real retained-bundle verification; mapped ARCH-I remains unchanged. |
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
| Active | R1 | [Publish release-evidence reviews where reviewers work](docs/backlog/R-engineering.md#r1-publish-release-evidence-reviews-where-reviewers-work) | Renderer/workflow commit `974ee328505af12bda78222e0c85326cada5957d`; backlog/status follow-up `7b56f0e8403008a7dfb64de511ab39bf8b430715`. Full R1 run `38176147143` passed at SHA `b3464bc5bbdb3d03149d9285506af69d8555d4e6` (7,205 pytest cases). Full current-code run `38179966176` passed at SHA `f5d5dd370abb44f7726196c4b7f954477a3e51a8` (7,229 pytest cases; all required gates passed; optional WordPress staging REST gate skipped). Artifact `11718610500` has all 17/17 required paths (392,779 bytes; expires 2026-10-25). Re-rendering its review/queue JSON produced a 1,224-byte summary with exact SHA, passed canonical validation, zero unwaived/waived issues, historical-unmatched runtime and representative-scope caveat, successful upload and complete bundle. Keep Active because the actual private GitHub rendered-summary page could not be inspected in the signed-out browser. |
| Active | R2 | [Enforce role boundaries, direct-I/O discipline, and controlled module growth](docs/backlog/R-engineering.md#r2-enforce-role-boundaries-direct-io-discipline-and-controlled-module-growth) | Close targeted boundary-coverage and expiring-waiver gaps without generic governance noise. |
| Active | R3 | [Restore service quality coverage above the retained baseline](docs/backlog/R-engineering.md#r3-restore-service-quality-coverage-above-the-retained-baseline) | Add behavior-focused service coverage and refresh the baseline only from a passing exact-commit run. |
| Closed | R4 | Publication usage/projection reconciliation guard | Missing/invalid/materially lagged usage/projection evidence stops public writes without rebuilding. |
| Closed | R5 | Hash-verified dependency lock artifacts | Native Ubuntu CPython 3.12 wheelhouse and offline hash-locked install are verified. |
| Closed | R6 | [Review bounded-log reduction telemetry and remediate recurring callers](docs/backlog/R-engineering.md#r6-review-bounded-log-reduction-telemetry-and-remediate-recurring-callers) | CTO scorecard and executive totals implemented; 162 focused tests pass with 100% contract coverage. Exact-HEAD fixture flags a recurring owner-mapped group; inspected retained log sample has 0 reductions in 20,444 events. Actual caller fixes remain review-driven if a corpus flags them. |
| Active | R7 | [Prove recoverable backups and full-state disaster restoration](docs/backlog/R-engineering.md#r7-prove-recoverable-backups-and-full-state-disaster-restoration) | Back up the mutually dependent stores/artifacts consistently and prove isolated restoration, integrity, lineage, and safe resume against explicit recovery objectives. |
| Active | R8 | [Harden Windows artifact path construction and reuse](docs/backlog/R-engineering.md#r8-harden-windows-artifact-path-construction-and-reuse) | PATH-01 mailbox paths and filename-collision fixes verified on native Windows (producer `08756d0740023b1c480b7789c9359a1018780a9d`): 2,374 focused mailbox/contract/handoff tests passed; sanitized direct-name, same-name/different-payload, Unicode ZIP, genuine duplicate, cross-attachment, repeat, exact readback, staging cleanup and impossible-root behavior covered. Formatting, Ruff, 775-file mypy (0 tracked errors), architecture import, role-I/O, service-boundary and contract-snapshot gates passed. PATH-02..05 and P2 PATH-06 remain open; R8 stays Active. |
| Active | R9 | [Accelerate CI validation fivefold without weakening release gates](docs/backlog/R-engineering.md#r9-accelerate-ci-validation-fivefold-without-weakening-release-gates) | R9.1/R9.2 and focused R9.3a/R9.3b/R9.3c are verified. R9.1's dependency follow-up removed 19 orphaned GPU pins; three exact-SHA full-CI reruns passed with unchanged gates. Clean Linux hash-locked install fell 362.923s→86.526s; hosted install medians fell 88–103s per job. Candidate median workflow was 11:49 vs 13:08 baseline (79s lower), while candidate pytest telemetry was 7:01 vs 5:38; only setup savings are attributed to package removal. Active runner median was 23.10 vs 30.10 minutes, with zero billed milliseconds for this public workflow. A later R9.1 cross-platform repair adds verified Linux/Windows wheel hashes without changing prior pins/hashes; native fresh installs and pip checks pass on Ubuntu CPython 3.12.3 and Windows CPython 3.12.10. Full lock, setup timing, and hosted-CI evidence is in R9 below. R9.3c replaces the synthetic fairness simulation with durable queue/outbox execution while preserving the source-before-analysis assertion and queue limits. Three exact-SHA full-CI attempts on `ebd3bed3` passed with all 7,447 node IDs, 86.36% coverage, 17/68/67 mutations and complete 11/11 release evidence. Median wall/pytest/active runner time was 13:08 / 5:38 / 30.10 minutes versus R9.3b's 13:52 / 6:52 / 29.45; the cross-SHA wall gain is not attributed to this test-fidelity fix, and runner use rose 0.65 minutes. Checkout follow-up localized the 6:40 outlier to one full-ref fetch on a `chilecentral` runner; same-run peers and 12 later checkout steps took 10–14 seconds. Its trigger remains unproven, so checkout depth is unchanged. No production scheduling, CI topology or quality gate changed. Broader R9.3 and R9.4 remain open; next profile Test A and the mutation critical path. |
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
| Deferred | D13 | [Evaluate direct OpenAI Responses migration](docs/backlog/R-engineering.md#deferred-initiative-d13-evaluate-direct-openai-responses-migration) | P2: selectively A/B direct OpenAI text/JSON generation against current Chat Completions on the frozen five-report cohort; migrate only with non-regressing quality/reliability and demonstrated overall benefit. Keep OpenRouter; test reasoning-context reuse separately. |
| Deferred | D14 | [Evaluate ChatGPT-plan debugging inference adapter](docs/backlog/R-engineering.md#deferred-initiative-d14-evaluate-chatgpt-plan-debugging-inference-adapter) | P2: evaluate an opt-in locally authenticated subscription-backed inference adapter at the existing LLM boundary. Validate eligibility/model parity first; unsupported API calls require explicit billed-API permission or fail. Preserve production default, quality and provenance. |
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

**Register counts (recounted from rows):** 33 Active, 45 Closed, 14 Deferred, 3 Excluded (95 total). The archived 2026-10-08 baseline contained 89 items; D13, E17, E18, R8, D14 and R9 were added as proposals on 2026-10-11, and R6 was reconciled to Closed. R9.1 has a three-run exact-SHA baseline, cold/warm setup evidence, and a verified GPU-stack removal: local clean install improved by 276.397 seconds and three candidate full-CI runs on `5bee0790` passed with a 79-second lower wall median than the R9.3c baseline; this wall difference is not wholly attributed to dependencies. R9.2 has three successful exact-SHA full runs, 13:51 median wall time and one failed attempt among four. R9.3a has an exact-node-set, three-run candidate cohort and a measured local 37.7% Test B selection-stage reduction, but no attributable full-CI speedup. The fivefold goal remains unverified; R9 remains Active for the rest of R9.3 and R9.4.


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

**Follow-up implementation verification — 2026-10-11:** Renderer/workflow
commit `974ee328505af12bda78222e0c85326cada5957d` separates canonical
exact-SHA review/queue validation from runtime and upload status. Backlog and
evidence-documentation follow-up commit `7b56f0e8403008a7dfb64de511ab39bf8b430715`
aligns tests and retained R6 status. Focused validation passed: 50 pytest
cases across backlog organization, workflow-queue, release-evidence workflow,
and release-review suites; formatting, Ruff, repository mypy baseline,
repository hygiene, backlog-source, documentation, and risk-policy gates.
Generated Markdown was inspected for valid review/queue evidence with a
partial bundle and historical runtime SHA, a contradictory successful review
with a failed required artifact, and missing review/queue inputs.

The push run
[`38174895618`](https://github.com/mbrakker/marketlense/actions/runs/38174895618)
tested exact SHA `7b56f0e8403008a7dfb64de511ab39bf8b430715` and completed
successfully in 15m45s: all repository, backlog/documentation, 7,205 pytest,
coverage, mutation, quality, queue, release-review, upload, and summary steps
passed. Optional WordPress staging REST verification was skipped by
configuration. Uploaded artifact
[`release-evidence-bundle`](https://github.com/mbrakker/marketlense/actions/runs/38174895618/artifacts/11715692798)
was 389,685 bytes, expires `2026-10-25T21:20:58Z`, and its downloaded file
inventory contains all 17 configured required paths. The uploaded canonical
review and queue JSON were passed back through the renderer: it reported
canonical validation `passed`, exact tested SHA/build, zero unwaived issues,
runtime `historical_unmatched`/`representative` with the declaration caveat,
and bundle `complete`. This is a local re-render of live artifact JSON, not a
readback of GitHub's rendered job-summary body. The Playwright run page
redirected to sign-in for this private repository, so direct live presentation
inspection remains unavailable; R1 remains Active until that reviewer-surface
acceptance is demonstrated.

#### R2. Enforce role boundaries, direct-I/O discipline, and controlled module growth

[Full R2 specification](docs/backlog/R-engineering.md#r2-enforce-role-boundaries-direct-io-discipline-and-controlled-module-growth).

#### R3. Restore service quality coverage above the retained baseline

[Full R3 specification](docs/backlog/R-engineering.md#r3-restore-service-quality-coverage-above-the-retained-baseline).

#### R7. Prove recoverable backups and full-state disaster restoration

[Full R7 specification](docs/backlog/R-engineering.md#r7-prove-recoverable-backups-and-full-state-disaster-restoration).

#### R8. Harden Windows artifact path construction and reuse

[Full R8 specification](docs/backlog/R-engineering.md#r8-harden-windows-artifact-path-construction-and-reuse).

#### R9. Accelerate CI validation fivefold without weakening release gates

[Full R9 specification](docs/backlog/R-engineering.md#r9-accelerate-ci-validation-fivefold-without-weakening-release-gates).

**R9.1 verification — 2026-10-12:** Three comparable baseline runs ([38174895618](https://github.com/mbrakker/marketlense/actions/runs/38174895618), [38176147143](https://github.com/mbrakker/marketlense/actions/runs/38176147143), [38176419426](https://github.com/mbrakker/marketlense/actions/runs/38176419426)) had a 15:48 median workflow time and 54.00 active runner-minutes total. Three full attempts on exact SHA `878063ca62f5ee6adbdf43977171040dbd1cf9d2` ([cold](https://github.com/mbrakker/marketlense/actions/runs/38177811842/attempts/1), [warm](https://github.com/mbrakker/marketlense/actions/runs/38177811842/attempts/2), [warm](https://github.com/mbrakker/marketlense/actions/runs/38177811842/attempts/3)) all passed; each release review validated 11/11 required entries with zero issues and uploaded all 17 bundle files. Setup-through-install median was 2:24 across all three (8s below baseline) and 2:19.5 warm-only; no end-to-end speedup was measured (23:56 median workflow time). All baseline pytest node IDs remain, coverage stayed at 86.21%, and all 17 mutation targets retained identical 67/68 results. Post-change jobs used 72.27 active runner-minutes; the GitHub API reported zero billable milliseconds for these public-repository jobs. Full timing table and limitations are in [R9](docs/backlog/R-engineering.md#r9-accelerate-ci-validation-fivefold-without-weakening-release-gates).

**R9.1 GPU dependency removal — 2026-10-13:** A complete source/manifest audit found no runtime or transitive requirement for PyTorch, Triton, CUDA, or NVIDIA packages; 19 orphaned lock pins were removed without changing unrelated versions or hashes. Fresh Linux Python 3.12 installs with `--require-hashes` and pip cache disabled measured 362.923s before vs 86.526s after, with `pip check` passing both times; installed distributions fell 178→159 and `site-packages` fell by 7,179,073,485 bytes. Across three full runs on candidate SHA `5bee0790cce3c921c829a08f31cff5cf2d3ef200` ([1](https://github.com/mbrakker/marketlense/actions/runs/38317018992/attempts/1), [2](https://github.com/mbrakker/marketlense/actions/runs/38317018992/attempts/2), [3](https://github.com/mbrakker/marketlense/actions/runs/38317018992/attempts/3)), all four job installs succeeded; install medians fell 88–103 seconds per job. Median workflow wall was 11:49 vs 13:08 for the exact-SHA R9.3c baseline, but pytest median rose from 5:38 to 7:01, so only the install-step savings are attributed to package removal. Coverage stayed at 86.36%, mutation at 17/68/67, and each release gate passed; attempt 3's 17-file bundle independently passed 11/11 checks with all 11 hashes and byte counts verified. The original Windows hash mismatch was resolved in the R9.1 cross-platform follow-up below without weakening hash verification or changing existing dependency pins. R9 remains Active for R9.3/R9.4. Full per-job timings and the limitation are recorded in [R9](docs/backlog/R-engineering.md#r9-accelerate-ci-validation-fivefold-without-weakening-release-gates).

**R9.1 cross-platform lock repair — 2026-10-13:** The R5 builder and canonical consistency check now evaluate Linux and Windows targets. All original 159 pins and hashes were preserved; the 163-entry lock has 39 added verified hashes and four pinned editable-build packages. Native wheel audits passed for 162 Linux-active and 163 Windows-active entries. Fresh offline hash-locked installs, editable browser-use setup, `pip check`, dependency consistency, CLI startup, and the 2-test browser runtime contract passed on Ubuntu 24.04 / CPython 3.12.3 and native Windows x64 / CPython 3.12.10. Install time was 66.33s Linux and 274.03s Windows from local audited wheel inventories; Linux wheel acquisition took 19.09s. These samples do not establish a setup speedup; the Linux inventory grew by 147,867 bytes (0.061%). First hosted run [38356564999](https://github.com/mbrakker/marketlense/actions/runs/38356564999) on SHA `12671b97e0448cf216d6e3edde8df80cae146f4a` passed both mutation partitions and all dependency installs, then failed one pytest fixture that had requested a non-native Windows audit on Linux (7,456 passed, 1 failed); release evidence correctly failed closed with no bundle. The test now checks the native platform against an opposite-platform artifact. Pytest artifact comparison also found that the first edit had renamed the existing `test_target_marker_filters_windows_only_pin` node; its ID is restored, and the assertion checks marker selection for both platforms. The failed node and all 18 focused tests pass on both Windows and Linux. Full hosted-CI rerun remains required. Full commands and limitations are in [R9](docs/backlog/R-engineering.md#r9-accelerate-ci-validation-fivefold-without-weakening-release-gates).

**R9.2 verification — 2026-10-12:** Exact SHA `1d78865d0c4b3c9e43a5a03dc4dfe267a78d62d4` passed full CI on attempts [1](https://github.com/mbrakker/marketlense/actions/runs/38213012092/attempts/1), [2](https://github.com/mbrakker/marketlense/actions/runs/38213012092/attempts/2), and [4](https://github.com/mbrakker/marketlense/actions/runs/38213012092/attempts/4); median workflow wall was 13:51 versus 23:56 for the hash-cached sequential cohort, while active runner usage increased from 24.09 to 30.63 minutes/run (public billed time remained zero). Attempt 3 failed one scheduler-fairness test and produced no approved release bundle; its fixture root cause was investigated in R9.3c below. Attempt 4's 17-file release bundle passed all 11 required checks, its hashes matched, and the review had zero issues. R9 stays Active for broader pytest profiling and release-timing telemetry; complete stage timings, failure details and commands are recorded in [R9](docs/backlog/R-engineering.md#r9-accelerate-ci-validation-fivefold-without-weakening-release-gates).

**R9.3a verification — 2026-10-12:** The final candidate SHA `e968a3f0e96e7278020f66557feb9004d97c300f` passed complete CI on all three exact-SHA attempts ([1](https://github.com/mbrakker/marketlense/actions/runs/38264311659/attempts/1), [2](https://github.com/mbrakker/marketlense/actions/runs/38264311659/attempts/2), [3](https://github.com/mbrakker/marketlense/actions/runs/38264311659/attempts/3)); final release bundles were 17 files with 11/11 required entries hash-verified and zero review issues. Its baseline SHA `03e7f26370c835b0f3fd22793d051a2c9e9e9254` has three successful full runs ([1](https://github.com/mbrakker/marketlense/actions/runs/38247162732/attempts/1), [2](https://github.com/mbrakker/marketlense/actions/runs/38247162732/attempts/2), [4](https://github.com/mbrakker/marketlense/actions/runs/38247162732/attempts/4)); attempt 3's existing PDF runtime-warning release failure is recorded and excluded. Median wall was 15:03 baseline vs 15:08 candidate; no attributable full-CI speedup is claimed. The same 7,447 unique node IDs, 17 targets/68 mutants/67 killed, and existing quality gates were retained. Detailed stage measurements, cost, variance, failure context, and verification commands are in [R9](docs/backlog/R-engineering.md#r9-accelerate-ci-validation-fivefold-without-weakening-release-gates). R9 remains Active for the residual Test A tail and checkout investigation, then R9.4 telemetry; the supervisor-fairness fixture correction is recorded below.

**R9.3c verification — 2026-10-12:** The recurring failure occurred on exact SHA `1d78865d0c4b3c9e43a5a03dc4dfe267a78d62d4` in [run 38213012092 attempt 3](https://github.com/mbrakker/marketlense/actions/runs/38213012092/attempts/3) and sampler SHA `895a001ad239be77976d40c5a6cff683eea1d098` in [run 38284060835](https://github.com/mbrakker/marketlense/actions/runs/38284060835), both at `source_progress_overtaken`. The old synthetic fixture's independent counters did not model durable claims, queue capacity, downstream payloads or outbox materialization. The replacement retains the source-before-analysis assertion over five durable source jobs, the production queue worker/outbox materializer and source-ingest → selection → analysis handlers. It checks 15 successful single-attempt jobs, lineage, idempotency replay and three-per-queue capacity. A local event trace showed source starts 4 and 5 before analysis start 3. The test passed 20 direct repetitions, three focused `-n 4 --dist=worksteal` runs and the 117-test supervisor/queue suite. Three complete exact-SHA runs on implementation SHA `ebd3bed3739e981594e6338bda675b338d80f069` passed: [attempt 1](https://github.com/mbrakker/marketlense/actions/runs/38301470970/attempts/1), [attempt 2](https://github.com/mbrakker/marketlense/actions/runs/38301470970/attempts/2), and [attempt 3](https://github.com/mbrakker/marketlense/actions/runs/38301470970/attempts/3). Each retained 7,447 unique node IDs, 86.36% coverage, 17 targets / 68 mutants / 67 killed, and a 17-file exact-SHA release bundle with all 11 required entries passing and manifest hashes/byte counts verified. Median wall / pytest / active runner time was 13:08 / 5:38 / 30.10 minutes versus the R9.3b four-worker median 13:52 / 6:52 / 29.45; this cross-SHA difference is not attributed to the test correction. See R9 for setup timings and run-to-run variance. No production scheduler, queue limits, CI topology, mutation or quality gate changed; R9 remains Active for broader R9.3 and R9.4.

**R9.1 cross-platform final hosted verification — 2026-10-13:** The rerun required after the fixture corrections passed on exact code SHA `77e28124971962aa8e6a17f21ce09d4d79559fcd` in [full CI run 38359509277](https://github.com/mbrakker/marketlense/actions/runs/38359509277). It retained all 7,449 previously observed pytest node IDs and added eight dependency tests (7,457 unique IDs); coverage passed at 84,757/98,151 lines (86.35%). All 17 mutation targets passed their configured floors (68 mutants, 67 killed). The exact-SHA release manifest/review passed all 11 required artifacts with zero issues/waivers, and independent SHA-256/byte-count checks matched all 11 files. Workflow wall was 9:44 and summed active runner time 21.95 minutes; the GitHub timing API reported zero billable milliseconds. Four hash-locked dependency installs passed. These single-run setup timings do not establish an improvement. R9 remains Active; R9.3/R9.4 remain open. Detailed stages and limits are in [R9](docs/backlog/R-engineering.md#r9-accelerate-ci-validation-fivefold-without-weakening-release-gates).

#### S3. Simplify the PDF visual-heuristics boundary

[Full S3 specification](docs/backlog/S-simplification.md#s3-simplify-the-pdf-visual-heuristics-boundary).

#### S4. Give WordPress shortcodes semantic ownership

[Full S4 specification](docs/backlog/S-simplification.md#s4-give-wordpress-shortcodes-semantic-ownership).

## Deferred and excluded work

The authoritative statuses and short reasons remain above; the [original register](docs/backlog/archive/CONSOLIDATED_TODO-20261011-preconsolidation.md) preserves the full historical context. Do not activate intentionally deferred DAG scheduling, temporary-sandbox HTTPS migration, speculative provider failover or generic infrastructure work without a measured MVP need. [D13](docs/backlog/R-engineering.md#deferred-initiative-d13-evaluate-direct-openai-responses-migration) is a P2 evidence-gated endpoint comparison, not authorization to change the production default or to build stateful reasoning chains. [D14](docs/backlog/R-engineering.md#deferred-initiative-d14-evaluate-chatgpt-plan-debugging-inference-adapter) is a distinct P2 subscription-backed local debug experiment, not a universal API proxy or permission to change production routing, silently bill API operations or weaken grounding. Exclusions remain prohibited behavior, not queued tasks.

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

### A8 comparison implementation evidence — 2026-10-12

- Comparator source commit: `20ac0f406ab14bd5c6cb78ace2a64f7fab3e132e` (`fix: classify missing replay expectations as incomplete`; includes `8c70e4cef9612ae9452f4392e597dc747bf82685`, `feat: support replay comparison expectations`, and `9d8e98c4d8b25496954a48802adb23e64fc3041b`, `feat: compare retained model-call replay bundles`). The versioned comparator and JSON CLI are read-only and do not construct a provider client; complete compatible identity comparisons require retained prompt, model, policy, schema, selected-evidence, output, and artifact identities. The request supports optional safe-field compatibility expectations without returning expected or retained identity values. A missing expected candidate identity is added to `missing_fields`, leaves `expectation_mismatch_fields` empty, and classifies as `incomplete`; a present mismatch classifies as `incompatible`. A regression requires a compatible complete cohort, changed output identity, and baseline validation pass to candidate validation fail.
- Exact-HEAD verification: `python -m pytest -q tests/test_model_call_replay_comparison.py tests/test_llm_service.py tests/test_llm_service_boundary.py` — 45 passed. `python -m ruff check src/services/llm_service.py src/contracts/workflow_control.py src/contracts/model_call_replay_comparison.py src/services/_llm_service/audit.py scripts/quality/compare_model_call_replay_bundles.py tests/test_model_call_replay_comparison.py` — passed. `python -m ruff format --check src/services/llm_service.py src/contracts/workflow_control.py src/contracts/model_call_replay_comparison.py src/services/_llm_service/audit.py scripts/quality/compare_model_call_replay_bundles.py tests/test_model_call_replay_comparison.py` — passed. `python -m mypy src/contracts/model_call_replay_comparison.py src/contracts/workflow_control.py src/services/_llm_service/audit.py src/services/llm_service.py scripts/quality/compare_model_call_replay_bundles.py` — no issues in 5 source files.
- CI checks passed: `python scripts/ci/check_role_io_boundaries.py`, `python scripts/ci/check_service_boundary_map.py`, `python scripts/ci/check_contract_schemas.py`, `python scripts/ci/check_documentation.py`, and `python scripts/ci/check_repository_hygiene.py`. Backlog checks passed: `python -m pytest -q tests/test_backlog_organization.py` — 7 passed; `python scripts/ci/check_backlog_source.py` — 33 active rows/sections, zero duplicate IDs, missing/orphan sections, or title mismatches. CLI `--help` was inspected. Tests exercise exact equivalence/repeatability, compatible output changes, incompatible cohorts, incomplete and malformed legacy bundles, comparable validation regression, deterministic field ordering, expectation mismatch without value disclosure, zero provider calls, no external writes, and private-content non-disclosure.
- Inspected deterministic synthetic CLI JSON: matching complete bundles returned `equivalent`; changed output/artifact identity returned `compatible_but_changed`; changed output identity with validation pass-to-fail returned `materially_regressed`; legacy inputs returned `incomplete`. For `--expect schema_sha256=...`, both-sides-missing and candidate-missing cases returned `incomplete`, included `schema_sha256` in `missing_fields`, left mismatch fields empty, and set `expectations_met=false`. A present model mismatch returned `incompatible` with only `model` in `expectation_mismatch_fields`; mixed missing schema and mismatched model returned `incomplete` with `IDENTITY_INCOMPLETE`, `COHORT_INCOMPATIBLE`, and `EXPECTATION_MISMATCH`. Repeated JSON was byte-identical, and expected values were absent from output.
- Retained-artifact limitation: no complete serialized model-call replay bundles or eligible real pair were available in the checked-in evidence corpus. Existing audit rows lack per-call policy, selected-evidence, output, and artifact identities; report lineage has no stable per-call join. Full comparison behavior is therefore demonstrated with synthetic fixture bundles only, and retained identity hashes are shape-checked but their producer derivation is not independently authenticated. A8 remains Active pending real retained-bundle verification; mapped ARCH-I was not changed by this fix.

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
