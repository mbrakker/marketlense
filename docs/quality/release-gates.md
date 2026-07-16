# Release Gates

> **Documentation type:** Current reference
> **Canonical topic:** Release and CI gates
> **Update trigger:** CI workflow, quality gate, baseline, or release-evidence requirement changes.

The authoritative CI command sequence is [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml). The local aggregate runner is:

```powershell
python scripts/ci/run_quality_gate.py --list
```

The gate sequence covers dependency consistency, formatting and linting, typing, architecture and I/O policy, bounded structured logging, repository hygiene, runbook and backlog ownership, contract snapshots, WordPress checks, default tests, coverage, mutation testing, and retained quality regressions. Benchmarks and evidence artifacts are separate gates where configured.

Run the focused checks appropriate to the changed area before the aggregate suite. This document explains gate categories; it does not record pass/fail results. See [benchmarks](benchmarks.md) and [evidence](evidence.md).
