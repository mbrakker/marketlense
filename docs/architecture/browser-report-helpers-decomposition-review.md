# Browser Report Helper Decomposition Review

## Decision

`src/services/browser_report_download_service.py` remains the single public
browser-download service boundary. The private compatibility surface remains
`src/services/_browser_report_download/helpers.py`, while focused helper
implementation now lives under:

```text
src/services/_browser_report_download/_helpers/
  state.py
  inspection.py
  interaction.py
```

This is a movement-only modular-monolith decomposition. It introduces no new
deployable component, public service entrypoint, prompt/config/schema change,
provider path, browser route, or upload behavior.

## Review Trigger

The change introduces three private peer modules, which triggers the
architecture review required by `AGENTS.md`.

## Required Review Answers

### Is this preserving a modular monolith, or drifting toward fragmentation?

It preserves the modular monolith. Callers continue importing the same helper
surface through `helpers.py`, and all implementation remains inside the
existing browser-report download service family.

### Is the new boundary semantic, or only structural?

It is semantic. `state.py` owns deterministic page metadata, load waits, and
real-tab diagnostics. `inspection.py` owns JavaScript result/error adaptation
and bounded static HTTP inspection. `interaction.py` owns screenshots,
coordinate fallback policy/execution, and autocomplete recovery.

### Can the same outcome be achieved with fewer modules and the same testability?

A two-module split would combine either state diagnostics with JavaScript/HTTP
inspection or user interactions with state reads. Those concerns have different
contracts, browser hooks, and failure events. Three modules are the smallest
split that isolates the existing helper responsibilities without adding
pass-through layers.

### Does this reduce total cognitive load for the next engineer?

Yes. The stable import path remains one module, while debugging a failed helper
result now points to the relevant owner: page state, inspection, or interaction.

## Preserved Behavior

- Helper return contracts, schema versions, event names, typed errors, CDP
  calls, JavaScript wrapping, screenshot behavior, HTTP acquisition policy,
  timeouts, branch order, and browser/model cost behavior are unchanged.
- `helpers.py` re-exports the previous private helper symbols for current
  browser runtime, preflight, and test-builder imports.
- The dependency direction is acyclic: `state` has no helper-sibling
  dependency, `inspection` may consume `state`, `interaction` may consume both,
  and `helpers.py` imports the private owners.

## Verification Evidence

Pre-move baseline:

- Focused helper contract suite passed before movement:
  `python -m pytest tests/test_browser_download_helpers.py -q`
  -> `13 passed`.

Implementation evidence:

- The new ownership test failed before extraction because
  `_browser_report_download/_helpers/` did not exist, then passed after
  extraction.
- AST movement audit compared moved definitions/constants against
  `HEAD:src/services/_browser_report_download/helpers.py`: `54` moved
  symbols/constants unchanged, `0` changed.

Post-move synthetic evidence:

- `python scripts/ci/check_split_symbol_links.py` passed.
- Focused affected suite passed:
  `python -m pytest tests/test_browser_download_helpers.py tests/test_browser_download_helpers_decomposition.py tests/test_browser_report_download_runtime_decomposition.py tests/test_browser_report_download_http_decomposition.py tests/test_browser_report_download_artifact_decomposition.py tests/test_browser_report_download_service tests/test_browser_report_download_cdp.py tests/test_browser_report_download_doc_type_predictor.py tests/test_cli.py -q`
  -> `186 passed`.

Live-gate evidence:

- The first guarded integration invocation skipped because
  `OPENROUTER_API_KEY` was not exported in the shell environment.
- After loading `OPENROUTER_API_KEY` from local `.env` into the child process
  without printing it, the guarded local browser-download integration passed:
  `RUN_BROWSER_DOWNLOAD_INTEGRATION=1 python -m pytest -m integration tests/integration/test_browser_report_download_service.py -q -rs`
  -> `1 passed` in `56.65s`.
- The live run used the existing local fixture and emitted the pre-existing
  browser-use/backoff deprecation warnings plus a pending browser reconnect
  teardown diagnostic. This decomposition does not suppress or reinterpret
  those runtime diagnostics.
