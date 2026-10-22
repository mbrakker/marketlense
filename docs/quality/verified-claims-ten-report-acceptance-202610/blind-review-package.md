# P6 blind-review package (prepared, not acceptance)

This package is a review handoff for an independent P6 reviewer. It contains pointers to the actual retained final editorial output and the hash-matched source evidence; it does not label the existing automated review as human acceptance.

## Review inputs

- Frozen source identity and physical page inventory: [`cohort-manifest.json`](cohort-manifest.json).
- Actual final editorial rows, stable IDs, evidence IDs, spans, protected metrics and source paths: [`step1-selection-ledger.json`](step1-selection-ledger.json) and the `artifacts.json` paths recorded in its `artifact.resolved_path` fields.
- Claim correction and verification attempts: [`step2-verification-ledger.json`](step2-verification-ledger.json).
- Independent page-by-page engineering audit: [`source-grounded-editorial-audit.md`](source-grounded-editorial-audit.md).
- Six strict source-recall checks: [`source-recall-reference-set.json`](source-recall-reference-set.json).

The reviewer should use the original PDFs from the manifest, verify the recorded SHA-256 before reading a claim, and inspect the full physical page(s) and bounded evidence spans. The package is read-only and contains no publication or canonical-promotion operation.

## Blind-review procedure

1. Read each final claim without using the report name, selected-theme rationale, or automated score as a quality signal.
2. Re-open the cited physical page(s), then judge the claim and its protected metric binding against the source wording and population.
3. Record one mutually exclusive result per claim: `accept`, `minor_revision`, `reject_factual`, `reject_unsupported`, or `unresolved_source`.
4. Record whether the claim is commercially important, analytically useful, specific, and non-redundant. Treat an omitted source finding as a selection-quality issue unless it makes a retained claim false.

## Acceptance criteria

| Dimension | Accept when |
|---|---|
| Factual fidelity | Value, unit, direction, population, denominator, geography, timeframe and observed/forecast/estimate status match the cited source, or the claim is an explicitly defensible interpretation of it. |
| Grounding and provenance | The cited PDF hash, physical page, evidence ID and span identify the source passage that supports the claim; headings and nearby context alone do not count. |
| Analytical value | The claim explains a meaningful implication or decision relevance, not only a generic restatement. Reasonable editorial interpretation is allowed when it is clearly bounded by the source. |
| Commercial relevance | The finding matters to digital commerce, marketing, customer experience, media, discovery, or an adjacent decision in the report's scope. |
| Specificity | The wording preserves material qualifiers such as cohort, geography, period, forecast status and scoped terms such as “some” or “after.” |
| Distinctiveness | The claim adds a distinct proposition or metric and is not a paraphrase of another retained claim. |
| Editorial quality | The wording is concise, natural, and useful without adding unsupported certainty, causality, or recommendations. |

This handoff remains **not assessed** until an independent reviewer records the per-claim decisions. The existing GPT-based scorecard is evidence about automated editorial review only, not P6 human acceptance.
