# Step 1 repeatability analysis

PARTIAL: the first isolated run is complete, but two clean independent Step1 evaluations per eligible report were not obtained. No deterministic selector defect was reproduced from the available comparable artifacts; remaining variance is confounded by model/workflow failure and candidate-generation drift.

## Runs

- First isolated run: 10 reports and 59 retained candidates; source `tmp/ten-full/frozen-reliability-9kx4zae9/frozen...`.
- Shared-batch repetition: available=True; artifact-bearing reports=0. It is invalid as a clean independent repetition because all ten terminal records failed and the run directory was reused.
- Supplemental isolated repetition: available=True; artifact-bearing reports=5 for Algolia, Criteo, Deloitte, KPMG, Reuters Institute.
- Remaining-five isolated repetition at `6f09874c`: available=True; all five reports reached typed terminal outcomes. Bain, Emplifi and StackAdapt passed validation/readiness; DoubleVerify failed validation on a confirmed noisy-chart relationship false positive; Adjust passed validation but failed the public identifier gate.
- Corrected follow-up at `08be09bf`: DoubleVerify passed validation/readiness after the relationship-boundary fix; Adjust failed closed on a separate unsupported timeframe/incomplete-numeric validation outcome after three bounded repairs. A provider-free re-render at `9e32ac36` removed the composite quote identifier from the retained Adjust public projection.

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

The selection ledger preserves the actual first-run pools, selected IDs, final wording, evidence spans and metrics. The selector already had regression coverage for stable IDs, semantic deduplication, provenance conflicts, fallback theme coverage and cache invalidation. The remaining-five live repeat changed the selected evidence roster materially: exact evidence-ID overlap with the baseline was DoubleVerify 1/5, Adjust 0/6, Bain 3/5, Emplifi 0/5 and StackAdapt 0/5. This is a live repeatability limitation, not proof that the selector itself caused every difference; candidate-generation/model variation and downstream terminal failures are confounders. A Criteo candidate-generation qualifier/timeframe drift was observed and is now bounded at candidate normalization: the unsupported `2023 plans` timeframe is cleared while the supported value/evidence remain, and prompts preserve scoped qualifiers. These changes do not establish improved live selection quality. The corrected DoubleVerify validator uses a precise `findings_statement` span only for metric-label binding checks, while preserving full evidence for other checks. The renderer now rejects composite internal quote identifiers in public citation labels. Adjust's later unsupported timeframe failure remains fail-closed. These observations remain open quality limitations.

## Remaining-five live selection ledger

The table compares the original ten-report final roster with the first clean remaining-five replay by retained evidence identity. It is a semantic stability signal, not a claim that different IDs are factual errors; the live rerun produced different candidate/final identities and was not accepted as a selector-quality improvement.

| Report | Baseline final | Repeat final | Shared evidence IDs | Terminal result at `6f09874c` |
|---|---:|---:|---:|---|
| DoubleVerify | 5 | 5 | 1 | validation failed; corrected follow-up passed |
| Adjust | 7 | 6 | 0 | readiness failed; corrected follow-up failed closed on timeframe validation |
| Bain & Company | 5 | 5 | 3 | validation/readiness pass |
| Emplifi | 5 | 5 | 0 | validation/readiness pass |
| StackAdapt Inc | 7 | 5 | 0 | validation/readiness pass |

The baseline-to-repeat roster differences are therefore retained as evidence of model/candidate-generation variance. No keyword relevance score, arbitrary minimum-count increase, ranking framework, or source-fidelity relaxation was introduced.
