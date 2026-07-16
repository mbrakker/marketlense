# MarketLense Documentation

This index separates current reference material from executable procedures, historical records, and generated inventories. Start with the [repository README](../README.md) for setup and primary commands.

| Area | Purpose | Audience | Status type | Canonical owner | Canonical location | Update trigger |
| --- | --- | --- | --- | --- | --- | --- |
| Product | Product behavior, lifecycle, and editorial output | Product, editorial, engineering | Current reference | Product documentation | [product/](product/overview.md) | Supported behavior changes |
| Architecture | System boundaries, artifacts, and workflow control | Engineers and architects | Architectural | Architecture documentation | [architecture/](architecture/overview.md) | Architectural change |
| Workflows | Stage-specific behavior from discovery through publication | Engineers and operators | Current reference | Workflow documentation | [workflows/](workflows/report-processing.md) | Workflow change |
| Operations | Local setup, credentials, monitoring, recovery, and deployment | Operators and incident responders | Operational | Operations documentation | [ops/](ops/local-development.md) | Operator procedure or environment change |
| Quality | Testing policy, gates, benchmarks, and evidence process | Contributors and reviewers | Current reference | Quality documentation | [quality/](quality/testing.md) | Quality-policy or gate change |
| Releases | Curated historical summaries; Git remains the detailed chronology | Reviewers and maintainers | Historical | Release history | [releases/](releases/README.md) | Review-period or release completion |
| Generated reference | Code/configuration-derived CLI, configuration, and capability inventories | Contributors and operators | Generated | Generator scripts | [generated/](generated/capability-manifest.md) | Run `python scripts/docs/generate_references.py` after relevant source changes |

## Quick routing

- New engineer: [local development](ops/local-development.md), [configuration](ops/configuration.md), then the [report lifecycle](product/report-lifecycle.md).
- Operator or incident responder: [monitoring](ops/monitoring.md), [recovery](ops/recovery.md), [troubleshooting](ops/troubleshooting.md), and [WordPress operations](ops/wordpress.md).
- Architect: [architecture overview](architecture/overview.md), [workflow control](architecture/workflow-control.md), [lineage-driven minimum regeneration](architecture/lineage-minimum-regeneration-planner.md), [external boundaries](architecture/external-system-boundaries.md), and the machine-enforced [architecture policy](quality/architecture-policy.md).
- Contributor: [testing](quality/testing.md), [release gates](quality/release-gates.md), and [CONSOLIDATED_TODO.md](../CONSOLIDATED_TODO.md).

The focused [WordPress front-end contract](../README_WORDPRESS.md) and [WordPress implementation map](architecture/wordpress-front-end.md) remain separate because they describe the theme/plugin surface rather than Python workflow operations.
