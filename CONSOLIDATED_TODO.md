# Consolidated TODO

Last audited: 2026-07-08

This file is the single active backlog for this repository. It supersedes older backlog notes, archived planning docs, and ad hoc audit intake.

Items below were rechecked against the current repository state. Completed capabilities are listed as closed evidence and are not active backlog. Partially landed capabilities remain only when a concrete implementation gap is still visible in code, tests, README, or local WordPress assets.

## Backlog Rules

- Treat this file as the only active TODO source.
- Remove an item when all acceptance criteria are met.
- Merge overlapping work into one item instead of creating parallel tasks.
- Before implementation starts, every prioritized item must have an owner, baseline metric, target metric, and review/expiry date.
- Keep changes compliant with `AGENTS.md`: no placeholder logic, no role mixing, no prompt text in code, no private-helper monkeypatching, and no new deployable boundary without architecture review.

Scoring:

- `Impact`: `1` low leverage, `5` highest leverage across reliability, quality, cost, speed, or architecture.
- `Effort`: `1` localized change, `5` broad refactor/migration with cross-module coordination.

## Current-State Evidence

- CI currently runs formatting, risk classification, split-symbol linking, typing, architecture import, forbidden patching, repository hygiene, quality ledger, remediation runbook, backlog source, contract schema snapshot, WordPress subproject, default pytest with coverage, coverage gate, mutation gate, quality non-regression, prompt fixture corpus regression, and release evidence manifest archival/freshness gates through `.github/workflows/ci.yml`.
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
- A 20-publisher live acquisition run on 2026-07-06 used `reports@marketbearing.eu` for delivery, verified ad hoc publisher Drive folder creation, blocked public-search drift after exact execution URLs, preferred complete on-site report captures over optional enum blockers, and tightened mailbox candidate selection so SATISFYD, Mimecast, and Sprinklr rejected unrelated Contentsquare delivery links with `candidate_count=0` while a Contentsquare-owned mailbox delivery still produced 12 eligible publisher-affine candidates.
- The LLM boundary now records primary/fallback provider decisions, but `budget_decision="not_configured"` remains; dynamic budget-aware model routing and live spend policy remain open.
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

## Priority Order

1. Pipeline autopilot, planning, resume, and recovery interconnections.
2. Cost and LLM controls.
3. Analytics projection and embeddings.
4. Publish durability, WordPress/public entity alignment, and public-site QA.
5. User-facing output quality and editorial contracts.
6. PDF/performance hotspots.
7. Architecture, schema compatibility, and observability gates.

---

## 1. Cost and LLM Controls

- **Title:** Enforce real-time spend guardrails across run/day/publisher budgets [Impact: 5/5, Effort: 2/5]
  - Problem fixed: Cost ledger append and rollup paths exist, but they are post-hoc reporting. There is still no pre-call policy that warns, pauses, or blocks expensive model/browser/OCR work based on live spend.
  - Why implement: Prevents runaway spend and makes cost decisions operationally visible.
  - Tradeoffs / risks: Needs a clear operator override path so legitimate runs are not blocked silently.
  - Acceptance Criteria:
    - YAML config defines thresholds for run, day, and publisher scopes.
    - Orchestrators check thresholds before model, browser, OCR, or other expensive calls.
    - Breaches emit typed events, structured logs, and explicit outcomes: `warn`, `pause`, `stop`, or `override`.
    - Tests cover warn, hard-stop, and operator-override paths with output contract and log assertions.

