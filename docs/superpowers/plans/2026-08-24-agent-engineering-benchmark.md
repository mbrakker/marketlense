# MarketLense Agent-Engineering Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reproducible, evidence-traceable corpus for evaluating coding agents on representative MarketLense engineering work without changing production behavior.

**Architecture:** Keep the corpus declarative in one versioned JSON file beneath `benchmarks/agent-engineering/`, with case-level historical provenance, evaluation criteria, and scoring weights. Add one MarketLense-specific quality script that validates the corpus and normalizes recorded agent-run telemetry into deterministic scores; it is not a general benchmarking framework. Store the committed baseline as a reproducible result artifact under the corpus directory and document the workflow in the existing benchmark methodology page.

**Tech Stack:** Python standard library, pytest, JSON, existing MarketLense quality/evidence conventions.

## Global Constraints

- Preserve production-code behavior; the change may affect only benchmark, test, and quality-documentation surfaces.
- Include 15–20 representative historical MarketLense cases across every requested work category.
- Keep task prompts free of intended file names, implementation strategies, and other solution leakage.
- Trace each ground-truth component to a repository commit and retained test/check/evidence source.
- Correctness is the dominant weighted metric; score telemetry deterministically where present and mark unavailable telemetry explicitly.
- The baseline command must be safe, local, deterministic, and must not invoke providers, browsers, email, publishing, or external writes.

---

### Task 1: Define the evidence-backed benchmark corpus

**Files:**
- Create: `benchmarks/agent-engineering/cases.json`
- Create: `benchmarks/agent-engineering/README.md`

**Interfaces:**
- Consumes: committed repository history, `AGENTS.md`, `docs/quality/service_boundary_map.json`, existing tests, quality scripts, and retained evidence.
- Produces: a JSON object with schema version, scoring defaults, telemetry contract, and 16 case records keyed by stable IDs.

- [x] **Step 1: Write the failing corpus-validation test**

```python
def test_agent_engineering_corpus_has_traceable_representative_cases() -> None:
    report = validate_corpus(ROOT / "benchmarks/agent-engineering/cases.json")
    assert report["passed"] is True
    assert report["case_count"] == 16
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_agent_engineering_benchmark.py::test_agent_engineering_corpus_has_traceable_representative_cases`

Expected: FAIL because the corpus validator and corpus do not yet exist.

- [x] **Step 3: Add the corpus and reader guide**

Create 16 concise cases whose prompts contain only the observed task request and whose separate ground truth names the historical commit, relevant files, fixtures, and verification commands. Define case-level correctness, discovery, scope, and verification weights that sum to 100 and make correctness at least 60.

- [x] **Step 4: Run the focused test**

Run: `python -m pytest -q tests/test_agent_engineering_benchmark.py::test_agent_engineering_corpus_has_traceable_representative_cases`

Expected: PASS with 16 valid cases across all required categories.

### Task 2: Add deterministic MarketLense benchmark validation and scoring

**Files:**
- Create: `scripts/quality/agent_engineering_benchmark.py`
- Create: `tests/test_agent_engineering_benchmark.py`

**Interfaces:**
- Consumes: `cases.json`; optional JSON agent-run record using its documented telemetry fields.
- Produces: a JSON validation/baseline report with case coverage, provenance checks, telemetry availability, deterministic per-case scores, and aggregate correctness-first score.

- [x] **Step 1: Extend the failing test for score semantics**

```python
def test_score_run_penalizes_scope_and_preserves_unavailable_measurements() -> None:
    report = score_run(corpus, run_record)
    assert report["aggregate"]["correct_completion"] == 1.0
    assert report["aggregate"]["irrelevant_files_modified"] == 1
    assert report["aggregate"]["token_usage_status"] == "unavailable"
```

- [x] **Step 2: Run the focused test to verify it fails**

Run: `python -m pytest -q tests/test_agent_engineering_benchmark.py::test_score_run_penalizes_scope_and_preserves_unavailable_measurements`

Expected: FAIL because the scoring entrypoint is not yet implemented.

- [x] **Step 3: Implement only the corpus-specific validator and scorer**

Validate IDs, coverage, score weights, prompt leakage markers, historical commit resolution, existing ground-truth paths, and executable verification commands. Score submitted run records using the committed case metadata; do not attempt to execute agents or introduce an agent-provider abstraction.

- [x] **Step 4: Run the focused tests**

Run: `python -m pytest -q tests/test_agent_engineering_benchmark.py`

Expected: PASS.

### Task 3: Capture the baseline and document the current workflow

**Files:**
- Create: `benchmarks/agent-engineering/baselines/codex-current.json`
- Modify: `docs/quality/benchmarks.md`

**Interfaces:**
- Consumes: the corpus and quality script.
- Produces: a repository-revision-bound corpus baseline and a canonical command that can be rerun by an operator.

- [x] **Step 1: Run the corpus baseline command**

Run: `python scripts/quality/agent_engineering_benchmark.py baseline --corpus benchmarks/agent-engineering/cases.json --output benchmarks/agent-engineering/baselines/codex-current.json`

Expected: exit 0; JSON includes 16 cases, all required categories, resolved history/path provenance, and an explicit `not_executed` agent-performance state rather than invented telemetry.

- [x] **Step 2: Write the current benchmark documentation**

Add the exact baseline and scoring commands, safe-worktree setup, input-record contract, reproducibility limits, and result interpretation to `docs/quality/benchmarks.md`.

- [x] **Step 3: Run final targeted validation**

Run: `python -m pytest -q tests/test_agent_engineering_benchmark.py tests/test_documentation_validation.py`

Expected: PASS.

- [x] **Step 4: Inspect the final change set**

Run: `git diff --check && git diff -- benchmarks/agent-engineering scripts/quality/agent_engineering_benchmark.py tests/test_agent_engineering_benchmark.py docs/quality/benchmarks.md`

Expected: no whitespace errors; no production-source changes; corpus and baseline are traceable.
