# Architecture Overview

> **Documentation type:** Architectural
> **Canonical topic:** System architecture
> **Update trigger:** Role ownership, deployable boundary, or core data-flow changes.

MarketLense is a modular monolith. The Python application remains one deployable system with strict internal roles:

```text
contracts <- services <- generators <- orchestrators <- CLI / UI
              external      domain       control plane
                 I/O         assembly
```

- Contracts define typed request and response models.
- Services own filesystem, database, network, provider, and browser I/O.
- Generators assemble domain outputs and validate semantic completeness.
- Orchestrators own sequencing, retry, state transitions, and idempotency.
- Utilities are deterministic helpers with no I/O.

The executable policy and allowed dependency directions are maintained in [architecture policy](../quality/architecture-policy.md). Read [repository structure](repository-structure.md), [workflow control](workflow-control.md), [data and artifacts](data-and-artifact-model.md), and [external system boundaries](external-system-boundaries.md) for the supporting reference.
