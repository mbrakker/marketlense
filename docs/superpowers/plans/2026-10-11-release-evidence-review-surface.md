# Release Evidence Review Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing GitHub Actions release-evidence summary show exact tested revision, canonical disposition, bounded issue totals, artifact reference, and safe runtime-corpus scope.

**Architecture:** Extend `scripts/quality/release_evidence_job_summary.py`, which the existing CI job already calls, and keep the release review and CTO collector as authoritative evidence producers. Render only validated scalar metadata, derive a run-page artifact reference from the existing GitHub Actions context, and show unavailable/non-green states when evidence is absent, stale, incompatible, or SHA/run-mismatched. Since upload follows the summary step and expires after 14 days, report artifact availability as unverified. Keep release gates, collection stages, and provider behavior unchanged.

**Tech Stack:** Existing Python CLI, GitHub Actions job summary/artifact context, pytest fixtures.

## Global Constraints

- No new dependencies, services, release gates, evidence producers, pipeline stages, or external provider calls.
- Do not render issue details, source content, prompts, responses, credentials, browser content, or discarded payloads.
- Preserve full canonical release issues in the existing uploaded review artifact.
- Keep R1 Active unless every acceptance criterion has verified evidence.

---

### Task 1: Render a bounded, fail-closed reviewer summary

**Files:**
- Modify: `scripts/quality/release_evidence_job_summary.py`
- Test: `tests/test_workflow_queue_evidence.py`

**Interfaces:**
- `render_release_evidence_job_summary(*, review: dict | None, queue_evidence: dict | None, tested_sha: str, expected_run_id: str | None = None, runtime_evidence: dict | None = None, artifact_url: str | None = None) -> str`
- The summary contains only fixed labels, validated SHA/build identity, integer issue totals, allow-listed corpus labels/states, and a validated HTTPS Actions run-page URL.

- [x] Write failing fixture tests for exact-SHA/run matching and mismatch, failed and absent review/queue inputs, stale/expired/unknown artifact status, each collector corpus scope, incompatible metadata, sensitive issue strings, and output byte bounds.
- [x] Run those focused tests and confirm the new cases fail against the current renderer or workflow condition.
- [x] Implement strict scalar extraction and fail-closed status mapping; omit all issue text and link to the existing run's artifact listing only when the Actions URL is valid.
- [x] Run the focused tests and inspect rendered Markdown from realistic release-review, queue-evidence, and CTO-leakage fixtures.

### Task 2: Keep the existing Actions summary visible for incomplete evidence

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/backlog/R-engineering.md`
- Modify: `docs/quality/evidence.md`
- Modify: `CONSOLIDATED_TODO.md`

- [x] Change only the existing summary step condition so it emits an explicit unavailable result when canonical summary inputs are missing; do not add or reorder processing, upload, provider, or gate steps.
- [x] Document the safe summary fields, canonical artifact reference, runtime-corpus labels, and unavailable behavior without duplicating detailed issues.
- [ ] Record verified R1 implementation scope, focused test results, live-presentation availability, and remaining gaps in the sole status authority; retain Active if upload/expiry or live rendering cannot be verified.

### Task 3: Verify the scoped result and publish the requested commit

**Files:**
- Inspect the complete final diff and changed-file list.

- [x] Run focused tests and applicable documentation/workflow checks; inspect actual fixture-generated summary output and scan it for sensitive fixture markers. Focused tests, Ruff, type check, and repository hygiene pass; documentation and backlog source checks report unrelated pre-existing D13/D14/PATH anchors and closed R6 detailed-ID issues.
- [ ] Inspect the final diff for unrelated changes or sensitive data; report whether live GitHub presentation and artifact-expiry state were observable.
- [ ] Commit the verified scope, push the current branch, and record the resulting SHA.
