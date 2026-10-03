# Architecture Policy

> **Documentation type:** Current reference
> **Canonical topic:** Architecture policy
> **Update trigger:** Role boundary, import direction, I/O policy, service ownership, or enforcement change.

The executable policy is [`architecture_policy.yaml`](architecture_policy.yaml). It defines architectural roles, permitted imports, allowed I/O, external-system ownership, and selected enforcement thresholds.

The CI gates inspect role imports, direct I/O, service-boundary ownership, split symbol links, and repository hygiene. Human-readable boundary rules are in [architecture overview](../architecture/overview.md) and [role boundaries](../architecture/role-boundaries.md).

When a change adds an external system, competing service entrypoint, new deployable component, or a materially new top-level architecture boundary, perform the architecture review required by `AGENTS.md` before merge.

MarketLense defaults to one modular monolith. A new deployable unit requires current evidence for at least two material needs: independent scaling, independent deployment cadence, hard failure isolation, genuinely separate ownership, or materially different runtime or compliance requirements. “Future readiness” alone is not evidence. The deployable review trigger in `architecture_policy.yaml` does not by itself satisfy this evidence threshold.
# SQLite ownership

The validation-reliability service is an approved read-only SQLite boundary for
its immutable validation telemetry. It remains responsible for translating
database errors into the canonical application error taxonomy.
