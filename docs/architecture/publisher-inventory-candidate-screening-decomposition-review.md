# Publisher Inventory Candidate Screening Decomposition Review

Date: 2026-05-28

## Decision

`src/generators/publisher_inventory_candidate_screening_generator.py` remains the stable generator import surface. Implementation is split into private `_publisher_inventory_candidate_screening/` capability owners for shared marker normalization, deterministic screening policy, response policy, and LLM batch execution.

This preserves the modular monolith. It does not introduce a new generator entrypoint, service boundary, prompt namespace, provider path, schema, or orchestration route.

## Boundary Rationale

The previous module combined deterministic URL/title prefilters, fallback screening decisions, prompt rendering, model-call batching, missing-decision repair, response adaptation, duplicate collapse, and publisher-success hard rejection. The new private modules split those stable semantic responsibilities while preserving the existing facade and public generator entrypoint.

The split creates more than three private peer modules, so this review is required. The boundary is semantic rather than size-only: deterministic no-model policy can be inspected separately from LLM batch execution and response post-processing, while callers still import through one generator facade.

## Verification Evidence

- Pre-refactor focused suite: `python -m pytest tests/test_publisher_inventory_candidate_screening_generator.py tests/test_publisher_inventory_candidate_quality_generator.py tests/test_publisher_inventory_orchestrator.py tests/test_publisher_inventory_orchestrator_decomposition.py tests/test_publisher_inventory_service tests/test_publisher_inventory_decomposition.py tests/test_config_service.py tests/test_cli.py -q` passed with `250 passed`.
- Pre-refactor deterministic baseline: `C:/Users/8FEE~1/AppData/Local/Temp/publisher_screening_baseline_pre_7ataf8ka/baseline.json`
- Red ownership test before movement: `python -m pytest tests/test_publisher_inventory_candidate_screening_decomposition.py -q` failed because `_publisher_inventory_candidate_screening/` modules did not exist.
- Post-refactor affected suite: `python -m pytest tests/test_publisher_inventory_candidate_screening_decomposition.py tests/test_publisher_inventory_candidate_screening_generator.py tests/test_publisher_inventory_candidate_quality_generator.py tests/test_publisher_inventory_orchestrator.py tests/test_publisher_inventory_orchestrator_decomposition.py tests/test_publisher_inventory_service tests/test_publisher_inventory_decomposition.py tests/test_config_service.py tests/test_cli.py -q` passed with `253 passed`.
- Post-refactor deterministic baseline: `C:/Users/8FEE~1/AppData/Local/Temp/publisher_screening_baseline_pre__q9e7fdz/baseline.json`
- Pre/post deterministic baseline comparison, excluding temp root and elapsed wall time, was exact: 3 approved items, 2 rejected items, 5 decisions, zero LLM requests for the deterministic fixture.
- CI-equivalent gates passed: formatting, risk policy, split-symbol links, type check, architecture imports, forbidden patching, repository hygiene, quality ledger, remediation runbooks, backlog source, contract schemas, WordPress subproject, full pytest coverage, coverage threshold, mutation gate, quality regression, and prompt fixture regression.
- Full pytest coverage gate: `2651 passed, 17 deselected`; coverage XML generated at `coverage.xml`.
- Coverage gate: global `82.75%`, orchestrators `84.56%`, generators `86.63%`, services `82.16%`.
- Mutation gate passed with unchanged accepted surviving mutants outside this split's changed files.
- Real LLM canary: loaded keys from `.env` into the canary process only, then ran isolated `screen_publisher_inventory_candidates()` with three LLM-path candidates, temp output and cost-ledger paths, and no browser/orchestrator/Drive/report-DB side effects. The canary completed in `10.792s` with one `gpt-5-nano` model call, request ID present, valid JSON response, 3 approved candidates, 0 rejected candidates, and one temp cost-ledger entry at `C:\Users\8FEE~1\AppData\Local\Temp\publisher_screening_live_94gopumc\cost-ledger.jsonl`.

## Movement Audit

The AST movement audit compared moved definitions/constants against `HEAD:src/generators/publisher_inventory_candidate_screening_generator.py`.

- Moved symbols audited: 55
- AST-identical moved symbols: 55
- Changed moved symbols: 0
- Facade-owned definitions after split: `screen_publisher_inventory_candidates`
