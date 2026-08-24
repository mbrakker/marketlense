# CodeGraph Codex MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evaluate CodeGraph as a development-only Codex MCP and retain it only if a narrow, reproducible Phase-0 comparison passes.

**Architecture:** Temporarily configure the externally installed `codegraph serve --mcp` command in the user-owned Codex configuration, then use only its default `codegraph_explore` tool through the stdio MCP transport. The corpus-specific benchmark remains under the existing agent-engineering benchmark directory and never imports CodeGraph into MarketLense runtime code. The measured result failed, so the MCP configuration, local index, guidance, ignore rule, project config, and global package were removed.

**Tech Stack:** CodeGraph v1.5.0 external CLI/MCP, Codex TOML MCP configuration, Python standard library, pytest, JSON.

## Global Constraints

- CodeGraph is an external development dependency only; no CodeGraph package, import, parser, graph database, resolver, or watcher enters `src/`.
- MCP exposes only CodeGraph’s default high-level `codegraph_explore` surface; do not set `CODEGRAPH_MCP_TOOLS` to enable low-level tools.
- `.codegraph/` remains local, ignored, and absent from commits.
- CodeGraph output is retrieval assistance, not repository authority; stale or ambiguous material findings require current-source/test verification.
- Phase-0 must fail the adoption gate if either arm misses a relevant file, CodeGraph adds a wrong source-backed conclusion, or targets for retrieval calls, response-token proxy, and elapsed time are not met.
- Phase-0 response tokens are a stated `UTF-8 response bytes / 4` proxy because Codex model telemetry is unavailable from local CLI calls.

---

### Task 1: Install and configure the minimal external MCP

**Files:**
- Modify: `C:\Users\Михаил\.codex\config.toml`
- Modify: `.gitignore`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: external `codegraph` executable and Codex MCP configuration.
- Produces: one `mcp_servers.codegraph` stdio entry executing `codegraph serve --mcp`, an ignored local index, and concise agent use guidance.

- [x] **Step 1: Verify the external CLI is absent before installation**

Run: `Get-Command codegraph -ErrorAction SilentlyContinue`

Expected: no command before the external installation.

- [x] **Step 2: Install and inspect the external CLI configuration snippet**

Run: `npm install -g @colbymchenry/codegraph@1.5.0` then `codegraph install --print-config codex`

Expected: a Codex-compatible stdio server snippet using `codegraph serve --mcp`.

- [x] **Step 3: Configure exactly one MCP server and local index ignore rule**

Add the `codegraph` MCP server entry to the user Codex TOML with only `command`, `args`, and a startup timeout. Add `.codegraph/` to `.gitignore`; do not add package dependencies or CodeGraph configuration to `src/`.

- [x] **Step 4: Add concise guidance**

Add four bullets to `AGENTS.md` directing multi-file structural questions to CodeGraph, retaining source/test verification for stale or ambiguous findings, and avoiding an immediate broad grep/read replay unless more evidence is required.

- [x] **Step 5: Initialize and verify the local index**

Run: `codegraph init` and `codegraph status --json`

Expected: the index is present under ignored `.codegraph/` and reports a completed, non-partial state.

### Task 2: Add the narrow Phase-0 retrieval comparison and apply its gate

**Files:**
- Create: `benchmarks/agent-engineering/codegraph-phase0.json`
- Create: `scripts/quality/codegraph_phase0_benchmark.py`
- Create: `tests/test_codegraph_phase0_benchmark.py`
- Modify: `benchmarks/agent-engineering/README.md`
- Modify: `docs/quality/benchmarks.md`

**Interfaces:**
- Consumes: two source-backed architecture-investigation cases and the external `codegraph_explore` MCP tool.
- Produces: deterministic source-retrieval coverage and a JSON report comparing explicit native discovery steps with one CodeGraph explore call per task.

- [x] **Step 1: Write the failing benchmark test**

```python
def test_evaluate_phase0_rejects_missed_files_and_unmet_targets() -> None:
    report = evaluate_phase0(native_rows, codegraph_rows, threshold)
    assert report["passed"] is False
    assert "missed_relevant_files" in report["failures"]
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_codegraph_phase0_benchmark.py`

Expected: FAIL because the Phase-0 scorer does not exist.

- [x] **Step 3: Implement the corpus-specific runner**

Run the declared native retrieval and one persistent-MCP `codegraph_explore` call per case. Capture command count, source-read count, elapsed milliseconds, UTF-8 response bytes, proxy tokens, expected-file recall, and source-backed conclusion verdict. Return failure when correctness regresses or the improvement targets are missed.

- [x] **Step 4: Run the Phase-0 command**

Run: `python scripts/quality/codegraph_phase0_benchmark.py --spec benchmarks/agent-engineering/codegraph-phase0.json --output benchmarks/agent-engineering/baselines/codegraph-phase0.json`

Observed: full relevant-file recall, 75% fewer retrieval calls, 56.3% fewer response-token-proxy units, but 993 ms CodeGraph query time versus 194 ms native time and one unverified structural marker. The adoption gate failed.

- [x] **Step 5: Remove the integration because the gate failed**

Run: `python -m pytest -q tests/test_codegraph_phase0_benchmark.py tests/test_documentation_validation.py`

Observed: the focused benchmark tests pass. `codegraph uninit --force` removed the local index; the Codex MCP entry, `.gitignore` rule, guidance, project config, and global package were removed. The failed report and reusable comparison are retained as rejection evidence, not adoption artifacts.
