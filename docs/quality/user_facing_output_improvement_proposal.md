# User-Facing Output Improvement Proposal

This review covers the report analysis prompt namespace under `src/prompts/report_vs/` and the public JSON schemas under `src/schemas/`. It proposes 20 high-impact improvements to make generated outputs more complete, grounded, data-driven, strategic, and consultancy-grade while preserving the existing architecture.

## Success criteria

- Improve executive usefulness without adding unsupported facts.
- Increase coverage across scope, methods, metrics, findings, risks, limitations, contradictions, recommendations, quotes, summaries, insights, expert comments, LinkedIn posts, taxonomy, categories, and cover semantics.
- Strengthen evidence traceability from final editorial claims back to evidence identifiers, pages, and source packs.
- Raise editorial quality toward senior consultancy standards: sharper implications, quantified support, clearer decision relevance, and explicit caveats.

## Design principles for coexistence

- Treat the current prompt and schema surface as the stable base; add optional, versioned fields before changing required fields.
- Keep evidence-pack extraction separate from final artifact generation; improvements should reuse existing packs before introducing new extraction work.
- Prefer prompt-only tightening first, then schema-backed additions, then validation gates.
- Preserve existing artifacts such as summary, insights, quotes, expert comment, and LinkedIn post while adding richer structures beside them.
- Make every new editorial claim traceable to an existing evidence ID, page, source pack, or evidence span.

## 20 high-impact improvements

### 1. Introduce an executive decision brief artifact

**What to change:** Add a user-facing `decision_brief` artifact with `strategic_context`, `decision_implications`, `priority_moves`, `watchouts`, `evidence_links`, and `confidence_note`.

**Why to do it:** The current artifact layer includes summary, insights, quotes, expert comment, and LinkedIn post, but it does not explicitly answer the executive question: “What decisions should this report influence?”

**Impact:** Turns the output from informative analysis into a practical leadership brief suitable for board, strategy, and operating reviews.

**How it improves the project:** It creates a premium, differentiated output format that connects source evidence to strategic action without forcing users to infer implications from prose.

**Pros:** High perceived value, clearer executive utility, strong fit for consultancy-style reporting, reusable across categories.

**Cons:** Requires careful grounding because action-oriented language can drift into unsupported recommendation if evidence is weak.

**Risks:** May duplicate recommendations unless the brief clearly distinguishes implications from explicit report recommendations.

**Coexistence with current features:** Keep existing summary and expert comment unchanged initially. Generate the decision brief as an additional artifact using summary, final insights, recommendations, risks, limitations, and evidence spans.

### 2. Make recommendations first-class in final artifacts

**What to change:** Promote extracted recommendations into final artifacts with fields for `recommendation`, `rationale`, `evidence_id`, `intended_actor`, `priority`, `implementation_horizon`, and `expected_business_effect`.

**Why to do it:** Recommendations are extracted as an evidence pack, but the user-facing artifact schema does not surface them as a dedicated final output.

**Impact:** Users see practical next steps instead of only a descriptive summary of the report.

**How it improves the project:** It closes the gap between evidence extraction and decision usefulness, making MarketLense outputs more actionable.

**Pros:** Better strategic value, easier downstream UI presentation, stronger consulting feel, improved differentiation from generic summarizers.

**Cons:** Some reports may not contain explicit recommendations; generated recommendations must not be invented.

**Risks:** If the system converts weak hints into recommendations, it may overstate the source material.

**Coexistence with current features:** Use the existing recommendations pack as the only source. If the pack is empty, expose a transparent `recommendations_not_found` status rather than synthesizing unsupported advice.

### 3. Surface risk register content in the final report

**What to change:** Add a `strategic_risks` artifact that presents risk, impact, likelihood, mitigation, evidence ID, and optional affected stakeholder or business area.

**Why to do it:** Risk extraction exists, but final user-facing outputs do not consistently expose downside scenarios or management mitigations.

**Impact:** Improves report completeness and helps leaders understand what could go wrong, not only what is changing.

