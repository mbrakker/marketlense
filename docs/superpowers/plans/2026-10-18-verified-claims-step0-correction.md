# Verified Claims Step 0 Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Correct the Step 0 reference-case identity semantics and make all 15 PDF-verified cases reusable as precise factual evaluation fixtures without changing production behavior.

**Architecture:** Extend the existing Step 0 JSON in place. Keep independently assigned source-reference IDs, persisted findings/doc-map IDs and downstream editorial IDs in separate fields; leave unavailable bindings unresolved. Add compact candidate mutations and expected results to the same cases, and update the existing baseline report/backlog evidence with exact verification commands and portability limitations.

**Tech Stack:** Existing retained JSON artifacts, PyMuPDF-rendered source-page evidence, Python/PowerShell hash checks, Markdown/JSON, pytest and repository CI documentation/hygiene gates.

## Global Constraints

- Work only on codex/fix-retained-insight-evidence-validation at starting SHA cdc7ae2bb01ef257d3f5f4666801f8be37234352.
- Use only the frozen five-report manifest with SHA-256 744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7.
- Preserve case IDs ACT-001 through ADJ-001 and all source meanings and qualifiers.
- Do not mix the October 16–17 archive, run paid calls, publish, overwrite source artifacts or add raw PDFs/prompts/model responses.
- Do not change production source, prompts, model settings, validators, Step 1 selection or Step 2 factualisation logic.
- Do not introduce a claims database, fixture service or new artifact-storage mechanism.

---

### Task 1: Resolve evidence identities

**Files:**
- Read: docs/quality/verified-claims-step0-reference-cases-20261018.json
- Read: frozen retained report_analysis/findings.json, doc_map.json and artifacts.json
- Modify: docs/quality/verified-claims-step0-reference-cases-20261018.json

- [x] Build a report-scoped inventory of persisted finding IDs, doc-map IDs and selected editorial IDs from the retained output.
- [x] Replace mixed source-reference values with separate source_reference_ids, canonical persisted bindings and editorial_ids.
- [x] Mark unavailable exact bindings unresolved; never synthesize an ID.
- [x] Run a binding resolver check for report, statement and physical-page consistency.

### Task 2: Add evaluation-ready candidate fixtures

**Files:**
- Modify: docs/quality/verified-claims-step0-reference-cases-20261018.json

- [x] Add structured source_truth fields for metric, unit, comparison, population, denominator, geography, period, status, page and chart/section identity where material.
- [x] Add one valid candidate and precise incorrect or ambiguous candidates with mutation descriptions, expected results and corrected statements.
- [x] Cover every mandatory Activate, Adjust, Capgemini, KPMG and Reuters failure category while keeping the top-level case count at 15.
- [x] Validate supported, unsupported and unresolved outcome semantics, including supported corrections.

### Task 3: Make page and artifact reuse auditable

**Files:**
- Read: frozen PDFs and existing retained artifact hashes
- Modify: docs/quality/verified-claims-step0-baseline-20261018.md

- [x] Record physical, printed and zero-based page conventions and the minimum chart/legend/footnote identity needed by each case.
- [x] Record committed versus ignored-local versus unavailable artifact status for each report.
- [x] Record the retained producer/run IDs, artifact paths and hashes needed to reconstruct later checks.
- [x] Preserve explicit limitations for missing report-level attribution and local-only artifacts.

### Task 4: Verify and reconcile canonical evidence

**Files:**
- Modify: docs/quality/verified-claims-step0-baseline-20261018.md
- Modify: docs/backlog/E-evidence.md
- Modify: CONSOLIDATED_TODO.md

- [x] Run JSON, case-count, identity, source-hash, page-coverage and candidate-outcome checks.
- [x] Run focused PDF/editorial tests and repository backlog/documentation/hygiene gates without provider calls or external writes.
- [x] Record exact commands and observed results; distinguish new evidence from pre-existing historical failures.
- [x] Leave E18 Active and document any remaining blockers.

### Task 5: Final scope review, commit and push

**Files:**
- Read: final staged diff and committed-file inventory

- [x] Confirm no production source, prompt, configuration, validator, raw PDF, credential or sensitive artifact changed.
- [x] Commit the correction on the requested branch with a focused documentation/evidence message.
- [x] Push the branch and verify local and remote commit SHA agreement.
- [x] Report PASS, PARTIAL or FAIL for Step 0 readiness and stop before Step 1.
