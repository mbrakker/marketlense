# Report-agnostic copy repair follow-up — 2026-10-01

This follow-up reran the same pinned five sources in the parent cohort pack:
Algolia, Bain & Company, Bigcommerce, Criteo, and DHL eCommerce. The source
manifest SHA-256 is
`fccce9143558f20b3f277f03e79c1b3cd78699fb3237f0336e1364a4cc1cda6d`. The
full 20-report cohort was not run.

The run used fresh isolated state and the production report workflow.
Publication was disabled; all five reports stopped at `awaiting_review`.
Generated prose, prompts, source extracts, and provider responses remain under
ignored `tmp/` storage. This folder retains the production-derived cohort
result and content-free hashes, typed outcomes, lineage checks, editorial
quality counts, and scalar usage metrics.

## Result

At implementation `eae746de7a6595b6dbddfcc69d7ad9ca8b26d2b6`, all five reports
passed validation and report-level publication readiness on the first
workflow attempt. All five final retained-claim packages match their final
artifact hashes, report/source identities, evidence, validator, configuration,
policy, publication-projection, and semantic-execution identities. Each
package has zero unsupported and unresolved factual claims. The retained
checks are in [`final_package_lineage.json`](final_package_lineage.json).

| Report | Validation | Readiness | Final state | Unsupported / unresolved claims |
| --- | --- | --- | --- | ---: |
| Algolia | pass | pass | `awaiting_review` | 0 / 0 |
| Bain & Company | pass | pass | `awaiting_review` | 0 / 0 |
| Bigcommerce | pass | pass | `awaiting_review` | 0 / 0 |
| Criteo | pass | pass | `awaiting_review` | 0 / 0 |
| DHL eCommerce | pass | pass | `awaiting_review` | 0 / 0 |

| Gate/evidence measure | Result |
| --- | ---: |
| Eligible final reports | 5/5 |
| Final packages materialized and lineage-bound | 5/5 |
| Report-level validation passes | 5/5 |
| Report-level readiness passes | 5/5 |
| Public-editorial quality passes | 5/5 |
| Public-editorial issues / hard failures / disabled waivers | 0 / 0 / 0 |
| Validation warnings | 0 |
| Readiness-stage provider calls | 0 |
| Publication attempts / published records / approvals | 0 / 0 / 0 |
| Operator interventions | 0 |

The database records five successful readiness jobs with empty provider-usage
and external-effect payloads. No WordPress publication or approval was
performed. The two `signal_candidate` jobs that ended with the typed
`cross_report_no_projected_sources` reason were optional cross-report work;
neither was a report terminal failure or affected readiness.

## Change and comparison

The shared report-copy and grounding prompts now require each factual finding
to remain an independently verifiable proposition, carry material source
qualifiers and population details, and bind chart/table labels to their visual
group rather than OCR order. Copy can stop when the retained source evidence
is narrow, instead of extending a post with unsupported bridge text. These
rules apply across publishers; no report-specific exception was added and no
validation or readiness rule was weakened.

The immediate predecessor measurement at `9db7f2e19b697517485926c0611e1126e5382343`
had 2/5 readiness passes and 0/5 validation passes. The comparison is between
stochastic provider runs and is not a controlled causal estimate.

| Measure | Predecessor (`9db7f2e`) | This run (`eae746d`) | Change |
| --- | ---: | ---: | ---: |
| Validation passes | 0/5 | 5/5 | +5 reports |
| Readiness passes | 2/5 | 5/5 | +3 reports |
| Typed terminal report failures | 3 | 0 | -3 |
| Provider calls | 220 | 173 | -47 (-21.36%) |
| Input tokens | 1,688,871 | 1,379,126 | -309,745 (-18.34%) |
| Output tokens | 596,703 | 333,098 | -263,605 (-44.18%) |
| Estimated cost | $0.446381 | $0.295323 | -$0.151058 (-33.84%) |
| Duration | 4,455.113 s | 2,537.774 s | -1,917.339 s (-43.04%) |

Usage totals cover the complete report workflow; the runner does not attribute
cost to individual reports. The per-report LinkedIn public-copy lengths were
Algolia 48 words, Bain 46, Bigcommerce 95, Criteo 47, and DHL eCommerce 62.
The shared prompt treats 180–280 words as a target and permits shorter
evidence-limited copy. These posts are concise; human review can expand them
when useful, without adding unsupported detail.

## Run identity

- Cohort run: `frozen-reliability-awmepi77`
- Isolated workflow directory: `ias-first-attempt-ii2fq93k`
- Implementation SHA: `eae746de7a6595b6dbddfcc69d7ad9ca8b26d2b6`
- Source-manifest SHA-256: `fccce9143558f20b3f277f03e79c1b3cd78699fb3237f0336e1364a4cc1cda6d`
- Cohort-result SHA-256: `a57721fece77e599317fd6178ac924a8a36e2c2a076315481925e71989df14c4`
- Predecessor-result SHA-256: `358af099e4c36b3d1fc0e41ae02a5673f664f8a665811d2957b5432f9c545223`
- Provider calls: `173`
- Input / output tokens: `1,379,126 / 333,098`
- Estimated provider cost: `$0.295323`
- Duration: `2,537.774 seconds`
- Publication: disabled; no publication attempts

The exact command was:

```powershell
python scripts/quality/run_frozen_reliability_cohort.py `
  --sources-manifest tmp/frozen20-next5-batch3-summary-scope-fix-20261001/frozen-reliability-h06gdcnr/frozen_cohort.json `
  --runs-root tmp/frozen20-next5-systematic-repair-final-20261001 `
  --max-duration 7200
```

[`cohort_result.json`](cohort_result.json) is the unchanged runner result.
[`measurement_summary.json`](measurement_summary.json) and
[`final_package_lineage.json`](final_package_lineage.json) contain no generated
report text; their package, artifact, evidence, configuration, policy,
validator, and claim-identity digests bind the retained measurement to this
run.
