# Codebase simplification audit

## Summary

I ran a heuristic scan across the 764 Python files under `src` and traced the strongest leads through their callers, contracts, and relevant documentation. I found several concrete issues in workflow queue health and its CLI. I did not find evidence that the repository’s typed contracts or private facades are gratuitous in general.

The stack is Python 3.12, with SQLite-backed services, a Streamlit UI, and a WordPress subproject. The documented default test command is `python -m pytest`; the local quality runner is `python scripts/ci/run_quality_gate.py --list`. Neither was run: this was a read-only audit. No source files were modified for the review; this report is the only added file.

## Findings

1. **Queue throughput is not a 24-hour measurement — medium severity.**

   [`health.py:215`](src/services/_workflow_queue_service/health.py#L215) selects the latest 200 completed attempts, with no time cutoff. [`health.py:257`](src/services/_workflow_queue_service/health.py#L257) then counts nonnegative runtime values as `throughput_24h`. Old attempts are included, and the result is effectively the size of the sample. Define whether throughput counts jobs or attempts, then aggregate that unit over the prior 24 hours. Add a test with both recent and older completions.

2. **`queue-list` does not show queue controls — medium severity.**

   [`workflow_queue.py:308`](src/_cli/workflow_queue.py#L308) describes listing each queue’s durable controls, but outputs `WorkflowQueueHealth` records instead. That contract has health metrics and no mode, enabled state, or limits ([`workflow_queue` contract:540](src/contracts/workflow_queue.py#L540)). Return persisted control records from this command. Test that a paused or disabled queue appears with its current settings.

3. **`queue-health --queue` calculates health for every queue before filtering — low to medium severity.**

   [`workflow_queue.py:324`](src/_cli/workflow_queue.py#L324) calls the all-queues health reader, then filters in memory at line 326. The reader runs several queue-specific queries inside a loop over all 26 queue names ([`health.py:177`](src/services/_workflow_queue_service/health.py#L177)). Pass the selected queue into the read path and validate its name there. Test that a single-queue request queries only that queue.

4. **Queue health reports zero reconciliation anomalies without measuring them — medium severity.**

   [`health.py:267`](src/services/_workflow_queue_service/health.py#L267) always returns `reconciliation_anomaly_count=0`. The separate reconciliation path can identify anomalies ([`health.py:273`](src/services/_workflow_queue_service/health.py#L273)), but health never checks or records them. Compute a read-only count, or version the contract to represent an unavailable value rather than a measured zero. Test a known anomalous queue state.

5. **Prompt logging guidance conflicts with the repository’s data policy.**

   [`role-boundaries.md:34`](docs/architecture/role-boundaries.md#L34) says to log prompt text and rendered output per model call. [`AGENTS.md:232`](AGENTS.md#L232) prohibits logging complete rendered prompts and prescribes prompt identity and bounded metadata instead. The evidence guide also says retained artifacts must not contain rendered prompts ([`evidence.md:41`](docs/quality/evidence.md#L41)). Update the architecture guidance to match the current policy; no code change is needed to address the documentation conflict.

## Complexity signals

The scanner reported 1,077 possible hotspots: 306 nested loops, 615 membership checks in loops, 104 sorts in loops, and 49 possible I/O or query calls in loops. Many are false positives or expected work—for example, set membership and sorting an iterable before the loop. I manually checked the strongest leads rather than treating the scanner’s counts as confirmed problems.

There is also **complexity concentrated in large functions**, especially [`publish_orchestrator.py:1300`](src/orchestrators/publish_orchestrator.py#L1300): `run_publish` spans about 1,239 lines and contains 46 `if` statements, six loops, and four `try` blocks. Other very long functions include `generate_artifacts` (about 1,002 lines) and `run_report_analysis` (about 932 lines). These are maintenance risks, but their size alone does not show that existing abstractions have no value. Any cleanup should follow real workflow phases and preserve sequencing, with focused behavior tests.

## Scope and limitations

I did not trace every branch of all 764 Python files or run live workflows, so this is a broad static and targeted review rather than proof of every runtime sequence. No source files were changed during the audit; `simplification.md` is the sole new file.
