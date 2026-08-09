# Release Gates

> **Documentation type:** Current reference
> **Canonical topic:** Release and CI gates
> **Update trigger:** CI workflow, quality gate, baseline, or release-evidence requirement changes.

The authoritative CI command sequence is [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml). The local aggregate runner is:

```powershell
python scripts/ci/run_quality_gate.py --list
```

The local gate sequence mirrors GitHub's pre-test checks, including dependency consistency, formatting and linting, typing, architecture and I/O policy, service-boundary mapping, refactor evidence, bounded structured logging, repository hygiene, runbook and backlog ownership, contract snapshots, and WordPress checks. It then runs the default tests, coverage, mutation testing, and retained quality regressions. Benchmarks and evidence artifacts are separate gates where configured. The release bundle also includes exact-HEAD deterministic queue evidence; it is a temporary-SQLite semantic check, not live production throughput evidence.

The GitHub job summary runs only when its release-review and queue-evidence inputs exist. The evidence bundle upload still runs after an earlier gate fails, retaining available diagnostics without adding a missing-artifact summary failure.

Repository hygiene exceptions are temporary migration tools, not permanent
storage policy. Generated screenshots belong in ignored runtime output or, when
they are intentional test inputs, under `tests/fixtures`; expired screenshot
exceptions are removed together with the tracked runtime artifacts.

Run the focused checks appropriate to the changed area before the aggregate suite. This document explains gate categories; it does not record pass/fail results. See [benchmarks](benchmarks.md) and [evidence](evidence.md).
