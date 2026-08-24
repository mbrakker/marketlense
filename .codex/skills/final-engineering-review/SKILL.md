---
name: final-engineering-review
description: Perform a read-only, evidence-backed final review of significant MarketLense changes with parallel correctness, architecture, and regression reviewers.
---

# Final Engineering Review

Use this Skill only after a **significant** change is implemented and before
the parent agent claims completion. It is a review, not a test runner or
completion gate. The deterministic completion command remains authoritative
for PASS/FAIL.

Significant means a production-code, contract, service, orchestrator, prompt,
configuration, CI, architecture-policy, or multi-file behavioral change. Skip
this Skill for documentation-only, formatting-only, or narrowly mechanical
changes unless the user specifically requests review.

## Inputs and preflight

The parent agent establishes one immutable review snapshot before dispatching:

1. Determine the comparison base and collect `git diff --check`, changed-file
   names, and the complete diff.
2. Read the directly relevant contracts, tests, and policy documents. For
   architecture review, include `AGENTS.md` and
   `docs/quality/architecture_policy.yaml`.
3. Provide every reviewer the same base revision, changed-file list, diff, and
   acceptance criteria. Do not ask reviewers to repair anything.

If the base or diff is unavailable, report the review as unverified. Do not
infer findings from an incomplete snapshot.

## Reviewer dispatch

Launch exactly these three independent reviewers concurrently when the current
Codex surface supports parallel agents. Use the `marketlense-delegation`
Explorer controls for their read-only scope and native-limit handling; otherwise
run them sequentially while keeping the same inputs and isolation. Do not add
reviewer roles unless a recorded benchmark result shows they improve useful
findings without increasing false positives.

Every reviewer receives this non-negotiable instruction:

> You are a read-only reviewer. Do not edit, create, delete, stage, commit, or
> format files; do not run tests or commands with side effects; do not make
> external writes. Inspect the supplied snapshot and repository evidence only.
> Return findings using the contract in `references/finding-contract.md`. Return
> an empty list when no high-confidence actionable finding is supported.

Give each reviewer only its own responsibility:

1. **Correctness** — Inspect introduced bugs, broken contracts, state
   transitions and error handling, wrong side effects, and concrete edge
   failures. Require an observable failure path.
2. **Architecture and simplicity** — Inspect `AGENTS.md` and architecture
   policy compliance, responsibility and I/O placement, duplicate
   external-system boundaries, speculative abstractions, unnecessary
   complexity, and unrelated refactoring.
3. **Regression and testing** — Inspect missing behavioral tests, unverified
   side effects, backward-compatibility risk, incomplete acceptance evidence,
   and tests that do not prove the changed behavior.

## Parent synthesis

The parent agent alone receives the three reports and may later apply repairs.
It must not pass raw reviewer output through unfiltered.

1. Verify every cited path and line against the review snapshot. Reject a
   finding with missing, stale, or ambiguous evidence.
2. Mark each finding `introduced`, `pre_existing`, or `uncertain` by comparing
   it with the base diff. Suppress `pre_existing` and `uncertain` findings from
   the final report; they are not completion blockers for this change.
3. Retain only findings at or above 85 confidence with a specific consequence
   and a credible reproduction, contract, policy, or missing-proof basis.
4. Deduplicate reports describing the same changed lines and underlying cause.
   Keep the clearest evidence and the highest confidence; preserve all relevant
   reviewer labels internally.
5. Return only the resulting high-confidence actionable findings, ordered by
   severity then confidence. If none survive, state: `No high-confidence
   introduced findings.` This is not a PASS declaration.

Use the historical evaluator only for controlled Skill assessment, not for an
ordinary code review:

```powershell
python scripts/quality/final_engineering_review_benchmark.py validate --corpus benchmarks/agent-engineering/final-engineering-review.json
python scripts/quality/final_engineering_review_benchmark.py score --corpus benchmarks/agent-engineering/final-engineering-review.json --run-record <review-run.json>
```

See `references/finding-contract.md` for required evidence and the evaluator
record. The benchmark data is evaluator-owned; do not disclose its accepted
findings to a reviewer working a historical case.
