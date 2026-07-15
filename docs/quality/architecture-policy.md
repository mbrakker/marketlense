# Architecture Policy

> **Documentation type:** Current reference
> **Canonical topic:** Architecture policy
> **Update trigger:** Role boundary, import direction, I/O policy, service ownership, or enforcement change.

The executable policy is [`architecture_policy.yaml`](architecture_policy.yaml). It defines architectural roles, permitted imports, allowed I/O, external-system ownership, and selected enforcement thresholds.

The CI gates inspect role imports, direct I/O, service-boundary ownership, split symbol links, and repository hygiene. Human-readable boundary rules are in [architecture overview](../architecture/overview.md) and [role boundaries](../architecture/role-boundaries.md).

When a change adds an external system, competing service entrypoint, new deployable component, or a materially new top-level architecture boundary, perform the architecture review required by `AGENTS.md` before merge.