**How it improves the project:** It makes outputs more balanced, advisory, and decision-ready.

**Pros:** Strong value for executives, supports strategic planning, highlights uncertainty and operational exposure.

**Cons:** Risk sections can feel repetitive if the source report is not risk-oriented.

**Risks:** Likelihood and impact fields may be sparse or qualitative, requiring clear confidence handling.

**Coexistence with current features:** Reuse the current risk register pack. Display it only when supported, and include `risk_register_not_found` in coverage diagnostics when absent.

### 4. Add limitations and methodology disclosure to outputs

**What to change:** Add a short `methodology_and_limitations` section with `method_summary`, `known_limitations`, `confidence_level`, and `interpretation_cautions`.

**Why to do it:** The system extracts methods and limitations, but final summary and editorial prompts do not require visible confidence or caveat disclosure.

**Impact:** Builds trust by showing users how much weight to place on the report.

**How it improves the project:** Consultancy-grade outputs are not just persuasive; they make evidence quality and caveats explicit.

**Pros:** Higher credibility, better grounding, fewer overconfident outputs, stronger fit for regulated or senior audiences.

**Cons:** Adds length and may reduce marketing-style polish if overdone.

**Risks:** Poorly worded caveats could make high-quality reports seem weak.

**Coexistence with current features:** Keep caveats concise and separate from the executive summary. Use existing methods and limitations packs without changing extraction behavior.

### 5. Create a metric spine across all editorial artifacts

**What to change:** Identify the strongest 3-6 metrics and propagate them through summary, insights, expert comment, LinkedIn post, and decision brief.

**Why to do it:** Insights candidates already capture metric components, but later editorial artifacts can still become generic if they do not reuse quantified evidence.

**Impact:** Produces more data-driven output with concrete values, timeframes, segments, and confidence indicators.

**How it improves the project:** It raises the perceived expertise of every user-facing artifact and reduces vague strategic language.

**Pros:** Better factual density, clearer proof points, stronger executive trust, easier validation.

**Cons:** Metric-heavy outputs can become mechanical if not synthesized well.

**Risks:** Incorrect metric propagation could spread one extraction error across many artifacts.

**Coexistence with current features:** Treat the metric spine as a derived artifact from key metrics and final insights. Existing text outputs can consume it without changing their public shape at first.

### 6. Enforce claim-level evidence spans in final editorial outputs

**What to change:** Require claim-level evidence spans where available, including evidence ID, source pack, section ID, page, offsets, and text excerpt.

**Why to do it:** The schema already allows evidence spans in several artifact objects, but prompts commonly ask only for a single evidence ID.

**Impact:** Makes claims auditable and supports future UI features such as “show source” or inline citations.

**How it improves the project:** It directly improves grounding quality and reduces hallucination risk.

**Pros:** Strong traceability, better validation, improved user trust, easier debugging.

**Cons:** More verbose payloads and more complexity in validation and display.

**Risks:** Missing spans could cause otherwise valid outputs to fail if rolled out too aggressively.

**Coexistence with current features:** Add spans as optional fields first. Keep `evidence_id` as the compatibility path until generators and UI are fully migrated.

### 7. Add insight scoring dimensions beyond a single usefulness score

**What to change:** Replace or supplement a single candidate score with `novelty`, `strategic_importance`, `evidence_strength`, `quantification_quality`, `actionability`, and `coverage_role`.

**Why to do it:** A single usefulness score does not explain why an insight is selected or help balance strategic value against evidence strength.

**Impact:** Improves final insight selection and makes it easier to avoid generic or overlapping insights.

**How it improves the project:** It gives the selection process a transparent consultancy-style rubric.

**Pros:** Better insight quality, easier validation, clearer selection logic, stronger editorial consistency.

**Cons:** More fields to generate and validate.

**Risks:** Scores can become pseudo-precision if not calibrated or explained.

