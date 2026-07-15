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

## Documentation map

| Need | Canonical location |
| --- | --- |
| Product behavior | [docs/product](docs/product/overview.md) |
| Architecture and boundaries | [docs/architecture](docs/architecture/overview.md) |
| Workflow stages | [docs/workflows](docs/workflows/report-processing.md) |
| Setup, deployment, recovery, and troubleshooting | [docs/ops](docs/ops/local-development.md) |
| WordPress front-end contract | [README_WORDPRESS.md](README_WORDPRESS.md) |
| Quality and release evidence process | [docs/quality](docs/quality/testing.md) |
| Historical summaries | [docs/releases](docs/releases/README.md) |
| Generated command and configuration inventories | [docs/generated](docs/generated/capability-manifest.md) |

The full documentation index includes status types and update triggers: [docs/README.md](docs/README.md).

## Current project status

The supported pipeline is configuration-driven and uses the documented validation and publication gates. Cross-report analysis, OCR fallback, and browser session reuse are configuration-gated capabilities; inspect their settings and workflow documentation before enabling them.

Active work is tracked only in [CONSOLIDATED_TODO.md](CONSOLIDATED_TODO.md). [x100tasks.md](x100tasks.md) is archived. Historical implementation detail belongs in Git history or [release summaries](docs/releases/README.md), not this README.

## Contributing

Read [AGENTS.md](AGENTS.md) before making changes. Preserve role boundaries, update the canonical documentation for changed behavior, regenerate references when CLI/configuration sources change, and run the focused quality checks for the affected area.

The root README is an entry point: keep it to stable orientation, essential setup, primary commands, and links to canonical documentation.
