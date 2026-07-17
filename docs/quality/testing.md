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

When diagnosing an apparently stalled run, use verbose progress, `--durations`, and (where needed) `-o faulthandler_timeout=<seconds>` before interrupting it. Quiet output alone is not evidence of a deadlock; the diagnostic command must identify the active test and stack before a timeout remediation is made.

Windows atomic-write tests exercise same-target thread serialization and the only permitted local retry guard: at most two re-attempts of the final rename for native access/sharing errors (`5` or `32`). This is not a workflow retry; all other write failures propagate as typed errors.

The contract-schema gate ignores files whose basenames are not valid Python module identifiers, so untracked editor copies cannot alter the generated contract inventory.

Tests assert observable behavior: completed contracts, persisted or emitted side effects, structured log fields, typed errors, retry decisions, and idempotency where applicable. Prefer pure tests, local fixtures, protocol fakes, local servers, and controlled integrations. Mock only approved public external boundaries, time, randomness, or OS/process seams. Pytest monkeypatching, private-helper patching, and replacement of generator/orchestrator internals are forbidden.

Detailed integrity rules are maintained here. The architecture policy, coverage/mutation requirements, and static forbidden-patching checks are described in [architecture policy](architecture-policy.md) and [release gates](release-gates.md).