**Coexistence with current features:** Keep the existing `score` field for backward compatibility and add the scoring dimensions as optional metadata before making them required.

### 8. Require non-overlap coverage categories for final insights

**What to change:** Tag each final insight with a coverage category such as market shift, customer behavior, operational implication, commercial signal, technology/channel signal, risk, recommendation, or methodology caveat.

**Why to do it:** The prompt asks for five non-overlapping insights but does not define what a balanced set should cover.

**Impact:** Reduces repeated insights and broadens the report’s strategic coverage.

**How it improves the project:** It makes the final five insights feel curated by an expert rather than selected by similarity or salience alone.

**Pros:** Better diversity, better report coverage, easier UI grouping, stronger editorial control.

**Cons:** Some narrow reports may not support all categories.

**Risks:** The model may force-fit categories unless instructed to use only supported coverage roles.

**Coexistence with current features:** Add a coverage role per insight while keeping exactly five final insights. Allow repeated roles when the source report is narrow, but require a reason.

### 9. Separate observations, implications, and recommended actions

**What to change:** Structure key editorial outputs into `observation`, `so_what`, and `now_what` components.

**Why to do it:** Current editorial prompts request synthesis, but a single text block can blur the line between what the report says, what it means, and what leaders should do.

**Impact:** Makes outputs clearer, more strategic, and easier to scan.

**How it improves the project:** It aligns the output with top-tier consulting communication norms.

**Pros:** Higher clarity, stronger actionability, easier validation of unsupported implications.

**Cons:** Can feel formulaic if every artifact uses the same structure.

**Risks:** The `now_what` component may drift into unsupported advice if not tied to recommendations or evidence.

**Coexistence with current features:** Use the structure inside new or optional artifacts first. Keep existing prose outputs for current consumers until the UI supports structured display.

### 10. Add contradiction-aware synthesis

**What to change:** Require summary, expert comment, and decision brief generation to check contradictions and explicitly identify unresolved tensions where evidence supports them.

**Why to do it:** A contradictions evidence pack exists, but downstream editorials do not consistently use it.

**Impact:** Prevents overconfident summaries when the underlying report contains conflicting claims or mixed signals.

**How it improves the project:** It makes analysis more expert and trustworthy, especially for complex market reports.

**Pros:** More nuanced output, better risk management, stronger professional credibility.

**Cons:** Can add complexity and reduce punchiness in simple outputs.

**Risks:** Overemphasizing minor contradictions may confuse users.

**Coexistence with current features:** Include contradiction handling only when the contradictions pack is generated and non-empty. Otherwise omit the section or mark it as not found in diagnostics.

### 11. Improve quote usefulness with quote roles

**What to change:** Add required or strongly encouraged quote roles such as proof point, executive voice, customer voice, methodology caveat, strategic tension, or market signal.

**Why to do it:** Quotes are currently selected verbatim with citation and evidence ID, but the output does not explain why each quote matters.

**Impact:** Makes quotes more purposeful and easier to place in editorial layouts.

**How it improves the project:** It turns quotes from decorative excerpts into evidence-backed narrative assets.

**Pros:** Better editorial flow, stronger source relevance, improved content design.

**Cons:** Requires another classification step or prompt instruction.

**Risks:** Quote roles may be wrong if the quote lacks context.

**Coexistence with current features:** Use existing optional schema fields such as label, style, mode, or add a backward-compatible `role` field. Preserve verbatim quote text unchanged.

### 12. Add audience segmentation to editorials

**What to change:** Add optional audience variants for CEO/board, CMO/growth, ecommerce/digital, product/technology, investor/strategy, and operations leaders.

**Why to do it:** Current editorials assume senior ecommerce, digital, or strategy leaders, which may not match every report or user need.

**Impact:** Increases relevance and perceived expertise for different users.

**How it improves the project:** It enables the same evidence base to produce sharper, role-specific outputs without changing extraction.

**Pros:** Higher personalization, better engagement, stronger commercial value.

**Cons:** More generated artifacts increase cost and validation needs.

