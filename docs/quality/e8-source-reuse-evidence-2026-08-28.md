# E8 canonical-source reuse evidence — 2026-08-28

> **Evidence type:** Deterministic local fixture, retained-corpus benchmark, and regression evidence
> **Scope:** Canonical source identity duplicate suppression
> **Status:** Complete for the supported resolved-identity and exact-content-hash path; exact-HEAD CI and release-evidence review passed.

## Fixture result

The focused fixture path records a retained package owner and presents the same
content through a different Drive/email/file-style reference. With a resolved
canonical identity and exact `md5:` content hash, the resolver selects the
original package deterministically. A ready package stops the duplicate before
acquisition and report research. A stale readiness package reuses through
`analysis_complete` and regenerates only `render_complete` against the
canonical owner; it makes zero duplicate acquisition calls.

The persisted row stores `1` avoided Drive acquisition action because the
resolved duplicate is stopped before its otherwise-required Drive download.
Browser launch, PDF parsing, OCR, extraction, and vector-work counters are
`0`: this Drive route neither bypasses a browser-backed route nor proves that
those conditional operations would have run. It stores model calls,
input/output tokens, and estimated cost as `0` with attribution state
`unavailable`: this fixture does not make a provider call and must not infer a
provider saving from elapsed test time.
The owner package count remains one; the duplicate receives a skipped outcome
or an outcome mapped from the owner repair, not a second independent package.

## Retained-corpus benchmark

The benchmark used the retained StackAdapt source owner
`1zt4RcZ-7dFNtf9zVWK2kUMpqJMSouUGn`, canonical identity
`source:038b017d7942e0bcce44627e5c9ff227`, and exact content hash
`md5:8ef1021c332aa85ba008da58ff8ec866`. It compared the retained fresh run
`8c48cb67-7851-4bc1-b533-787e168b8eea` with seven independent reuse lookups
against a temporary SQLite backup. It made no network, provider, browser,
Drive, or WordPress calls and did not alter the retained databases.

| Measure | Fresh retained run | Canonical duplicate replay |
| --- | ---: | ---: |
| Completed model calls | 17 | 0 |
| Input/output tokens | 131,302 / 14,837 | 0 / 0 |
| Estimated provider cost | $0.044064 | $0 |
| Provider-work span / reuse-resolution median | 90,295.028 ms | 21.670 ms |
| Acquisition/browser/PDF/OCR/extraction/vector actions | retained fresh work | 0 / 0 / 0 / 0 / 0 / 0 |
| Resolved owner / duplicate packages created | n/a | 7/7 / 0 |

All seven replays selected the same owner and the same retained HTML digest
`e7fe37b8da4edc29012e7da216f91e373a0e813372a22a2cea139201e1adce5f`.
The fresh timing is deliberately labeled a completed-provider-work span and
the candidate timing a pre-acquisition resolver measurement; this is evidence
of the suppression boundary, not a claim of an equivalent full-workflow
wall-time measurement. The generated scalar-only record is
`out/e8-source-reuse-benchmark-2026-08-28.json`.

## Commands and results

```powershell
python -m pytest -q tests/test_report_source_reuse.py
python -m pytest -q tests/test_ingest_file_orchestrator.py -k stale_canonical
python -m pytest -q tests/test_source_reuse_benchmark.py
python scripts/quality/benchmark_source_reuse.py --reports-db state/p12_p14_canary_20260826/reports.sqlite --usage-db state/p12_p14_canary_20260826/llm_usage.sqlite --owner-report-id 1zt4RcZ-7dFNtf9zVWK2kUMpqJMSouUGn --baseline-run-id 8c48cb67-7851-4bc1-b533-787e168b8eea --repeats 7 --output-json out/e8-source-reuse-benchmark-2026-08-28.json
python scripts/ci/check_contract_schemas.py --snapshot docs/quality/contract_schemas.json
```

The release-verification focused suite passed 40 tests across source reuse,
ingest-file recovery, report-pipeline, benchmark, and migration compatibility
coverage. The stale-owner fixture passed with no duplicate download and
persisted analysis-complete/render-only telemetry. The retained benchmark
passed with seven deterministic owner resolutions and zero candidate expensive
work. The contract schema gate passed after adding the typed telemetry
contracts.

## Guarded workflow validation

The isolated `gpt_5_6_luna_live_validation_20260825` overlay was loaded over
`src/config/app.yaml` through `MARKET_LENSE_CONFIG_PROFILE`. Its bounded ingest
run `d3885f6f-d6fa-4850-8087-806bf3c13b79` admitted no report because the one
selected Drive source had an unproven identity; it therefore failed closed
before PDF or model work. The guarded publish run
`bf3cc751-1e93-416c-a736-f0e7efb6a489` completed with the retained package
recorded as `wordpress_write_budget_zero`: no WordPress credential, target
preflight, or write was used. This verifies the existing validation and
publication safeguards remain in place for the E8 change.

## Scope and fail-closed limit

This evidence covers only reports with a `resolved` canonical source identity,
the same exact MD5 content hash, and a retained owner whose package remains
compatible. Changed bytes, conflicting/legacy/missing/ambiguous identity,
missing MD5 evidence, incomplete owners, and stale incompatibilities do not
reuse at this boundary; they continue through normal processing or the existing
minimum-regeneration path. The benchmark does not establish performance for
those unsupported cases, nor does it substitute the completed-provider span
for an end-to-end workflow duration.
