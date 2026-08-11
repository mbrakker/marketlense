# MarketLense

MarketLense is a report-intelligence pipeline and publishing system. It turns acquired source reports into validated, source-backed editorial artifacts and can publish approved output to a WordPress portal.

## What MarketLense does

MarketLense discovers and acquires report sources, processes PDFs and permitted on-site captures, extracts evidence and visual candidates, creates structured analysis and HTML, validates the result, and publishes approved artifacts. It also supports source and publisher operations, mailbox-delivered reports, cross-report Briefings, and an operator cockpit.

The system publishes validated pipeline output. WordPress is a rendering and publication layer, not a runtime intelligence-generation layer.

## Core capabilities

- Report and publisher discovery with retained source context.
- Direct, browser-assisted, and mailbox-based report acquisition.
- Contract- and schema-validated report processing, including evidence packs and visual candidates.
- Validation-driven regeneration and checkpoint-aware resume.
- WordPress publication for Reports, Signals, Briefings, Topics, and Publishers.
- Structured operational logs, trace inspection, run control, and cost/accounting surfaces.

Read the [product overview](docs/product/overview.md) for the public model and [editorial output](docs/product/editorial-output.md) for publication semantics.

## Report lifecycle

```text
Discover -> Acquire -> Ingest -> Analyze -> Validate -> Render -> Publish
                              ^                         |
                              +--- checkpoints/lineage --+
```

See the [report lifecycle](docs/product/report-lifecycle.md) and [workflow references](docs/workflows/report-processing.md) for current stage behavior.

## Architecture at a glance

MarketLense is a modular monolith with strict internal roles:

```text
contracts <- services <- generators <- orchestrators <- CLI / UI
              external      domain       control plane
                 I/O         assembly
```

Services own external I/O, generators assemble domain outputs, and orchestrators own sequencing, retries, state transitions, and idempotency. The executable policy is documented in [architecture policy](docs/quality/architecture-policy.md).

## Repository structure

| Path | Purpose |
| --- | --- |
| `src/` | Python contracts, services, generators, orchestrators, CLI, UI, prompts, configuration, and schemas |
| `Wordpress/` | Block theme, plugin, and WordPress scripts |
| `docs/` | Current reference, operations, quality, release history, and generated documentation |
| `scripts/` | CI, quality, dependency, and maintenance tooling |
| `tests/` | Unit, contract, pipeline, and guarded integration tests |

See [repository structure](docs/architecture/repository-structure.md) for ownership and [WordPress operations](docs/ops/wordpress.md) for the local subproject workflow.

## Requirements

- CPython 3.12 or later.
- A virtual environment with dependencies installed from the hash-locked dependency file.
- Provider credentials only for the workflows that use them.
- A local WordPress installation only when developing or verifying the WordPress subproject.

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
Copy-Item src\config\app.example.yaml src\config\app.local.yaml
```

Set machine-specific non-secret values in `src/config/app.local.yaml`; keep credentials in `.env` or the process environment. Continue with [local development](docs/ops/local-development.md), [configuration](docs/ops/configuration.md), and [credentials](docs/ops/credentials.md).

## Essential commands

```powershell
# Inspect registered commands
python -m src.cli --help

# Inspect a workflow plan without launching it
python -m src.cli plan "ingest new reports"

# Run a bounded configured ingest
python -m src.cli ingest --limit 1

# Start the operator cockpit
streamlit run src/streamlit_app.py

