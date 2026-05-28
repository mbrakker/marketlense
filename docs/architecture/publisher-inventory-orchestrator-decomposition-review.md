# Publisher Inventory Orchestrator Decomposition Review

Date: 2026-05-28

## Decision

`src/orchestrators/publisher_inventory_orchestrator.py` remains the canonical public orchestrator entrypoint for publisher inventory discovery. The split is internal to the same bounded context and introduces private owner modules under `src/orchestrators/_publisher_inventory_orchestrator/`:

- `dependencies.py`: dependency contract and default service/generator wiring.
- `idempotency.py`: idempotency scopes, checksum builders, record/reuse helpers, and persisted outcome restoration.
- `snapshot_io.py`: previous snapshot loading and snapshot filename generation.
- `candidate_flow.py`: resource-quality ranking, provenance counts, deferred recovery-cache recording, rollout guardrail logging, and URL-domain extraction.
- `runtime.py`: failure status mapping, time-budget checks, settings budget clamping, discovery retry wrapping, and UTC timestamp generation.

`run_publisher_inventory_discovery()` stays in the public module and remains the only workflow entrypoint.

## Architecture Trigger

This change creates more than three private peer modules, so it triggers the mandatory architecture review gate. It preserves the modular monolith: no new top-level package, deployable unit, queue, worker, external service boundary, schema, prompt namespace, or alternate orchestrator path is introduced.

The boundary is semantic rather than structural. Each moved module owns a stable helper family already visible in the former public file, while the public coordinator continues to own route sequencing, branching, retries, state transitions, and side-effect order.

The same outcome could not be achieved with fewer modules without combining unrelated helper families. In particular, dependency wiring, idempotency restoration, snapshot I/O, candidate post-processing, and runtime budget enforcement change for different reasons and are tested through different observable effects.

## Behavior Preservation

The decomposition is movement-only. It does not change:

- route order or fallback conditions
- retry/backoff policy
- idempotency scopes, keys, checksums, or restored payload semantics
- Drive upload/download behavior
- report-store write behavior
- candidate ordering or screening/quality calls
- logging event names
- dataclass contracts or schema versions
- prompt/config/provider interaction

Compatibility imports continue through `src.orchestrators.publisher_inventory_orchestrator`.

## Verification Evidence

Pre-move focused publisher inventory suite:

```powershell
python -m pytest tests/test_publisher_inventory_orchestrator.py tests/test_publisher_inventory_decomposition.py tests/test_publisher_inventory_service tests/test_publisher_inventory_candidate_screening_generator.py tests/test_publisher_inventory_candidate_quality_generator.py -q
```

Result: `195 passed, 7 warnings`.

Pre-move ownership test:

```powershell
python -m pytest tests/test_publisher_inventory_orchestrator_decomposition.py -q
```

Result: failed as expected because the new owner modules did not exist.

Post-move focused suite:

```powershell
python -m pytest tests/test_publisher_inventory_orchestrator_decomposition.py tests/test_publisher_inventory_orchestrator.py tests/test_publisher_inventory_decomposition.py tests/test_publisher_inventory_service tests/test_publisher_inventory_candidate_screening_generator.py tests/test_publisher_inventory_candidate_quality_generator.py tests/test_config_service.py tests/test_cli.py -q
```

Result: `250 passed, 7 warnings, 5 subtests passed`.

Split-symbol gate:

```powershell
python scripts/ci/check_split_symbol_links.py
```

Result: passed.

AST movement audit:

```powershell
python - <<'PY'
# Compared moved definitions/constants against HEAD:src/orchestrators/publisher_inventory_orchestrator.py
PY
```

Result: `39` expected moved symbols/constants found in both old and new locations, `39` unchanged by AST dump.

Configured CI-equivalent gates:

- `python scripts/ci/check_formatting.py`: passed.
- `python scripts/ci/check_risk_policy.py`: passed; change classified as critical.
- `python scripts/ci/check_split_symbol_links.py`: passed.
- `python scripts/ci/run_type_check.py`: passed.
- `python scripts/ci/check_architecture_imports.py`: passed.
- `python scripts/ci/check_forbidden_patching.py`: passed.
- `python scripts/ci/check_repository_hygiene.py`: passed.
- `python scripts/ci/check_quality_ledger.py`: passed.
- `python scripts/ci/check_remediation_runbooks.py`: passed.
- `python scripts/ci/check_backlog_source.py`: passed.
- `python scripts/ci/check_contract_schemas.py --snapshot docs/quality/contract_schemas.json`: passed.
- `python scripts/ci/check_wordpress_subproject.py`: passed.
- `python -m pytest --cov=src --cov-report=xml --cov-report=term-missing`: `2641 passed, 17 deselected, 33 warnings`.
- `python scripts/ci/check_coverage.py --coverage-xml coverage.xml`: passed; global coverage `82.69%`.
- `python scripts/ci/run_mutation_gate.py --json-out mutation_results.json`: passed.
- `python scripts/ci/check_quality_regression.py --baseline docs/quality/baseline_2026-02-21.json --coverage-xml coverage.xml --mutation-json mutation_results.json --docpack-root tests/fixtures/docpacks/golden`: passed.
- `python scripts/ci/check_prompt_fixture_regression.py --baseline docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json --config src/config/app.yaml --iterations 3`: passed.

## Live Baseline

The pre-move isolated real orchestrator canary baseline was captured outside the repository at:

`C:\Users\8FEE~1\AppData\Local\Temp\market-lense-publisher-orchestrator-baseline.json`

The canaries used live Capgemini, Bain, and Cardlytics publisher URLs with temporary SQLite/report output paths and local Drive dependency doubles. Real model calls were allowed. No real Drive writes were performed.

Post-move live canary comparison:

| Canary | Baseline Median | Post Median | Runtime Ratio | Count/Contract Result |
| --- | ---: | ---: | ---: | --- |
| Capgemini direct detail | `1.161s` | `1.106s` | `0.953` | matched |
| Bain filtered archive | `27.928s` | `25.576s` | `0.916` | matched |
| Cardlytics mixed hub | `9.132s` | `8.992s` | `0.985` | matched |

The post-move run matched normalized `PublisherInventoryDiscoveryResult` payloads, current/new/previous counts, run-quality summaries, source-row summaries, state-row summaries, model-call ledger counts, and baseline log-event coverage. Canonical `inventory_snapshot_sha256` values matched exactly for all canaries. Raw upload payload SHA values were not used as the comparator because the upload JSON contains capture-time fields; upload sizes and canonical snapshot hashes matched.
