# MarketLense Documentation

This index separates current reference material from executable procedures, historical records, and generated inventories. Start with the [repository README](../README.md) for setup and primary commands.

| Area | Purpose | Audience | Status type | Canonical owner | Canonical location | Update trigger |
| --- | --- | --- | --- | --- | --- | --- |
| Product | Product behavior, lifecycle, and editorial output | Product, editorial, engineering | Current reference | Product documentation | [product/](product/overview.md) | Supported behavior changes |
| Architecture | System boundaries, artifacts, and workflow control | Engineers and architects | Architectural | Architecture documentation | [architecture/](architecture/overview.md) | Architectural change |
| Workflows | Stage-specific behavior from discovery through publication | Engineers and operators | Current reference | Workflow documentation | [workflows/](workflows/report-processing.md) | Workflow change |
| Operations | Local setup, credentials, monitoring, recovery, and deployment | Operators and incident responders | Operational | Operations documentation | [ops/](ops/local-development.md) | Operator procedure or environment change |
| Quality | Testing policy, gates, benchmarks, and evidence process | Contributors and reviewers | Current reference | Quality documentation | [quality/](quality/testing.md) | Quality-policy or gate change |
| CTO evidence | Commit-bound repository inventory and snapshotted runtime telemetry | CTO, operators, reviewers | Generated evidence | CTO evidence collector | [CTO_evidence/](CTO_evidence/README.md) | Run the strict CTO evidence collector after representative processing |
| Releases | Curated historical summaries; Git remains the detailed chronology | Reviewers and maintainers | Historical | Release history | [releases/](releases/README.md) | Review-period or release completion |
| Generated reference | Code/configuration-derived CLI, configuration, and capability inventories | Contributors and operators | Generated | Generator scripts | [generated/](generated/capability-manifest.md) | Run `python scripts/docs/generate_references.py` after relevant source changes |

## Quick routing

- New engineer: [local development](ops/local-development.md), [configuration](ops/configuration.md), then the [report lifecycle](product/report-lifecycle.md).
- Operator or incident responder: [monitoring](ops/monitoring.md), [recovery](ops/recovery.md), [source publication metadata](ops/source-publication-metadata.md), [budget authority coverage](ops/budget_authority_coverage.md), [troubleshooting](ops/troubleshooting.md), and [WordPress operations](ops/wordpress.md).
- Architect: [architecture overview](architecture/overview.md), [workflow control](architecture/workflow-control.md), [asynchronous workflow queue](architecture/asynchronous-workflow-queue.md), [lineage-driven minimum regeneration](architecture/lineage-minimum-regeneration-planner.md), [external boundaries](architecture/external-system-boundaries.md), and the machine-enforced [architecture policy](quality/architecture-policy.md).
- Contributor: [testing](quality/testing.md), [release gates](quality/release-gates.md), [public editorial quality](quality/public-editorial-quality.md), and [CONSOLIDATED_TODO.md](../CONSOLIDATED_TODO.md).

The focused [WordPress front-end contract](../README_WORDPRESS.md) and [WordPress implementation map](architecture/wordpress-front-end.md) remain separate because they describe the theme/plugin surface rather than Python workflow operations.

## Complete documentation inventory

Every repository-maintained documentation asset outside runtime output belongs
to one of the locations below. Current reference and procedures describe
supported behavior. Generated files describe a specific source revision or
retained evidence. Historical records explain past decisions and never override
current documentation.

| Location | Contents and status |
| --- | --- |
| [Product](product/overview.md) | Current product model, [report lifecycle](product/report-lifecycle.md), and [editorial-output contract](product/editorial-output.md). |
| [Architecture](architecture/overview.md) | Current role boundaries, repository structure, workflow control, data/artifact model, asynchronous queue, external systems, lineage planning, operator cockpit, and WordPress implementation map. The remaining `*-decomposition-review.md` files are historical movement and ownership records. |
| [Workflows](workflows/report-processing.md) | Current procedures for report discovery, acquisition, processing, validation/regeneration, publishing, mailbox acquisition, and cross-report analysis. |
| [Operations](ops/local-development.md) | Current local and [Codex Cloud](ops/codex-cloud-environment.md) setup, configuration, credentials, deployment, monitoring, recovery, troubleshooting, WordPress operations, source-publication metadata, budget authority, and remediation/runbook coverage. Associated YAML files are machine-readable operational policy and coverage inputs. |
| [Quality](quality/testing.md) | Current testing, release-gate, benchmark, architecture-policy, public-editorial-quality, non-regression, and evidence procedures. YAML and JSON files in this directory are the enforced policy, allowlist, baseline, schema, and quality-ledger inputs; dated reviews and proposals are historical context. |
| [Generated reference](generated/capability-manifest.md) | Current source-derived [capability](generated/capability-manifest.md), [CLI](generated/cli-reference.md), and [configuration](generated/configuration-reference.md) inventories. Regenerate them with `python scripts/docs/generate_references.py`; do not edit them directly. |
| [CTO evidence](CTO_evidence/README.md) | Generated, commit-bound machine-readable telemetry, metrics, manifests, audit snapshots, and the retained review archive. The directory README identifies the collector and regeneration command. |
| [Release history](releases/README.md) | Curated historical release and review summaries. Git is the canonical commit-level record. |
| [Docpack guidance](docpacks/pack-specs.md) | Current evidence-pack schemas, persistence, referential-integrity rules, and [prompt-authoring](docpacks/prompt-authoring.md) requirements. |
| [Historical plans and specifications](superpowers) | Archived implementation plans and design specifications, organised by `plans/` and `specs/`; they record rationale and acceptance evidence, not current behavior. |
| [Brand specification](brand-spec.md) | Current Market Bearing visual tokens, interaction language, and product voice. |
| [Publisher inventory edge cases](publisher_inventory_edge_cases.md) | Observed publisher-specific discovery behavior and the generic handling currently applied. |
| [Browser route playbooks](../src/playbooks/browser_routes/README.md) | Current reviewable browser and private-API route guidance, including selection, stale handling, and promotion rules. The YAML files are runtime playbook assets. |
| [Engineering guidance](../AGENTS.md) | The repository engineering policy, [Copilot orientation](../.github/copilot-instructions.md), and [pull-request checklist](../.github/pull_request_template.md). |
| [Test-fixture guides](../tests/fixtures/pdf_benchmark/golden/README.md) | The retained [candidate/crop](../tests/fixtures/candidate_extraction/golden/crop_quality_v1/README.md), [PDF benchmark](../tests/fixtures/pdf_benchmark/golden/README.md), and [crop-refinement](../tests/fixtures/pdf_crop_refine/golden/README.md) corpora and their integrity rules. |
| [Vendored Browser Use](../tools/browser-use/README.md) | Preserved upstream package, example, and submodule documentation. It is reference material for the vendored tool, not authoritative MarketLense workflow or policy documentation. |
| [WordPress front-end contract](../README_WORDPRESS.md) | Current public rendering contract, shortcode surface, canonical cards, verification, and WordPress build procedures. |
| [Canonical backlog](../CONSOLIDATED_TODO.md) | The single current prioritised backlog. It is referenced here for routing but is not a documentation pack. |

The `cto-review-evidence.zip` archive is the packaged counterpart of the
generated CTO evidence directory. It is retained evidence, not a source of
current behavior or procedure.