# Run the default fast test suite
python -m pytest
```

Use the generated [CLI reference](docs/generated/cli-reference.md) for the current command inventory. See [workflow documentation](docs/workflows/report-acquisition.md) before commands that make external changes.

## Configuration

`src/config/app.yaml` is the committed non-secret default configuration. `src/config/app.example.yaml` shows environment-specific overlay values. `MARKET_LENSE_CONFIG_PATH`, an optional profile overlay, `app.local.yaml`, and supported environment variables participate in configuration resolution.

The main operator areas are paths, ingest, publishing, browser and mailbox acquisition, publisher discovery, and workflow control. The complete generated section inventory is in [configuration reference](docs/generated/configuration-reference.md); [configuration operations](docs/ops/configuration.md) explains precedence and safe editing.

## Testing and quality gates

The default suite excludes guarded integration tests. CI additionally enforces formatting, linting, typing, architecture and I/O boundaries, repository hygiene, contract snapshots, coverage, mutation, WordPress checks, and configured regression gates.

```powershell
python scripts/ci/run_quality_gate.py --list
python scripts/ci/check_documentation.py --check-generated
```

See [testing](docs/quality/testing.md), [release gates](docs/quality/release-gates.md), [benchmarks](docs/quality/benchmarks.md), and [evidence process](docs/quality/evidence.md).

## Documentation directory

[docs/README.md](docs/README.md) is the complete, status-aware documentation
index. It distinguishes current reference and operational procedures from
generated inventories, point-in-time evidence, and historical records. The
following map links every documentation set and explains what belongs there.

| Documentation set | What it contains | Start here |
| --- | --- | --- |
| Documentation index | The canonical inventory, ownership, status, and update triggers for every documentation set | [docs/README.md](docs/README.md) |
| Product | Supported product model, report lifecycle, and public editorial-output semantics | [docs/product](docs/product/overview.md) |
| Architecture | Current system boundaries, artifacts, workflow control, external-system ownership, and repository structure | [docs/architecture](docs/architecture/overview.md) |
| Workflow procedures | Discovery, acquisition, processing, validation, regeneration, publication, mailbox, and cross-report workflows | [docs/workflows](docs/workflows/report-processing.md) |
| Operations | Local setup, configuration, credentials, deployment, monitoring, recovery, troubleshooting, source metadata, budgets, and WordPress operations | [docs/ops](docs/ops/local-development.md) |
| Quality | Testing, release gates, architecture policy, benchmarks, public-editorial quality, enforcement configuration, and quality baselines | [docs/quality](docs/quality/testing.md) |
| Generated reference | Source-derived inventories for public CLI commands, configuration sections, external-system ownership, orchestrators, and schemas | [docs/generated](docs/generated/capability-manifest.md) |
| CTO evidence | Generated, commit-bound evidence manifests, telemetry, metrics, and audit snapshots; these are not hand-edited reference prose | [docs/CTO_evidence](docs/CTO_evidence/README.md) |
| Release history | Curated historical release and review summaries; Git remains the commit-level chronology | [docs/releases](docs/releases/README.md) |
| Docpack guidance | Evidence-pack schemas, persistence, validation, and prompt-authoring rules | [docs/docpacks](docs/docpacks/pack-specs.md) |
| Historical plans and specifications | Archived design and implementation records that explain past decisions but do not override current reference | [docs/superpowers](docs/superpowers) |
| Brand and publisher records | The Market Bearing visual specification and observed publisher-discovery edge cases | [brand specification](docs/brand-spec.md) and [publisher inventory edge cases](docs/publisher_inventory_edge_cases.md) |
| Browser route playbooks | Reviewable, file-based browser and private-API route guidance, including stale handling and promotion rules | [playbook guide](src/playbooks/browser_routes/README.md) |
| Engineering guidance | Repository policy, Copilot orientation, and the pull-request review checklist | [AGENTS.md](AGENTS.md), [Copilot guide](.github/copilot-instructions.md), and [PR template](.github/pull_request_template.md) |
| Test-fixture guides | Retained benchmark and crop-quality corpora, their integrity rules, and the baselines that consume them | [candidate fixtures](tests/fixtures/candidate_extraction/golden/crop_quality_v1/README.md), [PDF benchmark fixtures](tests/fixtures/pdf_benchmark/golden/README.md), and [crop-refinement fixtures](tests/fixtures/pdf_crop_refine/golden/README.md) |
| Vendored Browser Use reference | The preserved upstream tool documentation; it is not MarketLense’s canonical workflow documentation | [tools/browser-use README](tools/browser-use/README.md) |
| WordPress front end | The public rendering contract, shortcodes, card variants, and verification procedure for the WordPress subproject | [README_WORDPRESS.md](README_WORDPRESS.md) |
| Active backlog | The sole current prioritised work list; historical plans are not a backlog | [CONSOLIDATED_TODO.md](CONSOLIDATED_TODO.md) |

Use the complete [documentation index](docs/README.md) to locate an individual
file within these sets. Keep this README as stable orientation and keep
implementation, operational, generated, and historical detail in its
canonical documentation pack.

## Current project status

The supported pipeline is configuration-driven and uses the documented validation and publication gates. Cross-report analysis, OCR fallback, and browser session reuse are configuration-gated capabilities; inspect their settings and workflow documentation before enabling them.

Active work is tracked only in [CONSOLIDATED_TODO.md](CONSOLIDATED_TODO.md).
Historical implementation detail belongs in Git history or
[release summaries](docs/releases/README.md), not this README.

## Contributing

Read [AGENTS.md](AGENTS.md) before making changes. Preserve role boundaries, update the canonical documentation for changed behavior, regenerate references when CLI/configuration sources change, and run the focused quality checks for the affected area.

The root README is an entry point: keep it to stable orientation, essential setup, primary commands, and links to canonical documentation.
