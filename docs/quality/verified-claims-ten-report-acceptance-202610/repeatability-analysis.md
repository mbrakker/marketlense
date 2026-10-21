# Step 1 repeatability analysis

PARTIAL: the first isolated run is complete, but two clean independent Step1 evaluations per eligible report were not obtained. No deterministic selector defect was reproduced from the available comparable artifacts; remaining variance is confounded by model/workflow failure and candidate-generation drift.

## Runs

- First isolated run: 10 reports and 59 retained candidates; source `tmp/ten-full/frozen-reliability-9kx4zae9/frozen...`.
- Shared-batch repetition: available=True; artifact-bearing reports=0. It is invalid as a clean independent repetition because all ten terminal records failed and the run directory was reused.
- Supplemental isolated repetition: available=True; artifact-bearing reports=5 for Algolia, Criteo, Deloitte, KPMG, Reuters Institute.

## Identity comparison

| Report | Status | Jaccard / note |
|---|---|---|
| Adjust | not_comparable | not comparable |
| Algolia | comparable | 0.0 |
| Bain & Company | not_comparable | not comparable |
| Criteo | comparable | 0.1111 |
| Deloitte | comparable | 0.0 |
| DoubleVerify | not_comparable | not comparable |
| Emplifi | not_comparable | not comparable |
| KPMG | comparable | 0.0 |
| Reuters Institute | comparable | 0.0 |
| StackAdapt Inc | not_comparable | not comparable |

The selection ledger preserves the actual first-run pools, selected IDs, final wording, evidence spans and metrics. The selector already had regression coverage for stable IDs, semantic deduplication, provenance conflicts, fallback theme coverage and cache invalidation. The current ten-report replay did not reproduce a deterministic selector defect. A Criteo candidate-generation qualifier/timeframe drift was observed and then correctly rejected by downstream public grounding; this is evidence about upstream candidate construction, not a justified selector change. Reuters failed a downstream metric-label relationship validation. These observations remain open quality limitations.