**Risks:** Audience-specific framing can introduce unsupported assumptions if not grounded.

**Coexistence with current features:** Keep the current general expert comment as default. Generate audience variants only when requested or when a UI setting selects an audience.

### 13. Strengthen category and taxonomy output with business relevance

**What to change:** Add a user-facing `category_relevance` explanation that says why the report matters for each selected category and what evidence supports that classification.

**Why to do it:** Taxonomy and category fit currently support organization and discovery, but users benefit from seeing the strategic relevance behind the classification.

**Impact:** Improves discoverability, trust in categorization, and report browsing quality.

**How it improves the project:** It turns internal classification into a user-facing value signal.

**Pros:** Better portal UX, clearer category fit, more explainable recommendations.

**Cons:** Adds extra text that may be unnecessary in compact cards.

**Risks:** Category explanations may become generic unless tied to report evidence and category profiles.

**Coexistence with current features:** Add explanations beside existing selected category IDs and category fits. Keep category IDs unchanged for routing and filtering.

### 14. Convert the executive summary from narrative-only to pyramid principle

**What to change:** Require the executive summary to follow: top-line answer, supporting evidence, strategic implication, caveat, and recommended reading path.

**Why to do it:** A 5-7 sentence summary can be accurate but still feel flat if it lacks hierarchy.

**Impact:** Makes the summary faster to understand and more executive-ready.

**How it improves the project:** It improves clarity without requiring new data extraction.

**Pros:** High impact with prompt-only change, better readability, stronger consultancy tone.

**Cons:** The pattern can become rigid across many reports.

**Risks:** If the source evidence is weak, the top-line answer may become overconfident.

**Coexistence with current features:** Keep the same summary fields initially. Change only the prompt rubric, then consider adding structured subfields after validation proves stable.

### 15. Add report coverage diagnostics

**What to change:** Add `coverage_diagnostics` showing whether scope, methods, metrics, findings, quotes, limitations, risks, recommendations, and contradictions are present, weak, or absent.

**Why to do it:** The system already tracks family status and not-found reasons, but users do not see a consolidated coverage picture.

**Impact:** Increases transparency and helps users understand output quality and source gaps.

**How it improves the project:** It prevents absent evidence from looking like an editorial omission or model failure.

**Pros:** Better trust, easier QA, useful for internal monitoring and user-facing confidence.

**Cons:** Adds a technical-feeling section that must be designed carefully.

**Risks:** Too much diagnostic detail can distract from the main insights.

**Coexistence with current features:** Use diagnostics as metadata for UI badges or expandable sections. Do not force it into every prose artifact.

### 16. Require quantified comparisons where evidence supports them

**What to change:** Add fields for comparator, baseline, delta, base period, target period, geography, segment, and sample size where evidence provides them.

**Why to do it:** Metrics are more valuable when users understand compared to what, where, and for whom.

**Impact:** Produces more precise, decision-relevant insights.

**How it improves the project:** It improves analytical quality by moving beyond isolated numbers.

**Pros:** Stronger data storytelling, better executive interpretation, easier validation.

**Cons:** Not all reports provide comparable metrics.

**Risks:** The model may infer comparisons that are not explicit.

**Coexistence with current features:** Add comparison fields as optional metric metadata. Require empty values when not supported rather than inferred comparisons.

### 17. Introduce strategic narrative archetypes

**What to change:** Classify the report’s dominant narrative as acceleration, inflection, fragmentation, consolidation, resilience, trade-off, substitution, maturity, uncertainty, or system change.

**Why to do it:** Expert outputs need a coherent strategic storyline, not just a list of findings.

**Impact:** Makes summaries, expert comments, covers, and LinkedIn posts more distinctive and memorable.

**How it improves the project:** It gives editorial generation a grounded narrative frame that can improve consistency and quality.

**Pros:** Stronger story, better packaging, reusable across cover semantics and editorials.

**Cons:** Requires careful definition to avoid vague or subjective labels.

