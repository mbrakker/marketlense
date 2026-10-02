# Per-report timeout rerun — 2026-10-02

## Scope and method

This replay selected only the seven reports that had ended as
`ias_canary_timeout` in the retained 2026-10-01 frozen 20-report run. Each was
run separately through the canonical production queue workflow with fresh
isolated state. No other member of the 20-report manifest was submitted.

The prior run had ten reports reach readiness. Their measured active
`wall_time_ms`, summed per report over `source_ingest`, `report_selection`,
`report_analysis`, `report_render`, and `publication_readiness`, averaged
491.9668 seconds. The rerun limit was `ceil(2 × 491.9668) = 984` seconds for
each report. All seven completed within that individual limit.

The canary stopped at publication readiness. No `wordpress_publish` jobs were
created. Readiness made zero provider calls. The replay used implementation
revision `06e58098a6a8199ed374b966a66b55d99b7a6e18`.

The execution selected these stable report IDs from the 20-member frozen
manifest:

```text
cohort-2acb4a56e14add5d7717 cohort-11b0b55157f7d0636815
cohort-77bc67b2bc98187d9d58 cohort-0a019f840c3f89ad0a96
cohort-b10ed6c82b76739a806a cohort-f62048b469dd784e6e7c
cohort-f1652970000cfe246c94
```

Focused verification passed with `python -m pytest
tests/test_frozen_reliability_cohort_runner.py -q` (15 passed) and Ruff on the
changed Python files.

## Outcomes

| Report | Outcome | Elapsed (s) | Calls | Input tokens | Output tokens | Cost (USD) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| KPMG | Readiness pass; awaiting review | 540.004 | 36 | 347,902 | 65,420 | 0.066660 |
| Merchant Risk Council | `report_card_manifest_write_failed` | 409.080 | 27 | 186,085 | 52,395 | 0.043965 |
| Bain & Company | `validation_failed` (`expert_comment`, numeric grounding) | 573.209 | 34 | 194,569 | 68,459 | 0.051307 |
| Bigcommerce | `report_card_manifest_write_failed` | 659.358 | 32 | 299,576 | 70,844 | 0.064538 |
| Deloitte | `report_card_manifest_write_failed` | 562.827 | 27 | 268,926 | 62,263 | 0.057182 |
| Emplifi | `report_card_manifest_write_failed` | 485.212 | 27 | 289,070 | 55,075 | 0.055770 |
| SimilarWeb | `report_card_manifest_write_failed` | 516.676 | 36 | 252,287 | 55,932 | 0.052016 |

## Aggregate statistics

- Reports replayed: 7/7; all admitted.
- Readiness passes: 1/7; six reports remained blocked by typed terminal errors.
- Timeout outcomes: 0/7. Maximum individual elapsed time was 659.358 seconds,
  below the 984-second limit.
- Failure codes: five `report_card_manifest_write_failed`, one
  `validation_failed`.
- Provider calls: 219; input tokens: 1,838,415; output tokens: 430,388.
- Cost: $0.391438. Sum of per-report elapsed time: 3,746.366 seconds
  (62m 26s); mean: 535.195 seconds.
- Provider calls during readiness: 0. Publication jobs: 0.

The timeout change removed the shared-cohort cutoff for these reruns. It did
not resolve the separate rendering and numeric-grounding failures above.

## Retained machine-readable result

[cohort_result.json](cohort_result.json) contains each report's typed outcome,
diagnostic, lineage IDs, per-report usage, elapsed time, and aggregate summary.
The isolated execution artifacts remain under the ignored `tmp/` directory
recorded in that result.
