# Report editorial quality loss fixes

## Goal

Recover report quality losses seen in the frozen comparison while reusing retained evidence and preserving factual, quote, and source-provenance safeguards. The sampled reports show that taxonomy and the Source section are present; the concrete gaps are weak/over-pruned editorial copy, generic Signals cards, empty final quotes despite retained candidates, and hidden taxonomy tags.

## Evidence and observable outcomes

- Existing `insights_final` already carries `so_what` and `now_what`, but several values are generic and can be over-validated as source facts. Editorial interpretation/advice should survive when clearly authored as analysis, non-contradictory, and free of unsupported factual premises.
- Summary normalization can replace valid descriptive DocMap-backed claims with a small direct-evidence fallback. Keep descriptive claims tied to DocMap spans while numeric, superlative, causal, and other strong claims still require direct findings/quote evidence.
- Signals cards are currently built from DocMap section briefs rather than selected insights. Project existing retained findings and their implications/actions into these cards, with the prior topic-brief path only as a fallback.
- The quote-candidate pack contains attributed, page-linked source text, but the final selector abstains. Make candidate ID reuse explicit and deterministically retain a small set of validated verbatim candidates if selection still returns empty.
- Taxonomy and source-link/preview data are present in the samples. Surface the existing tags by default and make the existing cover preview open the already-verified public source URL. Do not expose local/acquisition PDF paths or add retrieval for these UI improvements.
- Prompt requirements should preserve explicit inclusive page ranges and ensure broad reports retain their distinct central facets.

## Scope

Update the relevant artifact normalization, grounding policy, render projection/template, and report prompts. Add focused regression coverage for summary filtering, quote fallback and abstention, editorial implication validation, signal-card rendering, and taxonomy/source presentation. Do not change publication flow, add a dependency, or create an additional File Search step.

## Implementation steps

1. Add failing tests for retained DocMap descriptive claims and excluded strong claims in summary fallback.
2. Implement a narrow summary predicate: retain DocMap-backed descriptive claims, but do not treat DocMap as direct support for numeric/strong claims; keep the existing post-generation claim-validation path.
3. Add failing tests for empty quote selection with populated quote candidates and for unsafe/empty candidates.
4. Update quote-selection instructions to copy candidate IDs, text, speaker/source, and page. Add a deterministic fallback from the already fidelity-filtered candidate pack; bind quote-candidate evidence spans and leave empty only when candidates are absent or invalid.
5. Add failing tests for `so_what`/`now_what` classification and non-contradictory editorial copy. Treat those fields as analyst interpretation/recommendation; keep contradictions, unsupported factual premises, numeric drift, false source attribution, certainty, and claimed outcomes as validation failures.
6. Update insight and Expert View prompts to prefer report-specific implications and conditional MarketLense-authored actions, without requiring the source itself to state every recommendation.
7. Add failing tests for Signals projection, then build cards from retained insights and their implications/actions. Preserve the topic-brief fallback when no final insight is available.
8. Add failing render assertions for visible taxonomy tags and a clickable source preview; update the template to show existing tags and link the existing preview only to the verified public source URL.
9. Tighten DocMap and taxonomy prompts to preserve explicit multi-page ranges and central facets across broad reports; do not infer page ranges or tags from missing evidence.
10. Run focused tests, prompt checks, editorial-output evaluation, inspect the final diff and secrets, then run the same two frozen reports through the isolated production workflow if the runner can be used with an isolated clean checkout and bounded spend.

## Risks and safeguards

- DocMap is a structured source synopsis, so it may support descriptive claims but must not authorize numeric claims or source-wide importance. Grounding validation remains active after normalization.
- Quote fallback must use exact retained candidate text only, preserve the candidate ID/page, and never parse unsupported speaker attribution. No DocMap-only passage becomes a quotation.
- Editorial implication fields can express advice, but must not turn into facts, unsupported numerical claims, certainty, causal outcomes, financial/operational benefits, or attributed source directives.
- Source preview images remain report-local approved preview assets; only the verified publisher URL is used as a link. Internal acquisition and archive paths stay private.
- Existing untracked benchmark JSON is user-owned and must remain untouched.

## Completion criteria

- Focused tests demonstrate preserved descriptive summaries, useful insight-based signal cards, quote recovery from retained candidates, and non-blocking non-contradictory editorial copy while contradiction/factual guard tests remain strict.
- Generated HTML exposes the taxonomy tags, existing source preview, and verified public source link.
- Final diff is limited to the above request; report executed checks and any live-run limitation accurately.

## Execution result (2026-10-04)

- Both rendered sample reports passed public editorial quality with zero issues; each exposes five Signals cards with `so_what`/`now_what`, three retained quotes, visible tags, and a source preview linked to its verified publisher URL.
- The two-report replay and final Capgemini recheck reused retained evidence and made zero File Search calls. No full five-report File Search cohort rerun was performed after these quality changes.
- Focused artifact, grounding, render, prompt, taxonomy, and evidence-pack suites passed (229 tests); the public report quality check passed. The prompt fixture gate passes with the user-approved, time-bounded 1.5% corpus token allowance; the committed April baseline is unchanged.