**Risks:** The archetype can oversimplify complex reports.

**Coexistence with current features:** Add as optional metadata derived from existing evidence shape, direction, insights, and contradictions. Do not replace cover semantics.

### 18. Add editorial quality gates before publishing

**What to change:** Extend validation with rule IDs for generic phrasing, unsupported implications, missing metric support, duplicated insights, missing caveats, weak actionability, forbidden internal references, and tone defects.

**Why to do it:** Current validation can flag schema and grounding issues, but top consultancy quality also requires editorial standards.

**Impact:** Raises output consistency and prevents low-quality prose from reaching users.

**How it improves the project:** It creates enforceable quality control for strategic writing, not only JSON validity.

**Pros:** Better polish, fewer generic outputs, stronger brand trust, measurable quality improvements.

**Cons:** More validation can increase regeneration cost and latency.

**Risks:** Overly strict rules may reject acceptable outputs or create repetitive writing.

**Coexistence with current features:** Add warnings first, then promote stable rules to errors. Use existing regeneration prompts to repair only the affected section.

### 19. Fix prompt copy defects that undermine professional quality

**What to change:** Correct visible prompt typos and wording issues, including “threeshort,” “peges,” and “evedence,” and tighten ambiguous editorial instructions.

**Why to do it:** Prompt quality affects model behavior and signals engineering discipline.

**Impact:** Reduces the chance of malformed, unprofessional, or confusing output.

**How it improves the project:** It is a low-risk quality lift that improves consistency across generated editorials.

**Pros:** Fast, low cost, easy to review, no schema impact.

**Cons:** Limited strategic improvement by itself.

**Risks:** Small wording changes can slightly alter generated outputs, so regression fixtures should be checked.

**Coexistence with current features:** This is fully compatible with current schemas and generators. It should be the first implementation step.

### 20. Version the user-facing editorial contract

**What to change:** Introduce an explicit editorial artifact contract version for any new final-output fields, especially decision brief, recommendations, risks, limitations, coverage diagnostics, and evidence spans.

**Why to do it:** The schemas include version fields in several places, but broad final-output evolution should be explicitly versioned to avoid silent breaking changes.

**Impact:** Enables safer rollout, backward compatibility, and reliable downstream rendering.

**How it improves the project:** It protects consumers of the artifacts schema as the output becomes richer.

**Pros:** Safer migrations, cleaner adapters, better testability, clearer release notes.

**Cons:** Requires migration discipline and more documentation.

**Risks:** Version fragmentation can occur if too many variants are supported indefinitely.

**Coexistence with current features:** Keep current artifact fields stable under the existing contract. Add a new version only when introducing schema-backed fields that downstream consumers must understand.

## Recommended implementation sequence

1. **Prompt-only quality pass:** fix prompt typos, add pyramid-principle summary requirements, tighten expert and LinkedIn structures, and add contradiction checks where relevant.
2. **Schema-backed coverage upgrade:** add optional user-facing recommendations, strategic risks, limitations, methodology confidence, coverage diagnostics, and category relevance fields.
3. **Evidence-traceability upgrade:** require evidence spans and metric spine propagation through summary, insights, expert comment, LinkedIn post, and decision brief.
4. **Validation upgrade:** add editorial quality and coverage validation rule IDs, initially as warnings, then promote stable rules to hard failures.
5. **Experience upgrade:** add executive decision brief and audience-specific editorial variants after the core evidence and schema contracts are stable.

## Expected impact

- Higher trust through visible evidence linkage, caveats, methodology context, and coverage diagnostics.
- Better executive usefulness through explicit implications, risks, recommendations, and decision briefs.
- Better report coverage through surfaced methods, limitations, contradictions, recommendations, and risk registers.
- More strategic editorial quality through pyramid-principle structure, metric spine propagation, contradiction handling, narrative archetypes, and audience-specific framing.
- Safer evolution through optional-first schema additions, validation warnings before hard failures, and explicit editorial contract versioning.
