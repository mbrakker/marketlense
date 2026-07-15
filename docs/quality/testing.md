# Testing

> **Documentation type:** Current reference
> **Canonical topic:** Testing practice
> **Update trigger:** Test layer, integrity rule, fixture, or default test command changes.

Run the default fast suite from the repository root:

```powershell
python -m pytest
```

Default test runs exclude the `integration` marker. Integration tests are explicit and must not make live provider calls unless their opt-in guard and credentials are present.

Tests assert observable behavior: completed contracts, persisted or emitted side effects, structured log fields, typed errors, retry decisions, and idempotency where applicable. Mock only external boundaries; do not patch private helpers or the primary logic path under test.

Detailed integrity rules are maintained here. The architecture policy, coverage/mutation requirements, and static forbidden-patching checks are described in [architecture policy](architecture-policy.md) and [release gates](release-gates.md).