- **Title:** Implement budget-aware model routing with deterministic context compaction [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Model resolution is still mostly static through configured OpenAI models and namespace matching. `llm_service` records budget policy as not configured.
  - Why implement: Reduces cost, latency, timeout risk, and unreviewable ad hoc prompt trimming.
  - Tradeoffs / risks: Requires careful evidence-retention tests and benchmark ownership.
  - Acceptance Criteria:
    - Policy table maps task families to model tier, max input budget, fallback tier, and quality threshold.
    - Routing decision, budget decision, compaction strategy, and reason are logged for each call.
    - Over-budget requests are compacted deterministically before model calls.
    - Regression tests protect evidence retention on a fixed prompt/output corpus.
    - Benchmarks show token/cost reduction without quality regression on that corpus.

- **Title:** Measure md5 vector-store reuse savings and stale-store risk [Impact: 4/5, Effort: 2/5]
  - Problem fixed: Duplicate-content vector-store reuse now exists, but operators cannot yet see avoided uploads/indexing calls or stale-store candidates across retained state.
  - Why implement: Quantifies cost and latency savings from md5 reuse and gives retention cleanup a concrete safety signal.
  - Tradeoffs / risks: The report must read existing state only by default and avoid remote provider calls unless explicitly requested.
  - Acceptance Criteria:
    - A quality command reads processed-state rows and reports duplicate md5 groups, reused vector-store count, avoided upload/indexing estimate, and rows missing reusable state.
    - Optional live validation samples a bounded set of reused vector stores and records status without mutating state.
    - Retention cleanup can consume the report or equivalent helper to avoid pruning stores still referenced by duplicate aliases.
    - Tests cover duplicate grouping, missing-vector-store rows, stale status classification, and no-provider-call default behavior.

---

## 2. Analytics Projection, Signals, and Embeddings

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

## 3. Publish Durability and WordPress Alignment

- **Title:** Turn the publish snapshot into durable jobs or rename it as an ops readiness snapshot [Impact: 5/5, Effort: 5/5]
  - Problem fixed: `publish_queue_orchestrator.py` is live in UI/ops flows but only builds a read-only snapshot from HTML files and publish state. It does not enqueue durable publish intents or atomically couple publish side effects to state transitions.
  - Why implement: Either creates a real reliable publish queue or removes misleading queue language.
  - Tradeoffs / risks: Durable jobs require queue/outbox infrastructure; renaming requires UI/docs/API cleanup.
  - Acceptance Criteria:
    - If implemented as jobs: publish intents can be enqueued, persisted, retried, dead-lettered, and idempotently delivered.
    - If kept read-only: contracts, UI labels, docs, and logs stop using queue terminology for this feature.
    - Outbox records side-effect intents atomically with related state changes if job delivery is implemented.
    - Failure-injection tests cover restart, retry, duplicate dispatch, and partial WordPress failures.

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

## 4. PDF, Dashboard, and Runtime Performance

## 5. User-Facing Output Quality and Editorial Contracts

- **Title:** Add live strategic insight-quality benchmark for scored insight fields [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Insight prompts now emit strategic scores, coverage roles, `so_what`, `now_what`, and report lenses, but there is no retained-artifact benchmark proving those fields improve diversity and decision usefulness over time.
  - Why implement: Converts the new contract fields into a measurable quality loop and prevents score/role drift from becoming decorative metadata.
  - Tradeoffs / risks: The benchmark must evaluate source-grounded structure and diversity without brittle wording expectations.
  - Acceptance Criteria:
    - A quality command evaluates existing report-analysis artifacts for role diversity, duplicate insight overlap, non-empty `so_what`/`now_what`, supported report lens, metric-backed score calibration, and evidence linkage.
    - Output compares current artifacts against a saved baseline and reports improvements/regressions by publisher/report family.
    - The benchmark can run in default read-only mode without model calls and optionally sample live regeneration behind an explicit flag.
    - Tests cover metric calculation, narrow-report fallback, unsupported-role detection, and unchanged-artifact baseline stability.

- **Title:** Render executive advisory and metric-spine payloads in public report pages [Impact: 5/5, Effort: 3/5]
  - Problem fixed: The artifact contract now emits optional `executive_advisory` and `metric_spine` payloads, but public report pages do not yet expose those higher-value decision artifacts.
  - Why implement: Turns the new analysis payloads into visible user value: faster executive scanning, clearer proof points, and stronger consultancy-grade differentiation.
  - Tradeoffs / risks: Rendering must stay fail-closed when optional payloads are absent and must not expose internal evidence IDs, spans, JSON fields, or generated diagnostics as public copy.
  - Acceptance Criteria:
    - Report HTML renders decision brief, supported recommendations, risks/watchouts, and strongest metric-spine proof points when present.
    - Empty/not-found advisory states render neutral omissions or admin diagnostics, not placeholder user-facing content.
    - Public copy uses source-safe labels and existing citation micro-lines without exposing evidence IDs or internal pack names.
    - Visual and schema tests cover populated advisory payloads, absent payloads, and mobile layout.

- **Title:** Benchmark route-memory avoided browser spend from mailbox and download outcomes [Impact: 4/5, Effort: 2/5]
  - Problem fixed: Mailbox successes now promote publisher route memory, but operators need a measured report showing avoided browser launches, avoided model calls, and route-success stability over retained publisher evidence.
  - Why implement: Quantifies cost/speed gains from the new feedback loop and gives a guardrail if stale route memory starts hurting acquisition quality.
  - Tradeoffs / risks: The benchmark must use retained report-store/state evidence and avoid rerunning expensive browser flows by default.
  - Acceptance Criteria:
    - A quality script reads existing report-store route history and state mail-delivery rows, then estimates avoided browser/model calls by route family and publisher.
    - Output reports exact-route reuse, publisher-policy reuse, mailbox-promoted route count, stale/conflicting memory count, and verified-success rate.
    - The script can optionally sample a bounded live rerun set when explicitly enabled.
    - Tests cover deterministic metric calculation and stale/conflict classification.

- **Title:** Add editorial contract versioning and quality gates before publishing [Impact: 5/5, Effort: 4/5]
  - Problem fixed: User-facing output can evolve across prompts and schemas without a single editorial contract version or publish-time gate for generic phrasing, unsupported implications, duplicated insights, missing caveats, weak actionability, forbidden internal references, and tone defects.
  - Why implement: Explicit versioning and validation let the project raise editorial quality without silently breaking downstream renderers or publishing low-trust prose.
  - Tradeoffs / risks: Overly strict gates can raise regeneration cost, block acceptable outputs, or create repetitive copy if repair prompts are too narrow.
  - Acceptance Criteria:
    - A user-facing editorial artifact contract version governs new final-output fields for decision brief, recommendations, risks, limitations, coverage diagnostics, evidence spans, scoring metadata, metric spine, and audience variants.
    - Adapters or migration logic preserve existing artifact consumers and public renderers until they opt into the richer version.
    - Editorial quality validation emits stable rule IDs for generic phrasing, unsupported implications, missing metric support, duplicate insights, missing caveats, weak actionability, forbidden internal references, and tone defects.
    - New quality rules start as warnings with logged remediation context, then can be promoted to hard failures only after fixture and live-artifact evidence proves stability.
    - README documents the editorial contract version, rollout sequence, warning-to-error policy, and coexistence behavior with current report artifacts.

## 6. Architecture, Schema Compatibility, and Observability

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


---

## 7. Pipeline Autopilot, Resume, and Recovery Interconnections

- **Title:** Add a single pipeline planning brain before execution [Impact: 5/5, Effort: 4/5]
  - Problem fixed: CLI, UI, ingest, report generation, analysis, publish, and recovery paths currently require the operator or caller to know which entrypoint and flags to use. The system has strong individual orchestrators, but no typed plan that derives the safest next action from repository state, config, credentials, checkpoints, and publish readiness.
  - Why implement: A plan-first control layer lets the pipeline need less user direction: users can request an intent such as `process ready reports`, `repair failed runs`, or `publish ready artifacts`, while the system decides which steps to run, skip, resume, or block.
  - Tradeoffs / risks: Requires careful scope control so the planner does not become a second orchestration implementation or embed domain logic.
  - Acceptance Criteria:
    - A typed `PipelinePlan` contract lists ordered steps, skipped steps, blockers, required credentials, side-effect boundaries, resume points, idempotency keys, and expected outputs.
    - A planner uses existing services/read models to inspect current state without performing side effects.
    - CLI/UI can run a read-only plan mode before execution and can execute an approved plan through existing orchestrators.
    - Tests cover ready, partially complete, failed, missing-credential, and publish-only states with plan contract and log assertions.

- **Title:** Add config-driven autopilot profiles for common pipeline intents [Impact: 4/5, Effort: 3/5]
  - Problem fixed: The settings model exposes many low-level knobs for workers, Drive listing, OCR, model scopes, ranking, caching, and publishing, so users still need operational knowledge to choose a safe run mode.
  - Why implement: Profiles let users choose intent, not implementation details, and let the planner select safe defaults based on current state.
  - Tradeoffs / risks: Profiles must be thin presets over existing typed settings, not a parallel configuration system.
  - Acceptance Criteria:
    - YAML defines documented profiles such as `safe_default`, `fast_cached`, `repair_failed`, `publish_ready`, `browser_acquisition`, `cost_saver`, and `high_quality`.
    - The planner can recommend or apply a profile while logging every resolved low-level setting that changes behavior.
    - Profile resolution validates against the existing settings contract and never hides secrets in YAML.
    - Tests cover profile selection, explicit override precedence, invalid profile names, and deterministic resolved settings.

- **Title:** Add an autonomous run supervisor control loop [Impact: 5/5, Effort: 5/5]
  - Problem fixed: Preflight, retry decisions, idempotency, checkpoints, run registry state, validation repair, and health scorecards exist as separate capabilities, but no single control loop continuously chooses `start`, `resume`, `retry`, `defer`, `repair`, `publish`, `dead-letter`, or `notify` across the full pipeline.
  - Why implement: Lets the system operate as an unattended agent that chooses safe next actions from state instead of requiring users to invoke the correct entrypoint or resume flag.
  - Tradeoffs / risks: Must remain a control-plane orchestrator and must not duplicate generator domain logic or service I/O behavior.
  - Acceptance Criteria:
    - A typed supervisor plan contract lists selected action, workflow, checkpoint/resume stage, idempotency scope/key, retry/defer decision, health inputs, blockers, and expected side effects.
    - The supervisor consumes existing preflight reports, run registry records, retry telemetry, validation failures, checkpoints, and idempotency lookups without performing unplanned side effects.
    - The supervisor can start a new run, resume from the latest safe checkpoint, invoke targeted repair, schedule retry/defer, publish when policy allows, or dead-letter with a remediation reason.
    - Pipeline tests cover fresh, duplicate, partial-checkpoint, validation-failed, transient-failed, missing-credential, and publish-ready scenarios with structured log assertions.

- **Title:** Add a durable autonomous dead-letter queue with typed remediation plans [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Failure classification and UI-run dead-letter concepts exist, but failed autonomous work is not yet represented as a durable queue of remediable work items with retry/defer/repair scheduling.
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
    - Orchestrators check budget before model, browser, OCR, Drive, and WordPress side effects and emit typed budget decisions.
    - The health scorecard consumes final budget usage and reports avoided calls, budget breaches, and override usage.
    - Tests cover normal use, warning thresholds, hard stop, defer, override, and structured log fields.

- **Title:** Add a persistent scheduler for deferred and user-action-required retry decisions [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Retry decisions can classify defer and user-action-required, but there is no durable scheduler that re-enters deferred work when the cooldown expires or prerequisites are fixed.
  - Why implement: Temporary rate limits, endpoint instability, and credential refresh windows should not require manual reruns.
  - Tradeoffs / risks: Scheduler must not become a separate deployable boundary without architecture review; start as a modular-monolith orchestrator.
  - Acceptance Criteria:
    - Scheduled action records include workflow, step, payload reference, earliest/latest run time, retry decision, blocker code, credential/config dependency, and attempt budget.
    - A scheduler orchestrator selects due work, validates preflight, and dispatches through existing orchestrators with idempotency.
    - User-action-required records resume automatically when the required credential/config preflight passes.
    - Tests cover due/not-due selection, credential blocker clearance, max-attempt exhaustion, duplicate suppression, and structured logs.

- **Title:** Promote run health scorecards into production run gates [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Health scorecards and retry telemetry are useful release evidence, but production workflows do not consistently use scorecard outcomes as gates for publish, retry, repair, or operator notification.
  - Why implement: Autonomous execution needs a self-assessment loop that turns run evidence into next actions.
  - Tradeoffs / risks: Gate thresholds must be calibrated to avoid noisy holds while still catching real quality regressions.
  - Acceptance Criteria:
    - Every autonomous workflow writes a run health scorecard artifact with error, retry, validation, latency, cost, benchmark, and retry-telemetry summaries where applicable.
    - Supervisor policy consumes the scorecard to allow publish, schedule retry, invoke repair, or notify operators.
    - Scorecard thresholds are configurable and logged with policy version.
    - Tests cover passing, warning, failing, missing-evidence, and threshold-override scorecards.

- **Title:** Add model fallback policies by failure class and artifact family [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Model selection is mostly namespace-static, so the system cannot automatically switch to cheaper models for easy work or stronger/different models for repeated schema or validation failures.
  - Why implement: Policy-driven fallback can reduce cost on easy tasks and rescue difficult artifacts without user intervention.
  - Tradeoffs / risks: Fallback must preserve reproducibility and must be forbidden when policy requires same-model replay.
  - Acceptance Criteria:
    - YAML fallback policy maps artifact family and failure class to model tier, temperature, max attempts, schema compatibility, and reproducibility constraints.
    - Fallback decisions are orchestrator-visible, bounded, logged, and included in cost/health evidence.
    - Generators continue to consume one typed LLM response contract.
    - Tests cover cheap-primary success, schema-failure fallback, validation-failure fallback, fallback exhaustion, reproducibility-forbidden fallback, and cost reporting.

    - Tests cover attachment, ZIP attachment, body-link, stale-evidence, and conflict paths with structured log assertions.

- **Title:** Auto-skip or route business-domain-only gated forms before mailbox polling [Impact: 4/5, Effort: 2/5]
  - Problem fixed: Several live gated publishers reject non-business delivery addresses before a report email can be requested, and a 2026-07-06 BigCommerce rerun proved browser identity email drift from the IMAP mailbox can turn a deliverable route into `blocked_email_domain` until corrected.
  - Why implement: Converts repeated external constraints and local identity/mailbox drift into fast, unattended route policy so the system avoids doomed submissions and spends browser budget on publishers where delivery is possible.
  - Tradeoffs / risks: The blocker must be evidence-backed and publisher-scoped with TTL so a future accepted mailbox or changed form does not stay permanently suppressed.
  - Acceptance Criteria:
    - `blocked_email_domain` outcomes persist publisher-scoped route policy with observed field label, host, and evidence timestamp.
    - Browser identity delivery email, work/professional email fields, and mailbox IMAP user are preflighted for domain alignment before email-form submission.
    - Future same-publisher gated candidates fail fast as typed `email_required / blocked_email_domain` unless an eligible configured business-domain mailbox is available.
    - Workflow-control reports avoided browser launches and skipped mailbox polls for the policy decision.
    - Live verification covers at least one publisher already observed with `blocked_email_domain` and shows reduced runtime without an operator step.
    - Tests cover policy TTL expiry, mailbox-availability override, exact-URL versus publisher-scope behavior, and required structured logs.

- **Title:** Learn and apply safe required-select identity values from live gated-form evidence [Impact: 5/5, Effort: 3/5]
  - Problem fixed: The 2026-07-04 database-derived email-route matrix blocked 4 of 10 tested publishers on required enum/select fields whose option sets were visible but not represented in the configured identity profile. The 2026-07-05/2026-07-06 second publisher set repeated the same high-impact blocker on Adobe's required State lookup after the route otherwise completed cleanly as `email_delivery / email_required`.
  - Why implement: Turns repeated manual publisher-form configuration into unattended, evidence-backed acquisition improvements, raising success rate without operator intervention.
  - Tradeoffs / risks: The system must only auto-select semantically safe values from allowlisted identity families and must fail closed for regulated, role-sensitive, or materially false options.
  - Acceptance Criteria:
    - Required enum blockers persist observed option sets, field labels, host, URL, and classifier confidence as structured acquisition evidence.
    - A config generator proposes host-scoped identity overrides only for allowlisted safe families such as company size, revenue band, country, industry, department, and organization type.
    - Proposed values require deterministic semantic matching to existing identity facts or approved default policies; unresolved sensitive fields remain `blocked_unknown_required_enum`.
    - Accepted overrides are written through the existing identity config service path with idempotent diffs, structured logs, and no secrets in YAML.
    - Live verification reruns at least three previously blocked publishers and demonstrates increased acquired or email-requested outcomes without increasing false submissions.
    - Tests cover option-set persistence, safe-family matching, sensitive-field refusal, config diff idempotency, and required structured logs.

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

- **Title:** Add model-call audit replay and drift comparison command [Impact: 4/5, Effort: 2/5]
  - Problem fixed: Model-call audit records are now emitted, but operators still need a first-class command to reconstruct replay bundles and compare prompt/model/schema/cache drift without making provider calls by default.
  - Why implement: Replayable audit review shortens debugging of model regressions and makes prompt or schema drift visible before costly reruns.
  - Tradeoffs / risks: Replay output must preserve redaction and must require explicit opt-in before any live provider call.
  - Acceptance Criteria:
    - CLI reads structured logs or retained audit artifacts and emits a deterministic replay bundle for a selected run/model call.
    - Drift comparison reports prompt hash, rendered-prompt redaction hash, model, seed support, schema version, cache key, validation status, and response ID differences.
    - Live-provider replay is disabled by default and requires an explicit flag plus budget confirmation.
    - Tests cover audit extraction, redacted bundle output, missing audit fields, cache-hit records, and drift comparison.

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

---

# Migrated Simplification Backlog

Migrated from `simplification.md`.

# Simplification Backlog

Last audited: 2026-06-15

This file captures the top simplification, decomplexification, reuse, and removal opportunities found in the current repository state. It intentionally mirrors the concise backlog style of `CONSOLIDATED_TODO.md`: ordered by leverage, measurable before implementation, and constrained by the architectural rules in `AGENTS.md`.

This is an analysis backlog, not an implementation approval. Before any item starts, the owner must confirm current behavior, define a baseline metric or regression fixture, and choose a movement-only or behavior-changing path explicitly.

## Backlog Rules

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

## Current-State Evidence

- `llm_service.py` is the sole OpenAI, OpenRouter, generic LLM-policy, and vector-store provider boundary; the legacy `openai_service.py` facade has been removed.
- Model-client construction is centralized at orchestrator/service-factory boundaries and injected into model-backed generators.
- Large orchestrators, publish workflow surfaces, PDF facade exports, and WordPress render-time intelligence remain broad behavior-preserving refactors.
- Cross-report contract shared vocabulary now belongs to the `_cross_report_analysis` package owner, and `src/contracts/cross_report_analysis.py` remains the documented public contract surface.

## Priority Order

1. Canonical service-boundary simplification.
2. Generator and orchestrator role-boundary cleanup.
3. Low-risk helper reuse and duplicate removal.
4. PDF/visual heuristics compatibility-surface reduction.
5. WordPress and CI/process simplification.

## 2026-06-14 Verification Evidence

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

## 2026-06-15 Retry-Ownership Verification Evidence

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

## 2026-06-16 Model-Client Boundary Verification Evidence

- Generators no longer import `llm_service` provider-policy construction helpers; `tests/test_model_client_injection_boundaries.py` enforces the boundary.
- Orchestrators and service-factory paths now build scoped model clients for report generation, report pipeline execution, cross-report synthesis, recategorization, publisher inventory screening, OCR fallback, and figure captions, then inject those clients into generators.
- Focused regression suite passed: `237 passed`.
- Live verification used existing project PDFs and golden report-analysis artifacts: full report generation produced HTML, OCR fallback produced a one-page OCR PDF, and cross-report synthesis produced a validated artifact with 8 sections.

---

## 1. Canonical Service-Boundary Simplification

- **Title:** Audit top-level service proliferation and demote internal capabilities [Impact: 4/5, Effort: 4/5]
  - Problem fixed: Many top-level service files appear to be internal capabilities rather than true external-system boundaries.
  - Why implement: Makes service ownership easier to discover and reduces peer-boundary confusion.
  - Tradeoffs / risks: Requires careful compatibility facades for public imports.
  - Acceptance Criteria:
    - Every top-level service is classified as an external system boundary, canonical service boundary, or candidate internal capability.
    - Internal capabilities move under private subpackages only when semantic ownership improves.
    - Public imports remain compatible or migration is explicitly approved.

---

## 2. Generator and Orchestrator Role-Boundary Cleanup

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

## 4. PDF and Visual-Heuristics Simplification

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

## 5. WordPress and Frontend Simplification

- **Title:** Split or simplify the large WordPress shortcode class by semantic shortcode ownership [Impact: 4/5, Effort: 4/5]
  - Problem fixed: The shortcode class owns many archive and rendering surfaces, including legacy Signal and Briefing archive renderers.
  - Why implement: Reduces PHP god-class risk and improves runtime testability.
  - Tradeoffs / risks: Requires WordPress runtime harness coverage and compatibility preservation.
  - Acceptance Criteria:
    - Shortcode handlers are grouped by semantic public surface, not arbitrary file size.
    - Shared view-model logic moves to existing builder classes where appropriate.
    - Runtime tests prove current shortcode output remains compatible.

- **Title:** Stop WordPress render-time intelligence synthesis where Python projections should own claims [Impact: 5/5, Effort: 4/5]
  - Problem fixed: WordPress still derives some intelligence/freshness/authority-style UI claims from local content state.
  - Why implement: Keeps analytical claims reproducible from approved pipeline artifacts.
  - Tradeoffs / risks: Requires projection contracts and neutral empty states.
  - Acceptance Criteria:
    - WordPress modules render approved projection data instead of deriving analytical claims from post counts or dates.
    - Missing projections fail closed with neutral UI or admin diagnostics.
    - Tests prove no intelligence claim is invented by WordPress runtime logic alone.

## Near-Term Launch Plan

### Phase 1: Boundary Corrections

- Audit top-level service proliferation and demote internal capabilities.

### Phase 2: Larger Workflow Simplification

- Consolidate publish orchestration surfaces.
- Reduce PDF visual heuristics compatibility exports.
- Simplify WordPress shortcode surfaces.

## Closed or Removed From Simplification Intake

- Implemented items are removed from this file after verification and closure in the consolidated backlog.
- Centralized model-client construction outside generators by moving scoped client construction to orchestrators/service-factory boundaries, adding a generator-boundary test, and verifying with focused tests plus live report-generation, OCR, and cross-report runs.
- Reduced cross-report contract fragmentation by deleting the private one-off `src/contracts/_cross_report_analysis/common.py` owner, moving shared vocabulary into `src/contracts/_cross_report_analysis/__init__.py`, preserving the public `src/contracts/cross_report_analysis.py` facade, and verifying with contract tests, schema/architecture gates, mutation gate, full regression suite, and a live model-backed cross-report generation run.
- Clarified report pipeline entrypoints by documenting the canonical batch, single-file, report-pipeline, report-generation, report-analysis, and `analysis_complete` restart entrypoints; removing the redundant ingest-level `report_generation_orchestrator` injection; and adding ownership tests for routing, direct stage invocation, and documentation. Verification used focused orchestrator tests plus a live existing-PDF report pipeline run and semantic restart canary.
