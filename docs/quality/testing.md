# Testing

> **Documentation type:** Current reference
> **Canonical topic:** Testing practice
> **Update trigger:** Test layer, integrity rule, fixture, or default test command changes.

Run the default fast suite from the repository root:

```powershell
python -m pytest
```

Default test runs exclude the `integration` marker. Controlled real provider calls are allowed in tests marked `integration` or `live` when an explicit opt-in guard and credentials are present. They must bound calls, tokens, duration, and cost; use read-only, sandbox, or reversible side effects; redact output; and skip clearly when prerequisites are absent.

Tests assert observable behavior: completed contracts, persisted or emitted side effects, structured log fields, typed errors, retry decisions, and idempotency where applicable. Prefer pure tests, local fixtures, protocol fakes, local servers, and controlled integrations. Mock only approved public external boundaries, time, randomness, or OS/process seams. Pytest monkeypatching, private-helper patching, and replacement of generator/orchestrator internals are forbidden.

Detailed integrity rules are maintained here. The architecture policy, coverage/mutation requirements, and static forbidden-patching checks are described in [architecture policy](architecture-policy.md) and [release gates](release-gates.md).
