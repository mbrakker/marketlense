# Testing

> **Documentation type:** Current reference
> **Canonical topic:** Testing practice
> **Update trigger:** Test layer, integrity rule, fixture, or default test command changes.

Run the default fast suite from the repository root:

```powershell
python -m pytest
```

Default test runs exclude the `integration` marker. Controlled real provider calls are allowed in tests marked `integration` or `live` when an explicit opt-in guard and credentials are present. They must bound calls, tokens, duration, and cost; use read-only, sandbox, or reversible side effects; redact output; and skip clearly when prerequisites are absent.

Tests that exercise a request's default relative accounting, ledger, cache, or state paths must isolate them under `tmp_path` (for example, with the existing `external_boundary_mocks_only.chdir(tmp_path)` fixture) or pass explicit test paths. They must not share repository-root state artifacts: accumulated local ledgers can turn a small unit case into an unbounded projection or lease-recovery operation.

CLI unit tests must inject the canonical configuration service whenever the command needs application settings. The default suite must not depend on developer credentials or a local `.env` file.

When diagnosing an apparently stalled run, use verbose progress, `--durations`, and (where needed) `-o faulthandler_timeout=<seconds>` before interrupting it. Quiet output alone is not evidence of a deadlock; the diagnostic command must identify the active test and stack before a timeout remediation is made.

Windows atomic-write tests exercise same-target thread serialization and the only permitted local retry guard: at most two re-attempts of the final rename for the Windows access/sharing error signatures (`5` or `32`). The signature-based guard is tested on every platform; this is not a workflow retry, and all other write failures propagate as typed errors.

The contract-schema gate ignores files whose basenames are not valid Python module identifiers, so untracked editor copies cannot alter the generated contract inventory.

Tests assert observable behavior: completed contracts, persisted or emitted side effects, structured log fields, typed errors, retry decisions, and idempotency where applicable. Prefer pure tests, local fixtures, protocol fakes, local servers, and controlled integrations. Mock only approved public external boundaries, time, randomness, or OS/process seams. Pytest monkeypatching, private-helper patching, and replacement of generator/orchestrator internals are forbidden.

Detailed integrity rules are maintained here. The architecture policy, coverage/mutation requirements, and static forbidden-patching checks are described in [architecture policy](architecture-policy.md) and [release gates](release-gates.md).

## Deterministic agent completion gate

The canonical pre-completion command is:

```powershell
python scripts/quality/agent_completion_gate.py
```

It reads the current `git diff` and untracked paths, deterministically maps the
change to repository subsystems and risk, runs existing focused checks, and
escalates high-risk work to `scripts/ci/run_quality_gate.py`. Its JSON report
contains changed files, selected checks, tests run, failures, unverified
requirements, and the aggregate-gate decision. Only a command-produced
`result: "PASS"` authorizes an agent completion claim; model judgment cannot
assign PASS. The command is development tooling only and adds no runtime
dependency. It is a MarketLense-native lifecycle completion check, not a
Claude Code hook or dependency.

The gate hashes the content of the tracked diff and untracked files before and
after checks, so a checker mutating an already-modified path makes PASS
impossible. It stores bounded actionable stdout/stderr only for failed checks
in the JSON report. Explicit `MARKETLENSE_RETAIN_FAILURE_OUTPUT=1` opt-in
retains redacted local failure output under the ignored
`.codex_tmp/agent_completion_gate/` evidence directory. Ordinary role-boundary
changes select focused lint, type, architecture, and credible affected tests;
the aggregate quality gate is reserved for public-contract, persisted-schema,
release-control, and named consequential-workflow changes, and is not preceded
by a duplicate default pytest run.
