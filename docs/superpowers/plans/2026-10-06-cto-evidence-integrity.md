# CTO Evidence Integrity Implementation Plan

> **For agentic workers:** Execute inline in this session, following the checklist task by task.

**Goal:** Make exact repository SHA evidence cover every run or candidate source and prevent metric names from proving specialized evidence classes.

**Architecture:** Keep the evidence qualification change in the canonical CTO projector. Track source SHA binding while projecting declared run sources, and let format adapters declare semantic evidence classes explicitly while preserving numeric metrics. Let bundle parsing accept the projected comparison fields already emitted by the canonical serializer while keeping declared manifests strict by default.

**Tech Stack:** Python, pytest, the existing CTO evidence contracts and retained artifacts.

## Global Constraints

- Preserve the public CTO evidence contract and fail-closed behavior.
- Keep declared-run manifest parsing strict by default and make no schema change.
- Reuse the existing SHA extraction logic and source references.
- Do not remove useful numeric measurements or refactor the large projector broadly.
- Keep run evidence distinct from historical state and preserve comparison semantics.
- Leave pre-existing workflow queue edits unstaged and unchanged.

---

### Task 1: Require SHA binding from every contributing run or candidate source

**Files:**
- Modify: `tests/test_cto_evidence_projection.py`
- Modify: `scripts/quality/_cto_review_evidence/run_projection.py`

**Interfaces:** Use existing `_embedded_tested_sha`, source references, `run.tested_repository_sha`, and comparison endpoints.

- [x] Add regressions for two bound sources (declared and embedded proof), a bound run plus unbound candidate, a contradictory embedded SHA, and an unbound supporting source.
- [x] Run the new SHA tests and confirm the unbound candidate is incorrectly masked by the current behavior.
- [x] Accumulate binding status across evidence-contributing `run` and `candidate` sources; add `exact_repository_sha` only when all relevant sources prove the expected SHA.
- [x] Rerun the SHA regressions and projection tests; preserve contradictory SHA invalidation.

### Task 2: Qualify specialized evidence by adapter semantics

**Files:**
- Modify: `tests/test_cto_evidence_projection.py`
- Modify: `scripts/quality/_cto_review_evidence/run_projection.py`

**Interfaces:** Preserve `_project_numeric` metric emission and the current per-format adapter dispatch.

- [x] Add regressions for generic cost and provider-timing metric names, provider-profile capabilities, and representative crop-QA, editorial, WordPress, and specialized producer capabilities.
- [x] Run the new regressions and confirm metric-name inference currently satisfies unsupported classes.
- [x] Remove name based capability inference; retain generic `measurements` and explicitly typed generic subject, outcome, attempt, and reuse classes.
- [x] Declare supported classes only in the corresponding typed adapters and preserve metrics.
- [x] Rerun projector and contract tests.

### Task 3: Validate retained evidence and quality gates

**Files:**
- Modify: `src/contracts/cto_evidence.py`
- Modify: `tests/test_cto_evidence_projection.py`
- Read: existing retained run manifests and producer artifacts; write only generated bundles to a fresh temp directory.

- [x] Add a bundle comparison roundtrip regression, confirm it fails because projected fields are rejected, and make bundle parsing accept those fields while retaining strict manifest parsing by default.
- [x] Run the focused projector, contract, export reliability run-scope, and contract roundtrip tests.
- [x] Run formatting, lint, and the repository type gate.
- [x] Project real retained frozen-five and artifact-DAG inputs through the canonical projector without rewriting source evidence.
- [x] Parse the written bundles and inspect SHA coverage, evidence class availability, unavailable metrics, disposition, historical-state separation, comparison direction and attribution, and prohibited content.

### Task 4: Commit and push the scoped change

**Files:** Commit only this plan, the projector, CTO bundle contract parser, and projection tests.

- [x] Inspect the final diff and stage only task files; unrelated in-progress edits stayed unstaged.
- [x] Commit on `main` and push the resulting changes to `origin/main`; verification record reached `origin/main` on 2026-10-07.
- [x] Report exact test/check outcomes, retained evidence inputs and bundle outcomes, and commit SHA in the final response.

## Verification results

The projection used committed code at `67aaec2ac1a63ee8e39d754949f8429321b57ec3` and the existing manifests under `out/cto_evidence_retained_projections/`.

| Retained case | Input artifact | Completeness / disposition | Run metrics | Other checks |
|---|---|---|---:|---|
| Frozen five | `docs/quality/reliability-cohort-20261001-next-five/cohort_result.json` | `complete` / `not_evaluated`; no required criteria were declared | 47 total; 35 unavailable values remain null | One run source pinned and bound by declared and embedded SHA; historical state is separate |
| Artifact DAG | `docs/quality/artifact-dag-latency-benchmark-20261006.json` | `complete` / `not_evaluated`; no required criteria were declared | 158 | Baseline and candidate sources pinned and endpoint-bound; 17 deltas verified as candidate minus baseline; `causal_attribution=not_established` |

Both written bundles passed contract roundtrip, had no unavailable required classes, and passed the identity, source-text-field, credential, email, and URL scans. Historical state remained partial with one metric in each bundle and stayed separate from run evidence.

Focused validation: `python -m pytest -q tests/test_cto_evidence_projection.py tests/test_cto_evidence_contract.py tests/test_export_reliability_run_scope.py tests/contracts/test_contract_roundtrip.py` — 2,297 passed. Ruff format and lint passed for the three touched Python files. `python scripts/ci/run_type_check.py` passed across 769 source files with zero tracked errors. A direct targeted mypy invocation on the projector and test file reported only diagnostics reproduced against their pre-change `HEAD` versions; the repository type gate remains the authoritative passing type result.
