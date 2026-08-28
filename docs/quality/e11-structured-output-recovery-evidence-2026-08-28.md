# E11 Structured-Output Recovery Effectiveness Evidence

> **Evidence date:** 2026-08-28
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

This is a measured telemetry and safe-repair foundation, not closure evidence
for E11. No fresh representative retained/live cohort with the new terminal
events exists yet, so no production first-pass, repair-cost, or terminal-failure
improvement is claimed. E11 remains active until a compatible post-change
cohort demonstrates a material observed improvement with unchanged
schema/grounding/editorial gates.
