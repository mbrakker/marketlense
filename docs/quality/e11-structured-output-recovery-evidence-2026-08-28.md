# E11 Structured-Output Recovery Effectiveness Evidence

> **Evidence date:** 2026-08-29
> **Scope:** Read-only aggregation of the retained standard-log shards from
> 2026-08-25 through 2026-08-28. These logs include historical automated and
> representative processing activity; this is not a fresh live cohort.

## Observed retained baseline

The read-only scorecard produced 5,038 output-level recovery observations. Its
JSON report hash was
`7849eafff4a04bd392819b20f1577f45f4b2e28375915e194cdee20a6cfc8bc4`.

### Reproduction manifest

The scorecard was generated read-only with:

```powershell
python scripts/quality/structured_output_recovery_effectiveness.py `
  --log logs/market_lense_2026-08-25.log `
  --log logs/market_lense_2026-08-26.log `
  --log logs/market_lense_2026-08-27.log `
  --log logs/market_lense_2026-08-28.log `
  --output out/e11_retained_recovery_effectiveness_20260828.json
```

The output is an ignored local evidence artifact at the stated path; its SHA-256
is the hash above. The explicit dated standard-log shard paths are the input
manifest, so a reviewer with the retained logs can reproduce the aggregation
without access to raw prompt or response content.

| Metric | Retained baseline |
| --- | ---: |
| First-pass valid rate | 91.624% |
| Deterministic-repair success rate | 0.000% |
| Model-repair success rate | 20.074% |
| Terminal failure rate | 7.285% |
| Repair attempts per output | 0.096 |
| Repair input/output tokens | 42,092 / 5,437 |
| Estimated repair cost | $0.031435 |
| Observed repair time | unavailable for legacy records |

The most costly retained classes were `structured_output_empty` (55 outputs,
27 terminal failures, $0.014920), `empty_response` (26 terminal failures,
$0.007800), and `invalid_json` (53 outputs, 26 terminal failures, $0.005265).
`schema_missing_required` was the highest-volume terminal class (135 outputs)
but has no cost attribution in this legacy scope. The highest single recoverable
call was one taxonomy `invalid_json` model repair ($0.004563); the historical
telemetry cannot retain its raw malformed text, so that record does not prove a
specific transport defect and did not justify a heuristic repair.

Legacy events do not retain workflow, schema, provider/model, or elapsed-time
attribution consistently. The baseline therefore marks those dimensions as
`partial`, rather than inferring values from unrelated usage records.

## Change and deterministic proof

The service now retains one typed terminal outcome for every execution and the
scorecard uses those outcome events preferentially over individual attempt
events. New events provide the missing attribution and rate denominators while
leaving provider calls, schemas, semantic checks, grounding, and the
three-attempt ceiling unchanged.

A narrow, quote-aware deterministic transport repair now converts literal JSON
control newlines inside an already-delimited string to their JSON escape. It
cannot add fields, close a structure, change a type, or bypass validators. The
focused deterministic replay shows the exact before/after effect for that
transport class: two provider calls with one repair call (11 repair input and
7 repair output tokens in the fixed response) become one primary call and zero
repair calls/tokens. Malformed, parseable semantic-invalid, missing-field,
wrong-type, and unsupported-property cases still exhaust the existing bounded
path and fail closed.

## Status

Closed on the scoped post-change cohort below. The observed improvement is
real and retained, but it is a three-document current-model cohort compared
with partially attributed historical telemetry; it is an operational result,
not a causal claim about a single model or repair alone.

## Earlier bounded validation (2026-08-29)

Three credentialed OpenAI integration-smoke invocations passed against the
current service boundary. Each invocation was independently bounded and made
no publication, Drive write, or WordPress call. The focused deterministic and
scorecard regressions also passed (39 tests).

An attempted three-PDF retained-cohort replay was correctly rejected before
provider work because the retained manifest's configuration/policy provenance
does not match the current admission configuration. A new empty isolated state
also correctly rejected its Drive candidates as missing canonical
source-identity evidence. These are fail-closed admission safeguards, not
structured-output recovery observations. No provenance check was bypassed, and
no recovery-effectiveness improvement is claimed from these runs.

Those preliminary attempts did not establish closure; the fresh cohort below
was then admitted with current provenance and executed the normal pipeline.

### Canonical retained replay

The approved `corpus_rehab_2b9799be10ecba64cc4ddd8d` campaign subsequently
processed the three canonical retained reports through the `artifact_repair`
queue. All three jobs succeeded, with 87, 91, and 219 validated artifacts
reused respectively. Its planned and actual provider-call counts were both
zero, and no report-analysis or publication job was queued. This is successful
safe retained replay evidence, but intentionally produces no new
structured-output recovery outcomes; it does not change the E11 status.

## Fresh isolated post-change cohort (2026-08-29)

Run `9f51aea0-ba99-4960-a23b-052ac9f21072` admitted and processed three
canonical-source PDFs through the normal Drive, acquisition, ingest, analysis,
validation, and local publish-readiness path. The isolated reports database
retained only canonical source-identity provenance; all derived report records
and artifacts were cleared before admission, preventing E9 artifact reuse from
entering the measurement. The run was bounded to three PDFs and $6.00; it made
85 provider calls (756,312 input / 77,923 output tokens; $0.244772 total).

The canonical run-filtered scorecard was generated with:

```powershell
python scripts/quality/structured_output_recovery_effectiveness.py `
  --log logs/market_lense_2026-08-29.log `
  --run-id 9f51aea0-ba99-4960-a23b-052ac9f21072 `
  --output out/e11_live_recovery_20260829/structured-output-recovery-scorecard.json
```

Its ignored local evidence artifact has SHA-256
`852c6c8ebc6e344948b1dfc4768bb4f64bbd32b42607c6fea839fb45424675e7`.
All 74 structured-output terminal outcomes were attributed to
`report_analysis` / `openai:gpt-5.6-luna` and had a first-pass-valid result:

| Metric | Retained baseline | Fresh cohort | Observed change |
| --- | ---: | ---: | ---: |
| Structured output observations | 5,038 | 74 | — |
| First-pass valid rate | 91.624% | 100.000% | +8.376 percentage points |
| Repair attempts per output | 0.096 | 0.000 | -0.096 |
| Repair input/output tokens | 42,092 / 5,437 | 0 / 0 | eliminated in cohort |
| Estimated repair cost | $0.031435 | $0.000000 | eliminated in cohort |
| Terminal structured-output failure rate | 7.285% | 0.000% | -7.285 percentage points |

The cohort preserved schema, semantic, grounding, and editorial validation;
structured-output recovery made no model-repair call and did not bypass any
validator. Two reports completed successfully. One separate report was held by
the existing publish-readiness gate after bounded content-quality regeneration;
this was not a structured-output failure and no substitute was selected.

A guarded `publish-wp --require-full-validation-manifest` attempt then stopped
at `validation_cohort_publication_not_ready` before any HTTP request or
WordPress write. WordPress credentials were blank and the isolated profile set
the WordPress-write budget to zero. This verifies the intended safe terminal
state without claiming a publication success.
