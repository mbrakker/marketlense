# Acquisition Failure Remediation Implementation Plan

> **For agentic workers:** Execute inline in this isolated worktree; every code change requires a failing focused test, a replay of only the frozen failed candidate cohort, and retained evidence.

**Goal:** Reproduce, decompose, and remediate the exact failed-acquisition candidates from the 2026-08-12 reliability run without acquiring replacement sources.

**Architecture:** Use the retained reliability SQLite snapshots and evidence bundle as the immutable input. Freeze an acquisition-only manifest, replay the cohort through the existing acquisition orchestrator with a new isolated state namespace, then make only evidence-supported corrections in the existing planner, browser identity, mailbox, verification, or telemetry boundaries.

**Tech Stack:** Python, SQLite, existing MarketLense acquisition/orchestration services, controlled browser and mailbox integrations, CSV/JSON evidence.

## Global Constraints

- Never rediscover a replacement candidate or reacquire a verified-successful source.
- Never publish to WordPress during this remediation run.
- Treat native PDF, onsite HTML, email-delivered PDF, and browser-captured content as distinct artifact classes.
- Stop a candidate only after verified persistence or a well-evidenced typed external/operator blocker.
- Commit fixes separately from generated evidence.

### Task 1: Freeze and validate the failed-acquisition cohort

**Files:**
- Create: `docs/CTO_evidence/acquisition_failure_remediation_<run_id>/failed_acquisition_manifest.json`
- Create: `docs/CTO_evidence/acquisition_failure_remediation_<run_id>/runtime_provenance.json`

- [ ] Extract failed terminal acquisition records from the retained reliability reports/state databases and retain source, route, identity, artifact, timing, configuration, and producer provenance.
- [ ] Deduplicate only by stable candidate/source identity; retain every original route attempt under each frozen member.
- [ ] Hash the manifest and validate that every member has one original terminal acquisition outcome and no successful verified artifact.

### Task 2: Diagnostic replay and failure decomposition

**Files:**
- Create: `acquisition_attempts.jsonl`, `acquisition_attempts.csv`, `artifact_verification.csv`
- Create: `acquisition_failure_decomposition.csv`, `acquisition_failure_pareto.csv`

- [ ] Run every frozen candidate on the same configuration/policy SHA in a fresh isolated namespace before changing production code.
- [ ] Retain per-attempt route, timing, bounded HTTP/browser/mailbox/LLM evidence, and a typed terminal state.
- [ ] Produce a one-row-per-candidate decomposition and Pareto, separating confirmed root causes, inferences, and hypotheses.

### Task 3: Implement evidence-supported general fixes

**Files:**
- Modify only the existing acquisition planner, browser identity/form, mailbox closure, artifact verification, or evidence exporter module proven by Task 2.
- Test: focused existing acquisition/browser/mailbox/verification test modules.

- [ ] Write a failing focused regression test for one confirmed root cause.
- [ ] Implement the smallest general correction without publisher-specific personal data, broad retry expansion, or validation weakening.
- [ ] Run the focused test and relevant acquisition regression suite before considering a second fix.

### Task 4: Fixed-cohort replay and evidence closure

**Files:**
- Create: route/funnel/cost/latency/before-after/remaining-failure CSVs, `test_results.json`, `evidence_consistency.json`, `README.md`.

- [ ] Replay only the immutable frozen cohort after local fixes.
- [ ] Verify every artifact and assign each frozen member exactly one terminal state.
- [ ] Calculate unique-candidate KPIs separately from attempt counters, validate funnel monotonicity, and commit evidence separately from code.
