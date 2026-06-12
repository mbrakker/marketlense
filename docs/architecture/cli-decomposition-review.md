# CLI Decomposition Review

Generated: 2026-06-12

## Scope

This review covers the movement-only split of `src/cli.py` into private
command-family owner modules under `src/_cli/`.

The public CLI boundary remains `src.cli`. Operators still invoke commands with
`python -m src.cli`, and existing tests and callers can still import or patch
the same `src.cli` symbols.

## Architecture Review

- Modular monolith preservation: the split stays inside the existing `src/`
  deployable and introduces no new process, package, service boundary, queue,
  or external integration path.
- Boundary semantics: `src.cli` remains the single canonical CLI boundary.
  Private owner modules are grouped by command capability: app bootstrap,
  shared helpers, report pipeline commands, browser diagnostics/downloads,
  publisher inventory, cross-report analysis, private-API playbook promotion,
  trace rendering, admin commands, and UI-run commands.
- Cognitive load: command implementations no longer share one 1,979-line
  module. Each command family can be read in one private owner while discovery
  still starts at `src.cli`.
- Indirection budget: the only compatibility indirection is the `src.cli`
  facade and runtime patch-point synchronization for existing public `src.cli`
  test seams. No second CLI entrypoint was added.
- External behavior: Typer command names, options, default command behavior,
  logs, orchestrator/service calls, cost-triggering paths, retry behavior,
  prompt behavior, and artifact paths were not intentionally changed.

## Owner Modules

- `src/_cli/app.py`: Typer app construction, callback, and `main`.
- `src/_cli/common.py`: pure shared CLI time/path helpers.
- `src/_cli/pipeline.py`: ingest, candidate extraction, WordPress publishing,
  recategorization, cover generation, category update, and cost reporting.
- `src/_cli/browser.py`: report-download and browser-doctor commands.
- `src/_cli/publisher.py`: publisher discovery and acquisition-path audit.
- `src/_cli/cross_report.py`: cross-report CLI request construction and command.
- `src/_cli/private_api.py`: private-API playbook promotion request loading and
  command.
- `src/_cli/trace.py`: structured log loading, trace depth calculation, and
  trace rendering command.
- `src/_cli/admin.py`: Drive OAuth and publisher sync commands.
- `src/_cli/ui_runs.py`: replay and worker commands for UI-run control.

## AST Movement Audit

Audit source: `HEAD:src/cli.py`.

- Moved top-level symbols: `40`
- Unchanged moved symbols: `18`
- Changed moved symbols: `22`
- Facade-owned definitions after split: `0`
- Missing symbols: `0`

The changed moved symbols are command/helper functions that gained one runtime
patch-point synchronization call, plus the Typer default callback, which now
performs a lazy lookup through `src.cli` to avoid an import cycle while
preserving the default `ingest` behavior.

## Verification

- Red ownership test before movement:
  `python -m pytest tests/test_cli_decomposition.py -q` failed with `2 failed`
  because `src/cli.py` was 1,979 lines and `src/_cli/` owner modules did not
  exist.
- Post-split structure and affected behavior:
  `python -m pytest tests/test_cli_decomposition.py tests/test_cli.py tests/test_ui_run_control_orchestrator.py tests/test_ui_run_replay_orchestrator.py tests/test_run_registry_service.py -q`
  passed with `36 passed`.
- Touched-file syntax:
  `python -m compileall -q src\cli.py src\_cli` passed.
- Touched-file lint:
  `python -m ruff check src/cli.py src/_cli tests/test_cli_decomposition.py`
  passed.
- Full synthetic suite:
  `python -m pytest -q` passed with `2897 passed`, `19 deselected`,
  `22 warnings`, and `20 subtests passed`.
- Live CLI entrypoint checks:
  `python -m src.cli --help`,
  `python -m src.cli generate-cross-report-analysis --help`, and
  `python -m src.cli browser-doctor --help` all exited zero and showed the
  registered commands/options through the `src.cli` facade.
- Live command execution:
  `python -m src.cli cost-report --date 2026-01-01 --top 1` exited zero using
  real local settings and the local cost ledger path. It loaded configuration,
  emitted structured logs, and reported no matching ledger entries for that
  date without making LLM/API calls.
- Long-file scan:
  `python scripts/count_long_files.py --min-lines 500` reports no first-party
  `src` file at or above 1,000 lines.
