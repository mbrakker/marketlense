# Release Gates

> **Documentation type:** Current reference
> **Canonical topic:** Release and CI gates
> **Update trigger:** CI workflow, quality gate, baseline, or release-evidence requirement changes.

The authoritative CI command sequence is [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml). The local aggregate runner is:

```powershell
python scripts/ci/run_quality_gate.py --list
```

The local gate sequence mirrors GitHub's pre-test checks, including dependency consistency, formatting and linting, typing, architecture and I/O policy, service-boundary mapping, refactor evidence, bounded structured logging, repository hygiene, runbook and backlog ownership, contract snapshots, and WordPress checks. It then runs the default tests, coverage, mutation testing, and retained quality regressions. Benchmarks and evidence artifacts are separate gates where configured. The release bundle also includes exact-HEAD deterministic queue evidence; it is a temporary-SQLite semantic check, not live production throughput evidence.

The PDF candidate benchmark runs in mutation partition 0. Its result and its
single-stage timing telemetry travel in that partition's run- and attempt-scoped
artifact. The release-evidence job requires both files and merges the recorded
stage into the pytest/coverage command telemetry before checking the remaining
release gates. A missing or failed candidate result prevents release approval.

The release-evidence job first checks the `ci_start`, `tests`, and `mutation`
job results before checkout, Python setup, dependency installation, or artifact
handling. A failed, cancelled, skipped, or missing prerequisite writes a short
job summary and fails the release-evidence job. Artifact downloads, evidence
merges, and bundle upload are skipped on that path. Once all prerequisites pass,
the full release-evidence sequence below runs unchanged. The release job checks
out only the requested `HEAD` commit (`fetch-depth: 1`); its release gates bind
artifacts to that exact SHA and do not require ancestry. The `tests` and
`mutation` jobs retain full-history checkouts for their base-ref diff gates.

The release-review gate requires the pytest telemetry, CI performance benchmark,
and machine-derived executive summary alongside the manifest. A green manifest
alone is insufficient: release review rejects nonzero pytest exit codes,
recorded failed tests, `ci_performance_benchmark.json.passed: false`, a false
`quality_passed`, contradictory summary claims, or mismatched commit/run
provenance. A waiver may record an exception but cannot make failed machine
evidence or a failed manifest release-green.

After prerequisites pass, the GitHub job summary runs after the release-bundle
upload, including when a later release gate prevents review or queue-evidence
generation. It reports absent inputs as unavailable/non-green. Upload-step
success is reported separately from configured required-file completeness, so
a partial diagnostic archive is not described as a complete bundle. When a
pytest or mutation prerequisite fails, no release bundle is uploaded.

## GitHub merge enforcement

The `ci` workflow runs for both `push` and `pull_request` and exposes a separate
`tests` status check. If merge enforcement is enabled, require that check and
require the branch to be current with its base before merging. GitHub
repository settings are the merge authority and cannot be enforced by this
checkout. On 2026-10-14, the GitHub branch-protection API reported `main` as
unprotected, and the repository had no rulesets; therefore CI failures were
visible on pull requests but were not enforced as merge-blocking checks.
Enable a branch-protection rule or ruleset when that enforcement is intended.
Require pull requests as part of the same rule when direct pushes must be
prevented. Enable required code-owner review separately if the repository
intends the existing `CODEOWNERS` file to be a merge requirement.

Repository hygiene exceptions are temporary migration tools, not permanent
storage policy. Generated screenshots belong in ignored runtime output or, when
they are intentional test inputs, under `tests/fixtures`; expired screenshot
exceptions are removed together with the tracked runtime artifacts.

Documentation may retain relative pointers to ignored runtime evidence under
`out/`, `output/`, `cache/`, `logs/`, `state/`, or `temp/`. The documentation
gate validates versioned link targets and heading anchors, while treating those
runtime pointers as audit references because a clean CI checkout does not
contain their artifacts.

Run the focused checks appropriate to the changed area before the aggregate suite. This document explains gate categories; it does not record pass/fail results. See [benchmarks](benchmarks.md) and [evidence](evidence.md).
