# MarketLense Copilot Instructions

This file is a concise orientation for Copilot. The repository-wide
[engineering policy](../AGENTS.md) is authoritative; its architecture,
testing, documentation, security, and change-discipline requirements take
precedence over this guide.

## Project model

MarketLense is a modular-monolith report-intelligence and publishing system.
It acquires approved report sources, extracts and validates source-backed
artifacts, produces editorial output, and publishes approved records to
WordPress. WordPress renders and presents approved output; it does not perform
runtime intelligence generation.

Current behavior and operator procedures are indexed in
[docs/README.md](../docs/README.md). Use generated documentation for the
current command, configuration, capability, orchestrator, and schema
inventories rather than maintaining duplicate lists here.

## Code layout and entrypoints

- `src/cli.py` is the public CLI facade; command families live in `src/_cli/`.
- `src/streamlit_app.py` and `src/ui/` provide the operator cockpit.
- `src/contracts/` defines typed public, persisted, and external-boundary
  contracts.
- `src/services/` owns filesystem, network, database, browser, provider, and
  other external I/O.
- `src/generators/` performs domain assembly and semantic validation without
  direct infrastructure access.
- `src/orchestrators/` owns workflow sequencing, retries, idempotency, and
  explicit state transitions.
- `src/prompts/` contains prompt resources; load and render them through the
  prompt service rather than embedding substantial prompt prose in code.
- `src/config/` contains non-secret configuration assets. Credentials belong
  in `.env` or the process environment, never in committed files.
- `src/playbooks/browser_routes/` contains reviewable, file-based browser route
  guidance. See its [README](../src/playbooks/browser_routes/README.md) before
  changing a playbook.
- `src/utils/` contains deterministic helpers and must remain free of external
  I/O.

The dependency direction is `contracts <- services <- generators <-
orchestrators <- CLI / UI`. Follow the executable
[architecture policy](../docs/quality/architecture-policy.md) for the complete
role map, permitted imports, and canonical external-system boundaries.

## Change and validation expectations

- Inspect the relevant contracts, configuration, tests, documentation, and
  current behavior before changing code.
- Keep changes surgical; do not add compatibility layers, speculative options,
  or generic abstractions without a current need.
- Use `AppError` for expected application failures, keep retries explicit in
  orchestrators, and preserve idempotency at repeatable external-write
  boundaries.
- Test observable behavior without monkeypatching private implementation
  details. Update the relevant documentation pack with every code change.
- Start with focused checks, then use the repository quality gates appropriate
  to the risk. The default suite is `python -m pytest`; the documented release
  gates are listed by `python scripts/ci/run_quality_gate.py --list`.

For pull-request structure, use the repository
[pull-request template](pull_request_template.md).
