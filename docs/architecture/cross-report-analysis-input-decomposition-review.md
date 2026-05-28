# Cross-Report Analysis Input Decomposition Review

## Decision

`src/generators/cross_report_analysis_input_generator.py` remains the stable
generator compatibility facade used by the cross-report orchestrator, CLI, and
tests. Focused implementation now lives under:

```text
src/generators/_cross_report_analysis_input/
  shared.py
  source_selection.py
  theme_selection.py
  evidence_signals.py
```

This is a movement-only modular-monolith decomposition. It introduces no new
public generator entrypoint, external I/O boundary, prompt namespace, schema
version, orchestrator path, model call, or publication path.

## Review Trigger

The change introduces more than three private peer modules, which triggers the
architecture review required by `AGENTS.md`.

## Required Review Answers

### Is this preserving a modular monolith, or drifting toward fragmentation?

It preserves the modular monolith. Cross-report input preparation remains one
generator facade, while the private modules stay inside the same bounded
cross-report generator capability.

### Is the new boundary semantic, or only structural?

It is semantic. `shared.py` owns deterministic normalization and shared score
helpers. `source_selection.py` owns projected-source filtering and selection.
`theme_selection.py` owns theme candidates, recent-theme rotation, novelty, and
publishability checks. `evidence_signals.py` owns evidence/raw-metric assembly,
signal scoring, and evidence agreement grouping.

### Can the same outcome be achieved with fewer modules and the same testability?

A two-module split would couple source/theme ranking with evidence/signal
assembly, or would mix file-service recent-theme reads with pure signal scoring.
Four private modules are the smallest split that keeps the existing generator
entrypoints readable without creating forwarding-only layers.

### Does this reduce total cognitive load for the next engineer?

Yes. The orchestrator and tests still use one facade, while changes to source
selection, theme rotation, publishability, evidence assembly, or signal
agreement can be inspected in one focused owner.

## Preserved Behavior

- Scoring weights, filter normalization, candidate ordering, theme rotation,
  publishability rules, evidence limits, signal scoring, agreement grouping,
  logging events, typed errors, prompt inputs, model-call count, and cost
  behavior are unchanged.
- Existing imports through
  `src.generators.cross_report_analysis_input_generator` continue resolving.
- The private dependency direction is acyclic: implementation modules may
  consume `shared.py`; `evidence_signals.py` does not import source or theme
  implementation modules.

## Verification Evidence

Pre-move baseline:

- `python -m pytest tests/test_cross_report_analysis_input_generator.py tests/test_cross_report_analysis_orchestrator.py -q`
  -> `48 passed`.

Implementation evidence:

- The new decomposition ownership test failed before extraction because
  `_cross_report_analysis_input/` did not exist, then passed after extraction.
- AST movement audit compared moved definitions/constants against
  `HEAD:src/generators/cross_report_analysis_input_generator.py`: `51` moved
  symbols/constants unchanged, `0` changed.

Post-move synthetic evidence:

- `python scripts/ci/check_split_symbol_links.py` passed.
- Focused affected suite passed:
  `python -m pytest tests/test_cross_report_analysis_input_decomposition.py tests/test_cross_report_analysis_input_generator.py tests/test_cross_report_analysis_orchestrator.py tests/test_cross_report_analysis_generator.py tests/test_cross_report_analysis_contracts.py tests/integration/test_analytics_store_cross_report_reads.py tests/test_cli.py -q`
  -> `174 passed, 4 deselected`.
- Full coverage suite passed:
  `python -m pytest --cov=src --cov-report=xml --cov-report=term-missing`
  -> `2645 passed, 17 deselected`.
- Coverage gate passed: global `82.71%`, generators `86.60%`,
  orchestrators `84.56%`, services `82.12%`.
- Formatting, risk policy, type checking, architecture imports, forbidden
  patching, repository hygiene, quality ledger, remediation runbooks, backlog
  source, contract schemas, WordPress subproject, mutation, prompt fixture
  regression, and quality regression gates passed.
- The first prompt fixture run failed on runtime-only variance while tokens,
  expected calls, browser attempts, and estimated cost were unchanged; the
  immediate rerun passed.

Live-canary evidence:

- Isolated real cross-report canary used temp projection SQLite, temp
  idempotency DB, temp output root, real prompt rendering, and a real
  `gpt-5-mini` model call. No WordPress live publish was enabled.
- Two initial real model attempts failed validation because the provider
  returned malformed citations: first unknown evidence IDs, then raw metric IDs
  in the evidence field. This was external model-output variance on the canary
  fixture, not a deterministic input-preparation mismatch.
- The final real canary used claim/finding/quote evidence only and passed:
  status `validated`, validation `pass`, selected reports
  `["report-b", "report-a"]`, selected theme `theme-tag-ai`, signals
  `["signal-ai", "signal-retail"]`, publish status `not_requested`, model
  `gpt-5-mini`, total tokens `6035`, artifact persisted, elapsed `40.374s`.
