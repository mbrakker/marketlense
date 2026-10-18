# Verified Claims Step 0 Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish an independently auditable factual, editorial, and performance baseline for the exact frozen five-report cohort before implementing verified-claims stages 1–7.

**Architecture:** Reuse the pinned cohort manifest, original retained PDFs, existing evidence packs, report artifacts, validation records, and telemetry. Persist only a concise Markdown baseline report and a structured JSON reference set under `docs/quality/`; do not add a claims store, service, validator, model call, or production behavior.

**Tech Stack:** PowerShell and Git for identity/integrity checks; existing MarketLense retained JSON/Markdown artifacts; SHA-256/MD5 hashing; Markdown and JSON evidence records; focused repository integrity checks.

## Global Constraints

- Work only on `codex/fix-retained-insight-evidence-validation`, starting from the verified branch SHA.
- Verify exactly the five PDFs in `docs/quality/reliability-cohort-20261001-next-five/frozen_cohort.json`.
- Match manifest SHA-256 `744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7`.
- Do not change production logic, prompts, configuration, quality gates, or the established frozen baseline.
- Do not mix the 2026-10-16–17 ingest archive into the frozen-five comparison.
- Do not run paid model calls, publish, overwrite retained evidence, or commit raw PDFs, credentials, or sensitive provider artifacts.
- Keep unavailable source/evidence explicit; do not infer source facts from OCR or secondary summaries alone.
- Update `CONSOLIDATED_TODO.md` and `docs/backlog/E-evidence.md` only when the verified audit supplies current evidence or an actionable gap.

---

### Task 1: Pin branch, cohort, and retained-artifact identity

**Files:**
- Read: `docs/quality/reliability-cohort-20261001-next-five/frozen_cohort.json`
- Read: `docs/quality/reliability-cohort-20261001-next-five/README.md`
- Read: `docs/quality/reliability-cohort-20261001-next-five/before_cohort_result.json`
- Read: `docs/quality/reliability-cohort-20261001-next-five/cohort_result.json`

- [x] Confirm the exact branch, starting SHA, clean starting tree, manifest hash, five members, source paths, and manifest MD5 values.
- [x] Resolve each source path and compute available-file SHA-256/MD5 without changing files; record missing or mismatched files as open evidence gaps.
- [x] Inventory the retained evidence directories and identify the best comparable editorial producers, exact producer SHAs, run IDs, and cache/replay limitations.

### Task 2: Audit report-level evidence and editorial flow

**Files:**
- Create: `docs/quality/verified-claims-step0-baseline-20261018.md`
- Read: retained evidence packs, candidate/final editorial artifacts, validation and retained-claim records for each frozen report

- [x] For each report, trace source identity → findings/evidence pack → selected candidates → source-page references → evidence-fidelity result → final Insights/Summary/Expert View/Key Figures/distribution copy → retained-claim validation.
- [x] Record preserved, changed, duplicated, misinterpreted, omitted, and rejected facts separately from unavailable evidence.
- [x] Keep report-level results separate from aggregate cohort measurements and distinguish the frozen baseline from the October diagnostic ingest archive.

### Task 3: Build the factual reference cases

**Files:**
- Create: `docs/quality/verified-claims-step0-reference-cases-20261018.json`
- Read: original PDF pages and corresponding retained evidence/artifacts

- [x] Add supported and defective cases covering Activate forecast/observation, video/audio cohort and metric-label inversions; Adjust casino and slots installs/sessions; Capgemini switching behaviour, populations, and denominators; KPMG qualitative/comparative findings; and Reuters AI-search forecast/referral figures.
- [x] For every case, record canonical evidence ID when available, PDF identity, exact source page, source-supported meaning, qualifiers, candidate/editorial statement, defect classification, expected verification outcome, and independent-confirmation state.
- [x] Inspect the original rendered page for each case; mark any case that cannot be independently confirmed as `requires_review` rather than treating OCR/model output as source truth.

### Task 4: Capture editorial and performance baselines

**Files:**
- Modify: `docs/quality/verified-claims-step0-baseline-20261018.md`
- Read: `docs/quality/frozen-five-systematic-fixes-baseline-20261005.json`
- Read: `docs/quality/frozen-five-autonomous-mvp-comparison-20261009.md`
- Read: applicable retained telemetry and report artifacts

- [x] Preserve exact run identities and producer SHAs for the best comparable historical outputs.
- [x] Capture only supported measures: topic coverage, factual errors, unsupported claims, duplication, distinctive insights, analytical quality, readiness, repairs, wall-clock, provider calls, tokens, and cost.
- [x] Label stochastic-run comparisons, cohort-level-only measures, unavailable fields, and pre-existing failures explicitly; do not invent report-level attribution.

### Task 5: Define the reusable Steps 1–7 comparison protocol and reconcile backlog evidence

**Files:**
- Modify: `docs/quality/verified-claims-step0-baseline-20261018.md`
- Modify: `docs/backlog/E-evidence.md`
- Modify: `CONSOLIDATED_TODO.md`

- [x] Define exact five-PDF identity binding and deterministic replay versus stochastic-run comparison semantics.
- [x] Define measures for factual correctness, false acceptance/rejection, important-topic retention, usefulness, reliability, time, cost, repairs, and provenance.
- [x] Update E18 evidence/status notes only with verified current-HEAD results; leave the outcome Active and identify residual gaps.

### Task 6: Validate, inspect, commit, and push the Step 0 evidence

**Files:**
- Read: final diff and new JSON/Markdown evidence

- [x] Run JSON parsing, manifest/hash integrity, repository hygiene, documentation/backlog checks, and focused PDF/editorial evidence checks that do not trigger model calls or external writes.
- [x] Inspect the final report and reference cases for source-page coverage, secret/raw-artifact exposure, exact SHA/run identity, and scope.
- [x] Commit the coherent Step 0 evidence slice on the intended branch, push that branch, and report the resulting commit SHA, passed/open acceptance checks, and residual gaps.
