# Agent Completion Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one deterministic MarketLense command that produces PASS/FAIL completion evidence from the working-tree diff and existing quality checks.

**Architecture:** `scripts/quality/agent_completion_gate.py` will inspect `git diff HEAD` plus untracked files, classify paths with explicit repository-owned rules, select only existing focused checks, and invoke `scripts/ci/run_quality_gate.py` only for deterministic high-risk escalation. It reports structured JSON with a concise summary; no LLM, provider, Claude Code component, or production import participates in the decision.

**Tech Stack:** Python standard library, Git CLI, existing CI scripts, pytest, ruff, mypy.

## Global Constraints

- Reference Claude Code lifecycle/completion concepts only; do not vendor, copy, or depend on Claude Code.
- Reuse `scripts/ci/run_quality_gate.py` for aggregate verification; do not recreate its command sequence.
- A required command failure, no-change invocation, unverified escalation, or working-tree mutation during checks makes PASS impossible.
- Focused changes run focused checks; changes under CI/policy/dependency/external-boundary paths escalate to the canonical aggregate quality gate.
- The gate adds no production runtime dependency and no source code under `src/`.

---

### Task 1: Define deterministic classification and selection

**Files:**
- Create: `tests/test_agent_completion_gate.py`
- Create: `scripts/quality/agent_completion_gate.py`

**Interfaces:**
- Consumes: repository-relative changed paths.
- Produces: `classify_changes(paths)` and `select_checks(classification, paths)` returning immutable structured data.

- [x] **Step 1: Write failing classification/selection tests**

```python
def test_classifies_service_changes_as_high_risk() -> None:
    classification = classify_changes(("src/services/file_service.py",))
    assert classification.full_gate_required is True
    assert "service_boundary" in classification.subsystems
```

- [x] **Step 2: Run the new test to verify RED**

Run: `python -m pytest -q tests/test_agent_completion_gate.py`

Expected: FAIL because the completion-gate module does not exist.

- [x] **Step 3: Implement the minimal path classifier and check selector**

```python
def classify_changes(paths: tuple[str, ...]) -> ChangeClassification:
    ...

def select_checks(
    classification: ChangeClassification, paths: tuple[str, ...]
) -> tuple[Check, ...]:
    ...
```

- [x] **Step 4: Verify GREEN**

Run: `python -m pytest -q tests/test_agent_completion_gate.py`

Expected: PASS.

### Task 2: Execute checks and emit completion evidence

**Files:**
- Modify: `scripts/quality/agent_completion_gate.py`
- Modify: `tests/test_agent_completion_gate.py`

**Interfaces:**
- Consumes: selected `Check` records and a command runner.
- Produces: report fields `result`, `changed_files`, `selected_checks`, `tests_run`, `failures`, `unverified_requirements`, and `full_gate_required`.

- [x] **Step 1: Write failing execution and escalation tests**

```python
def test_failed_required_check_prevents_pass() -> None:
    report = build_completion_report(...)
    assert report["result"] == "FAIL"

def test_high_risk_selection_includes_canonical_aggregate_gate() -> None:
    checks = select_checks(classify_changes(("AGENTS.md",)), ("AGENTS.md",))
    assert checks[-1].command == ("python", "scripts/ci/run_quality_gate.py")
```

- [x] **Step 2: Run the test to verify RED**

Run: `python -m pytest -q tests/test_agent_completion_gate.py`

Expected: FAIL because execution/reporting functions do not exist.

- [x] **Step 3: Implement Git inspection, subprocess execution, integrity comparison, and JSON output**

```python
def main() -> int:
    changed_files = discover_changed_files(ROOT)
    classification = classify_changes(changed_files)
    report = run_completion_gate(...)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["result"] == "PASS" else 1
```

- [x] **Step 4: Verify GREEN**

Run: `python -m pytest -q tests/test_agent_completion_gate.py`

Expected: PASS.

### Task 3: Document and verify the canonical lifecycle command

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/quality/testing.md`
- Modify: `docs/quality/release-gates.md`

**Interfaces:**
- Consumes: completion-gate JSON report.
- Produces: one documented command and the rule that deterministic execution—not an LLM—decides completion.

- [x] **Step 1: Reuse existing documentation validation**

The existing documentation validator covers the command and links; no duplicate
command-specific validator is needed.

- [x] **Step 2: Document the command and high-risk escalation policy**

```powershell
python scripts/quality/agent_completion_gate.py
```

- [x] **Step 3: Run focused validation**

Run: `python -m pytest -q tests/test_agent_completion_gate.py tests/test_documentation_validation.py`

Expected: PASS.

- [x] **Step 4: Run the completion gate and aggregate gate required by this policy/agent-instruction change**

Run: `python scripts/quality/agent_completion_gate.py`

Observed: the completion gate emitted `FAIL` because the canonical aggregate
runner stopped at the existing full-repository mypy baseline gate with eleven
unbaselined errors in browser-download/report-download modules outside this
change. Focused checks and working-tree integrity passed; the unrelated type
baseline was not changed or weakened.

- [x] **Step 5: Commit and push after final diff review**

```bash
git add AGENTS.md docs/quality/testing.md docs/quality/release-gates.md \
  scripts/quality/agent_completion_gate.py tests/test_agent_completion_gate.py \
  docs/superpowers/plans/2026-08-24-agent-completion-gate.md
git commit -m "feat: add deterministic agent completion gate"
```
