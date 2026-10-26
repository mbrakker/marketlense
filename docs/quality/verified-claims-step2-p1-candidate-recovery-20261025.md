# Verified Claims Step 2 — P1 candidate-generation and recovery evidence

Date: 2026-10-25
Producer commit: `5182502dc3e7efbea4c13cb5e7c4437a6f7f2769`
Scope: one fresh provider-backed Adjust run, shadow-only, no publication writes.

## P0–P2 verification — 2026-10-26

Starting implementation: `a4b417bffbd5552633f0117096ab7580efe39852`.
The retained empty-checkpoint ambiguity described below remains a limitation:
without the discarded raw response, explicit model abstention cannot be
distinguished from a missing root. Later location-only candidate rosters were
nonempty but failed the factual-ID boundary; they are not evidence of empty
model generation. The existing bounded fallback remains necessary.

One eligibility defect was reproduced: a supported hyphenated finding with
an `evidence:findings:` prefix could be dropped because the text-normalized
lookup key changed punctuation while fidelity IDs used literal identity.
The fallback now also compares the exact namespace-stripped ID, preserving
the existing raw-ID comparison (including upstream fidelity's prefixed raw
IDs). Output identities and factual fields are unchanged. Selection cache
version 19 prevents reuse across this eligibility change. Supported and
unsupported cases cover both ID forms and both fidelity representations.
This defect was not the cause of the retained bare-ID Adjust failures.

Missing regression cases now cover unknown primary/secondary/span IDs,
ambiguous quote identities, quarantine, malformed summary repair paths,
duplicate/missing repair identities, and missing/quarantined/wrong-page
secondary verified facts. No new validator, prompt, retry or quota was added.

Seven opt-in provider checks through production `run_grounding_check` used
unchanged retained Adjust canonical facts. Different populations, incompatible
periods, regional-as-global claims and installs/sessions conflation were
`contradicted`; irrelevant secondary evidence and false causality were
`not_established`; the compatible global finance/e-commerce comparison passed.
Inspection of the returned reasons confirms the relevant metric relationships,
not merely a generic failure. This is component-level semantic evidence, not
end-to-end acceptance. It used seven calls, 35,765 input / 15,970 output tokens
and estimated `$0.010586`. Retained evidence:
`C:\ml-adjust-acceptance-20261026\tmp\p1-b-multifact-live-20261026a\multifact-live0`.

The fresh Adjust end-to-end outcome and final source review are recorded below
once execution completes; the component checks alone do not close P0.

## Retained failure reconstruction

The older Adjust candidate checkpoint was not an unexplained empty artifact.
At the `654a5cf1` run, the normalized
`report_vs/artifacts/insights_candidates` checkpoint contains
`{"output":[]}`. Its usage-ledger row records a completed, parse-valid primary
call (4,687 input tokens, 704 output tokens, 675 reasoning tokens, `$0.000821`),
with no schema error, provider error, or recovery attempt. The old candidate
contract permitted an empty list as abstention, and the normalizer therefore
accepted it before the findings fallback ran. The raw provider response was
not retained by policy, so the retained evidence cannot distinguish an explicit
provider `[]` from a missing root normalized to the same checkpoint. It does
establish the responsible boundary: accepted empty primary output followed by
unconditional findings fallback.

The subsequent `83870a1c` run was different: seven model candidates plus 17
fallback candidates were selected, all 24 visual candidates were admitted, and
the final grounding gate rejected a qualitative rewrite that broadened
supported finance-app installs into “acquisition”. This was an interpretation
quarantine problem, not a failed factual binding.

## Minimal corrections

- Candidate selection now treats an empty or missing candidate root as
  recoverable when the existing fidelity-approved findings contain enough
  eligible evidence for the existing minimum. It uses the existing bounded
  primary/model-repair/regeneration path; exhausted recovery still falls back
  fail-closed to the existing evidence-backed findings selector.
- Findings fallback is conditional: a primary roster meeting the existing
  minimum and editorial-plan theme coverage does not get expanded merely to
  fill capacity. Fallback remains available when coverage or eligibility is
  insufficient.
- Interpretation-only grounding failures in `so_what`/`now_what` no longer
  quarantine the canonical fact. The existing targeted wording-repair/removal
  path can use the authoritative evidence; metric/factual failures retain the
  quarantine behavior.
- Candidate selection cache version advanced from 12 to 13. The new private
  candidate audit records root presence/type, raw and normalized counts,
  recovery disposition, fallback reason, and verified-fact admission without
  retaining prompts or raw provider responses.

## Fresh Adjust run

Frozen cohort member: `cohort-b638414df0b1fccea1cd`
Source PDF SHA-256: `ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`
Run root: `C:\ml-step1-adjust-p1-live\tmp\verified-claims-p1-recovery-20261025\frozen-reliability-9jjh7yog`
Terminal state: `awaiting_review`; validation: `pass`; publication readiness:
`pass`; WordPress writes: none.

| Measure | Failed `83870a1c` run | Fresh corrected run | Change |
| --- | ---: | ---: | ---: |
| Provider calls | 84 | 53 | -31 (-36.9%) |
| Input tokens | 983,264 | 566,731 | -416,533 (-42.4%) |
| Output tokens | 134,403 | 118,909 | -15,494 (-11.5%) |
| Estimated cost | `$0.182050` | `$0.135151` | -`$0.046899` (-25.8%) |
| Wall-clock time | 1,098.765 s | 831.0 s | -267.765 s (-24.4%) |
| Automatic repairs | 0 | 0 | unchanged |
| Structured-output recovery calls | 0 | 0 | unchanged |
| Final insights | 5 | 5 | unchanged |
| Grounding / readiness | fail / fail | pass / pass | corrected run passes |

The preceding accepted `654a5cf1` run used 75 calls, 707,174 input tokens,
115,340 output tokens, `$0.147414`, and 1,001.563 seconds. The fresh run is
lower by 22 calls, 140,443 input tokens, `$0.012263` (8.3%), and 170.563
seconds, with 3,569 more output tokens (3.1%). These are provider-backed
run-level differences, not a causal claim about selection quality; the model
returned a different candidate roster.

### Candidate funnel and empty-output result

| Audit field | Fresh value |
| --- | ---: |
| Model output status / count | `accepted_non_empty` / 8 |
| Root present / type | yes / list |
| Raw / normalized candidates | 8 / 8 |
| Eligible supported findings available | yes |
| Recovery attempted / attempts | no / 1 primary attempt |
| Findings fallback invoked / count | no / 0 |
| Fallback reason | `primary_adequate` |
| Selected source / count | `model` / 8 |
| Verified-fact admission | 7 admitted, 1 quarantined |
| Post-admission candidates | 7 |

The fresh run therefore did not silently accept an empty checkpoint: the
provider supplied eight model candidates, existing evidence admission retained
seven, and one conflicting cross-platform fact was quarantined. The final
selector chose five from the seven admitted facts. Gaming candidates remained
in the admitted alternative roster even though the stochastic final five
favoured other report themes. No fallback was needed.

## Final five independent PDF review

All five final insights had one `verified-fact:` evidence ID, a direct evidence
span, and the physical page shown below. The source identity and PDF hash above
were preserved.

| Stable ID | Page | Factual/editorial review |
| --- | ---: | --- |
| `insight-ecommerce-install-session-divergence` | 27 | -10% installs and +5% sessions in 2025; the interpretation keeps acquisition and sessions distinct. |
| `insight-ecommerce-retention-by-day` | 29 | Day-1 retention 13.2% to 12.6%; wording does not claim a cause and separates early from later intervals. |
| `insight-finance-install-session-divergence` | 34 | -4% installs and +21% sessions; no broader acquisition claim is made. |
| `insight-genai-maturity-efficiency` | 9 | “Over 20%” remains scoped to a small advanced-deployment group and is marked reported, not a general benchmark. |
| `insight-ecommerce-cpi-subvertical-divergence` | 29 | Deal-discovery CPI $1.44 to $2.26; the wording does not generalize the subvertical result to all e-commerce. |

Independent review found no material factual or numeric error, unsupported
causal interpretation, source-page mismatch, or evidence-ID mismatch in these
five. Public editorial quality, validation, and readiness all passed. The
final roster differs from the earlier accepted run, so this is evidence of a
successful corrected run, not proof of stable live selection effectiveness.

## Verification inventory and limitations

Focused recovery, selection, regeneration, evidence-binding, grounding,
public-quality, schema, architecture, formatting, Ruff, and changed-scope
mypy checks passed. The full default suite passed 8,141 tests with 2 skips,
32 deselections, and 24 subtests; one CPython-3.14 native-wheelhouse test
failed locally and passed when rerun under the repository's CPython 3.12
interpreter. PDF candidate benchmark passed all four rows with matching hashes
and signatures. No provider or publication call was made by the deterministic
tests.

The run had no recovery event, so live recovery effectiveness remains
unmeasured. The old raw empty provider response and the historical 838 repair
diagnostic were not retained. The live run demonstrates that the normal
non-empty path now preserves coverage and removes the previously observed
grounding failure; it does not establish repeated-run stability across the
full frozen cohort.

**Verdict:** PASS for the P1 candidate-generation/recovery correctness slice
and this fresh Adjust report; **PARTIAL/NO-GO** for broader Step 2 live
selection effectiveness. Step 3 remains unstarted/not ready.

## Coverage-aware shortlist follow-up — e0e7cb22 and 8bd2b15f

The follow-up correction separates the existing minimum viable two-insight
check from the default five-insight editorial target. Before visual admission,
the selector now considers a bounded six-to-eight candidate opportunity pool,
uses the existing finding/evidence-fidelity signals, and resolves section-ID
plan references through their original findings. An adequate eight-item model
roster remains on the model path with no fallback call. A short roster is
supplemented only when additional distinct, fidelity-approved opportunities
exist; a report with only two eligible findings remains a valid two-insight
report. The verified final selector now preserves the final model's explicit
selection rather than padding it from the candidate roster.

The same follow-up records planned, supported, lost, and central themes after
visual admission. In the fresh run below, four of five planned themes were
supported, one optional cross-platform theme was lost, no central theme was
lost, and seven admitted alternatives remained available. This is an honest
coverage result, not restoration of the quarantined fact.

The first attempted invocation failed before provider work because the nested
temporary path exceeded the Windows path limit (`analysis_pack_path_too_long`).
It is retained as an environment/preflight limitation and excluded from the
quality denominator. One corrected isolated provider run was then executed
from the short worktree path. It used producer commit
`e0e7cb22c043c794dc6540094e04b65245092e29`; the public-render citation
correction is `8bd2b15f`. The run root was
`C:\ml-step1-adjust-p1-live-coverage\tmp\verified-claims-coverage-20261025\frozen-reliability-wt1szsyw`.

| Funnel measure | Corrected run |
| --- | ---: |
| Model candidates / fallback candidates | 8 / 0 |
| Pre-visual candidates | 8 |
| Evaluated / admitted / quarantined | 8 / 7 / 1 |
| Planned / supported themes | 5 / 4 |
| Lost optional / central themes | 1 / 0 |
| Available final alternatives | 7 |
| Explicit final model selections | 5 |

The admitted stable identities were
`global-ecommerce-installs-sessions-2025`,
`finance-regional-install-session-growth-2024-2025`,
`global-casino-slots-install-session-divergence-2025`,
`genai-maturity-and-reported-efficiency-gains`,
`global-finance-installs-sessions-2025`,
`global-casual-game-growth-2025`, and
`global-gaming-retention-2024-2025`. The quarantined identity was
`cross-platform-data-satisfaction` because its corrected binding conflicted
with the authoritative verified fact. The final five were
`global-finance-installs-sessions-2025` (page 34),
`global-casino-slots-install-session-divergence-2025` (page 19),
`genai-maturity-and-reported-efficiency-gains` (page 9),
`global-ecommerce-installs-sessions-2025` (page 27), and
`global-gaming-retention-2024-2025` (page 21). Direct review of the original
PDF pages found no material factual error, unsupported causality, or binding
mismatch in these five.

| Measure | Accepted `5182502` baseline | Corrected run | Change |
| --- | ---: | ---: | ---: |
| Provider calls | 53 | 56 | +3 (+5.7%) |
| Input tokens | 566,731 | 545,144 | -21,587 (-3.8%) |
| Output tokens | 118,909 | 113,908 | -5,001 (-4.2%) |
| Reasoning tokens | 49,057 | 47,106 | -1,951 (-4.0%) |
| Cached input tokens | 10,830 | 10,830 | 0 |
| Estimated cost | `$0.135151` | `$0.125492` | -`$0.009659` (-7.1%) |
| Wall-clock | 831.0 s | 924.187 s | +93.187 s (+11.2%) |
| Automatic repairs / recovery | 0 / 0 | 0 / 0 | unchanged |
| Validation | pass | pass | unchanged |
| Provider-backed readiness | pass | fail | renderer leak, corrected deterministically |

The provider-backed readiness failure was solely the existing public
identifier-leak rule: the new `verified-fact:<stable-id>` citations were not
covered by the renderer's older `insight-*` suppression. The minimal renderer
correction in `8bd2b15f` suppresses that internal label while preserving the
underlying artifact evidence. A provider-free rerender of the retained output
reported zero internal-ID leaks, zero editorial blockers, five insights, five
metric-spine entries, and complete evidence linkage. The original provider
readiness JSON remains an honest record of the pre-fix run and was not
overwritten; no second provider run was made.

**Follow-up verdict:** PASS for the deterministic coverage, final-selection,
renderer, and regression slices; **PARTIAL/NO-GO** for fresh live selection
effectiveness and broader Step 2 promotion. Step 3 remains unstarted/not
ready. The follow-up does not claim a causal live-quality improvement from one
stochastic run.

## Step 1 coverage correction and fresh Adjust replay — 2026-10-25

Commit `3eb0eadcdddf90b973e955cb41d78b531ec6021b` closes the three targeted
selection defects without adding a provider call. Theme coverage now resolves
against original findings and fidelity-approved evidence IDs; the findings
fallback is no longer used as a membership oracle. Short rosters receive a
bounded six-to-eight opportunity pool, ranked by the existing quality,
fidelity, plan, and deduplication rules. Final selection uses the same shared
validator to retain supported central themes while allowing weaker optional
themes to be omitted. Selection identity advanced to
`evidence_backed_shortlisting:15`.

The required fresh isolated Adjust run used the exact frozen PDF with
SHA-256
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`, commit
`3eb0eadc`, and no publication or canonical-artifact write. The candidate
checkpoint is not an unexplained empty success: the provider produced an
empty candidate roster after three structured-output attempts
(`structured_output_empty`, recovery exhausted). The existing findings
fallback then supplied and retained seven fidelity-approved opportunities;
the audit records model output `0`, fallback `7`, selected `7`, pool bound
`7`, and no unresolved supplementation theme. A separate report-level
structured-output repair call was recorded; automatic repairs were `0`.

| Funnel measure | Latest Step 1 baseline | Fresh corrected run |
| --- | ---: | ---: |
| Provider calls | 56 | 51 |
| Input tokens | 545,144 | 645,698 |
| Output tokens | 113,908 | 103,218 |
| Estimated cost | `$0.125492` | `$0.135208` |
| Wall-clock | 924.187 s | 782.212 s |
| Model / fallback candidates | 8 / 0 | 0 / 7 |
| Evaluated / admitted / quarantined | 8 / 7 / 1 | 7 / 5 / 2 |
| Final insights | 5 | 5 |

Relative to that stochastic baseline, the run used 5 fewer calls (-8.9%),
100,554 more input tokens (+18.4%), 10,690 fewer output tokens (-9.4%),
`$0.009716` more estimated cost (+7.7%), and 141.975 fewer seconds
(-15.4%). A separate current cached-input-token breakout was not retained in
the compact cohort result, so no cached-token improvement is claimed.

The pre-admission plan contained seven themes. Visual admission left two
supported themes and lost five optional themes; no central theme was lost.
The final selection retained both supported central themes and omitted no
central theme. The five final, independently checked claims were:

| Stable ID | PDF page | Source-grounded result |
| --- | ---: | --- |
| `ecommerce-installs` | 27 | Global e-commerce installs fell 10% year over year in 2025. |
| `ecommerce-install-session-growth` | 27 | Global e-commerce sessions increased 5% year over year in 2025. |
| `ai-maturity` | 9 | A small advanced-deployment group reportedly achieved efficiency gains over 20%; the qualifier was preserved. |
| `intro-installs-growth` | 6 | Global app installs grew 10% year over year in 2025 versus 8% in 2024. |
| `gaming-casual-installs` | 19 | Casual-game installs grew 19% and sessions 37% year over year from 2024 to 2025. |

Full-page PDF text and rendered-page review found the quantities, populations,
periods, qualifiers, evidence IDs, and physical pages consistent. Validation
and publication-readiness both passed; no unsupported retained claim or
public-citation identifier leak was observed. The run does demonstrate that
the empty candidate checkpoint is explained and safely recovered, but it does
not demonstrate improved live model shortlisting: the model roster was empty,
five of seven post-admission themes were optional losses, and the comparison
is stochastic.

**Verdict:** PASS for deterministic theme mapping, bounded fallback
accounting, final central-theme protection, and focused regression coverage;
**PARTIAL/NO-GO** for live selection effectiveness and broader Step 2
promotion. Step 3 remains unstarted/not ready.

## Candidate recovery diagnostics and theme-coverage correction — 2026-10-25 (`492b85a9`, finalized test `163ecfe2`)

This is the first replay of the diagnostic and canonical-ID corrections. The
selection identity is now `evidence_backed_shortlisting:17`; the candidate
pool bound applies to both model and fallback paths, and fallback theme
membership is canonicalized once before ranking and audit.

### What produced the empty model checkpoint

The Adjust candidate checkpoint was not a successful explicit empty result and
was not a missing-root result. The bounded parser diagnostics recorded a
present list root on every attempt, but every normalized candidate was a
location-only `source:page:*` reference and therefore failed the existing
candidate evidence contract. The provider response was parse-valid; the
failure was recorded as `structured_output_empty` after normalization.

| Attempt | Mode | Root | Raw / normalized | Location-only | Response chars | Terminal result |
| --- | --- | --- | ---: | ---: | ---: | --- |
| 0 | primary | present list | 11 / 11 | 11 | 15,256 | `structured_output_empty` |
| 1 | model repair | present list | 6 / 6 | 6 | 8,463 | `structured_output_empty` |
| 2 | regeneration | present list | 6 / 6 | 6 | 8,463 | `structured_output_empty` |

The exact provider JSON is intentionally not retained in the checkpoint; only
bounded structural diagnostics are recorded. Accordingly, the evidence
supports the root type, counts, response size and normalization disposition,
but not a claim about wording inside the discarded response. No new retry,
budget or reasoning setting was introduced. Since the IDs were not safe
evidence bindings, promoting them would have weakened provenance. The existing
fidelity-approved findings fallback was therefore the correct fail-closed
recovery path. An explicit `insights_candidates: []` remains distinguishable
from this failure, and a missing required root now raises a structural error.

### Fallback coverage correction

The prior fallback replay exposed an ID-form mismatch: fidelity IDs used the
`evidence:findings:` prefix while editorial-plan eligibility used the same
finding identity in another canonical form. The old intersection therefore
disabled theme-priority matching and allowed one topic to consume the bounded
roster. Canonicalizing the eligible set once fixes the membership decision
without fuzzy matching or quota padding.

| Planned theme from the prior replay | Earlier disposition | Corrected disposition | Evidence-based reason |
| --- | --- | --- | --- |
| Gaming retention | Eligible finding, omitted before visual evaluation | `gaming-overall-retention` is retained as a ranked alternative | Existing fidelity-approved finding was hidden by ID-form mismatch |
| E-commerce retention | Eligible finding, omitted before visual evaluation | `ecommerce-retention` is retained as a ranked alternative | Existing fidelity-approved finding was hidden by ID-form mismatch |
| Finance session performance | Eligible finding(s), omitted before visual evaluation | `finance-sessions` is retained as a ranked alternative | Existing fidelity-approved finding was hidden by ID-form mismatch |
| Platform satisfaction | Reached the prior fallback/selection path but was quarantined during admission | `platform-satisfaction` is available to the corrected path | The corrected mapping preserves the eligible binding; it does not bypass visual admission |
| Methodology | No eligible finding/evidence binding | Still omitted | No source-backed candidate exists; no weak substitute was manufactured |

On the deterministic replay, the old fallback roster was
`intro-installs-growth`, `ai-maturity`, `platform-satisfaction`,
`gaming-casual-installs`, `ecommerce-installs`, `finance-installs`, and
`ecommerce-install-session-growth`. With the corrected canonical membership,
the strongest eligible roster became `finance-installs`,
`gaming-overall-retention`, `ecommerce-retention`, `finance-sessions`,
`ai-maturity`, `platform-satisfaction`, and `intro-installs-growth`. This
restores four addressable theme opportunities; methodology remains a correct
fail-closed omission.

### Fresh isolated Adjust replay

The run used the frozen Adjust PDF with SHA-256
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`, commit
`492b85a9`, and no canonical-artifact or WordPress write.

| Measure | Model-success baseline | Prior fallback replay | Corrected replay |
| --- | ---: | ---: | ---: |
| Provider calls | 56 | 51 | 48 |
| Input tokens | 545,144 | 645,698 | 626,134 |
| Output tokens | 113,908 | 103,218 | 124,280 |
| Estimated cost | `$0.125492` | `$0.135208` | `$0.138615` |
| Wall-clock | 924.187 s | 782.212 s | 807.477 s |
| Model / fallback candidates | 8 / 0 | 0 / 7 | 0 / 6 |
| Visual evaluated / admitted / quarantined | 8 / 7 / 1 | 7 / 5 / 2 | 6 / 6 / 0 |
| Final insights | 5 | 5 | 6 |
| Automatic repairs | 0 | 0 | 0 |

The corrected replay used three bounded candidate attempts and one recorded
structured-output recovery call; it did not trigger automatic report repairs.
Compared with the prior fallback replay it used three fewer provider calls
(-5.88%), 19,564 fewer input tokens (-3.03%), 21,062 more output tokens
(+20.41%), `$0.003407` more estimated cost (+2.52%), and 25.265 more seconds
(+3.23%). These are not a causal live-quality improvement claim: provider
candidate content and downstream routing are stochastic. The current
grounding ledger retained 12,635 cached input tokens versus 10,830 in the
prior replay; a compact cohort-level cached-token total was not retained.

Current stage ledger:

| Stage | Calls | Input | Output | Estimated cost |
| --- | ---: | ---: | ---: | ---: |
| Candidate primary | 1 | 58,114 | 10,314 | `$0.010968` |
| Candidate model repair | 1 | 64,081 | 2,210 | `$0.007513` |
| Candidate regeneration | 1 | 62,372 | 2,543 | `$0.007509` |
| Visual correction | 6 | 66,935 | 2,128 | `$0.007758` |
| Visual verification | 6 | 70,163 | 6,182 | `$0.010108` |
| Grounding | 8 | 73,010 | 48,144 | `$0.030235` |

### Final insight ledger and source review

All six final insights were inspected against full rendered PDF pages 6, 9,
11, 19, 30 and 35. The stable IDs, evidence IDs, protected factual fields,
physical pages and editorial wording remained aligned.

| Stable ID | Evidence ID / page | Final claim and independent review |
| --- | --- | --- |
| `finance-regional-growth-latam` | `verified-fact:finance-regional-growth-latam` / 35 | 76% installs and 57% sessions, 2024–2025, LATAM; the two metrics remain separate and the action is conditional benchmarking |
| `global-app-growth-2025` | `verified-fact:global-app-growth-2025` / 6 | 10% global installs in 2025 versus 8% in 2024; used as a historical acquisition benchmark, not a forecast |
| `gaming-casual-growth` | `verified-fact:gaming-casual-growth` / 19 | 19% installs and 37% sessions, 2024–2025, global casual gaming; install and engagement implications remain distinct |
| `ecommerce-paid-organic-ratio` | `verified-fact:ecommerce-paid-organic-ratio` / 30 | Global median paid/organic ratio 0.48 to 0.54; the wording does not turn channel mix into a performance verdict |
| `cross-platform-satisfaction` | `verified-fact:cross-platform-satisfaction` / 11 | Around 31% of marketers report complete satisfaction; the action is a diagnostic/data-priority implication, not an unsupported solution claim |
| `ai-efficiency-gains` | `verified-fact:ai-efficiency-gains` / 9 | Low/moderate maturity and a small advanced group above 20% efficiency gains; the qualifier and diligence recommendation are preserved |

Validation passed with two non-factual warnings: quotes abstained because no
quote was required, and the summary opening was broader than the retained
source-supported finding. Publication readiness passed all 16 rules. The
rendered HTML contained zero internal `verified-fact:`, `evidence:findings:` or
`source:page:` identifiers. The final artifact contains six metric-spine
entries and four key figures. No unsupported or materially incorrect numeric,
population, period, qualifier or page binding was found in this inspection.

The prior e-commerce installs/session pair remains two distinct source-backed
facts rather than a fuzzy merge. The existing final-selection contract already
permits a future multi-evidence synthesis when a final claim genuinely needs
both IDs; this replay did not demonstrate such a synthesis, and no distinct
decision was collapsed.

### Limitations and status

The run demonstrates bounded diagnostics, safe fallback, corrected theme
membership and a source-consistent final report. It does not demonstrate that
the provider will reliably produce usable model candidates: all three
candidate attempts again emitted location-only references. Exact discarded
provider content is unavailable by design, and this is one stochastic live
run. The dirty-worktree preflight failure occurred before any provider call
and is excluded from the measurements.

**Verdict:** PASS for the deterministic recovery diagnosis, fail-closed root
handling, canonical fallback membership, bounded candidate pool and current
report factual/readiness review; **PARTIAL/NO-GO** for live model shortlisting
effectiveness and Step 2/3 promotion. E18 remains **Active/PARTIAL**, Step 2
remains **PARTIAL/NO-GO**, and Step 3 remains unstarted/not ready.

## Artifact references

- Corrected fresh cohort result: `C:\ml-step1-adjust-p1-live-corrected\frozen-reliability-6s6d_312\cohort_result.json`
- Corrected final artifacts: `C:\ml-step1-adjust-p1-live-corrected\frozen-reliability-6s6d_312\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-xl7ef0zi\output\mobile-app-trends-2026-pdf\report_analysis\artifacts.json`
- Corrected candidate checkpoint: `C:\ml-step1-adjust-p1-live-corrected\frozen-reliability-6s6d_312\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-xl7ef0zi\output\mobile-app-trends-2026-pdf\report_analysis\prompt_family_report_vs_artifacts_insights_candidates.json`
- Corrected validation result: `C:\ml-step1-adjust-p1-live-corrected\frozen-reliability-6s6d_312\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-xl7ef0zi\output\mobile-app-trends-2026-pdf\report_analysis\validation.json`
- Corrected publication-readiness result: `C:\ml-step1-adjust-p1-live-corrected\frozen-reliability-6s6d_312\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-xl7ef0zi\output\mobile-app-trends-2026-pdf\report_analysis\publish_readiness.json`
- Corrected rendered report: `C:\ml-step1-adjust-p1-live-corrected\frozen-reliability-6s6d_312\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-xl7ef0zi\output\mobile-app-trends-2026-pdf\report_analysis\report.html`
- Fresh cohort result: `C:\ml-step1-adjust-p1-live\tmp\verified-claims-p1-recovery-20261025\frozen-reliability-9jjh7yog\cohort_result.json`
- Final artifacts: `C:\ml-step1-adjust-p1-live\tmp\verified-claims-p1-recovery-20261025\frozen-reliability-9jjh7yog\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-mzh1tlid\output\mobile-app-a5407b768f97\report_analysis\artifacts.json`
- Candidate checkpoint: `C:\ml-step1-adjust-p1-live\tmp\verified-claims-p1-recovery-20261025\frozen-reliability-9jjh7yog\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-mzh1tlid\output\mobil-a5407b768f97\report_analysis\prompt_family_report_vs_artifacts_insights_candidates.json`
- Validation result: `C:\ml-step1-adjust-p1-live\tmp\verified-claims-p1-recovery-20261025\frozen-reliability-9jjh7yog\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-mzh1tlid\output\mobile-app-a5407b768f97\report_analysis\validation.json`
- Publication-readiness result: `C:\ml-step1-adjust-p1-live\tmp\verified-claims-p1-recovery-20261025\frozen-reliability-9jjh7yog\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-mzh1tlid\output\mobile-app-a5407b768f97\report_analysis\publish_readiness.json`

## Candidate evidence-ID authority and multi-fact fidelity — 2026-10-26 (`c45dbfed`, `1c7164f2`)

### Candidate evidence boundary

The candidate-generation boundary now supplies an explicit
`candidate_allowed_evidence_ids_json` vocabulary built from the existing
fidelity-approved, page-addressable findings and eligible attributed quotes.
The vocabulary is not limited to the fallback roster: all eligible findings
are exposed. DocMap section IDs, `source:page:*` location labels, unknown or
ambiguous quotes, and unsupported/quarantined findings are excluded. The
primary candidate request and its existing bounded repair/regeneration path
receive the same vocabulary. The candidate validator checks both
`evidence_id` and optional `evidence_ids` before shortlisting, so a model
cannot bypass the boundary through a secondary reference. The shortlisting
cache identity is `evidence_backed_shortlisting:18`.

This is a deterministic candidate-ID correction; it does not add an LLM call,
change the candidate schema, alter model settings, or map page labels by
proximity. The provider-free tests also retain the existing fail-closed
fallback and cache behavior.

### Multi-fact production-path review

The existing verified grounding path was replayed by
`test_verified_grounding_batches_preserve_referenced_multi_fact_qualifiers`.
A final insight with primary `verified-fact:fact-1` and secondary
`verified-fact:fact-2` retains both complete canonical facts, their distinct
metrics, populations, timeframes, evidence IDs, pages, and source spans;
unrelated `fact-3` is excluded. The same test confirms that a missing
secondary fact fails with `verified_fact_snapshot_invalid`. A new candidate
regression rejects a secondary `section-1` reference even when the primary
finding is allowed. No second multi-fact validator or LLM stage was added.
The replay did not demonstrate a new multi-fact synthesis in the live report;
the two linked-fact contract is covered and the live final roster retained
distinct single-fact claims.

### Fresh isolated Adjust run

The one provider-backed run was started from `c45dbfed` before the final
verified-fact rebinding correction, using the exact frozen PDF SHA
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`. It made
no WordPress or canonical publication writes.

| Measure | Result |
| --- | ---: |
| Provider calls | 53 |
| Input tokens | 619,294 |
| Output tokens | 138,957 |
| Estimated cost | `$0.147772` |
| Wall-clock | 879.368 s |
| File-search calls | 7 |
| Structured-output recovery calls | 2 |
| Automatic report repairs | 0 |
| Visual facts evaluated / admitted / quarantined | 6 / 6 / 0 |
| Candidate model output / fallback supplementation | 7 / 1 |
| Selected candidate count | 6 |
| Persisted final insights in failed terminal state | 5 |

The candidate checkpoint was not empty. Its bounded audit recorded a present,
schema-valid list with seven normalized model candidates, no invalid evidence
reference rejection, no structured-output recovery, and
`fallback_reason=primary_incomplete`; one fidelity-approved fallback candidate
was used to complete the six-opportunity pool. Thus the model supplied most
candidate content and the fallback supplemented coverage; no silent empty
checkpoint or unbounded recovery occurred.

The run then failed closed during targeted regeneration with
`regeneration_evidence_rebind_unresolved` for
`verified-fact:finance-regional-growth-contrast`. The retained verified-fact
finding had a real physical page and excerpt, but the rebinding boundary only
recognized `findings` and `quote_candidates` source-pack labels. The failure
was not a candidate-ID rejection and did not promote an unsupported claim.
The saved validation result therefore contains a grounding error and summary
quality warnings; no publication-readiness artifact was produced. It recorded
zero unsupported retained factual claims, but the run is not a passing
end-to-end editorial result.

### Root-cause correction after the run

`1c7164f2` extends the existing page-bound rebind and canonical span checks to
the authoritative `verified_facts` source-pack representation, while keeping
the positive-page and non-empty-excerpt requirements. Canonical evidence text
restoration now treats those verified-fact spans as authoritative as well.
DocMap spans, missing pages, empty excerpts, quarantined IDs, and unrelated
source packs remain rejected. Focused integration coverage proves both that a
verified-fact rebind succeeds and that the existing DocMap rejection remains.
The provider run was not repeated after this correction, so its live terminal
failure is evidence of the pre-correction boundary and not a claim about the
corrected live outcome.

### Verification and status

The affected focused suite passed **613 tests** after the correction. Ruff's
enforced changed-file `F` check and formatting check passed; targeted mypy
passed for both changed source modules. The earlier prompt/grounding suite
remains green, including the existing verified multi-fact test and the
candidate prompt-fixture gate. No output schema or publication contract was
changed.

Final repository verification also passed the static, architecture, policy,
documentation, contract-schema, WordPress, and full-repository mypy gates.
The full pytest run completed with **8,159 passed, 2 skipped, 32 deselected,
and 1 environment-only failure**: the native wheelhouse audit requires CPython
3.12 while this runner is CPython 3.14. The affected artifact-generation
mutation partition killed **3/3 mutants (100%)**. The prompt-fixture gate
remained green at 109,185 tokens / `$0.024141` versus the 108,751-token /
`$0.024098` baseline; the only material delta is the already documented
publishing-family +434 tokens / +`$0.000043` candidate-evidence prompt input.

**Verdict:** **PASS** for the candidate evidence-ID boundary, secondary-ID
fail-closed behavior, verified-fact physical-page rebinding, existing
multi-fact preservation, and focused regression coverage. **PARTIAL/NO-GO**
for live end-to-end editorial quality because the only fresh run failed before
publication and was executed before `1c7164f2`; a post-fix provider result is
not claimed. E18 remains **Active/PARTIAL**, Step 2 remains **PARTIAL/NO-GO**,
and Step 3 remains unstarted/not ready.

### New artifact references

- Fresh candidate-ID run result: `C:\ml-step1-adjust-p1-candidate-ids-live\frozen-reliability-96wqh9bn\cohort_result.json`
- Fresh candidate-ID artifacts: `C:\ml-step1-adjust-p1-candidate-ids-live\frozen-reliability-96wqh9bn\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-cc85hvbl\output\mobile-app-trends-2026-pdf\report_analysis\artifacts.json`
- Candidate generation audit (embedded in artifacts cache): same `artifacts.json`, `_cache.candidate_generation`
- Fresh validation result: `C:\ml-step1-adjust-p1-candidate-ids-live\frozen-reliability-96wqh9bn\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-cc85hvbl\output\mobile-app-trends-2026-pdf\report_analysis\validation.json`
- Fresh regeneration audit: `C:\ml-step1-adjust-p1-candidate-ids-live\frozen-reliability-96wqh9bn\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-cc85hvbl\output\mobile-app-trends-2026-pdf\report_analysis\regeneration_candidate_audit_1.json`

## P0-P2 root-cause verification and c8 Adjust replay — 2026-10-26 (`c8a09eaf`)

### Targeted P1 regeneration correction

The preceding `1c7164f2` replay failed closed at
`regeneration_evidence_rebind_unresolved` for
`verified-fact:finance_latam_growth`. Inspection of
`_build_grounding_package()` showed that an `alternative_evidence` repair
excluded every evidence ID mentioned by a target issue, even when the issue
was an `artifact_quality` wording warning rather than a quarantined factual
binding. The package therefore had no usable current evidence for a safe
wording repair. The minimal correction in `c8a09eaf` excludes only explicit
quarantined evidence IDs and chooses replacement evidence only when such IDs
exist; otherwise the existing current evidence remains available. Factual
quarantine behavior is unchanged.

The new regression
`test_alternative_rebind_keeps_non_quarantined_current_evidence` exercises the
production package builder with an `artifact_quality` warning and proves that
the retained evidence ID remains in the grounding package. Existing
quarantined-evidence replacement tests remain unchanged. This correction does
not alter candidate ranking, fallback coverage, visual admission, prompts,
schemas, or retry policy.

### Fresh isolated Adjust replay

The run was isolated from clean `c8a09eaf`, used the retained PDF whose SHA-256
is `ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`, and
made no canonical-artifact, publication-readiness, HTML, WordPress, or other
external write. The source identity and PDF hash matched before visual
evaluation.

| Measure | c8 replay |
| --- | ---: |
| Provider calls | 44 |
| Input tokens | 348,173 |
| Output tokens | 60,562 |
| Estimated cost | `$0.090001` |
| Wall-clock | 726.949 s |
| File-search calls | 10 |
| Structured-output recovery calls | 1 |
| Automatic report repairs | 0 |
| Workflow retries | 0 |
| Visual candidates evaluated / admitted / quarantined | 6 / 4 / 2 |
| Visual outcome counts | 5 verified / 1 unresolved |
| Terminal state | `report_payload_incomplete` at `pre_validation` |

The candidate audit was not empty: six candidates were evaluated, four facts
were admitted, and the audit recorded five verified visual outcomes and one
unresolved outcome. Four supported themes were retained from five planned
themes. The lost cross-platform-satisfaction theme was not marked central;
all four admitted themes were selected and no weak padding was introduced.

### Quarantined-candidate ledger and source inspection

| Candidate | Provider result | Binding/source review | Terminal disposition |
| --- | --- | --- | --- |
| `marketers-platform-data-satisfaction` | Correction preserved the 31% claim; verification returned `verified` with substantive page notes and page 11 | Full PDF page 11 says that only around 31% of marketers report complete satisfaction with unifying and reading data across platforms. The canary recorded `verified_fact_corrected_binding_conflict`; the corrected result was not promoted without a compatible authoritative binding. | Quarantined fail-closed; no unsupported fact admitted |
| `gaming-cpi-2025` | Two bounded correction attempts returned `unresolved` | Full PDF page 20 contains gaming session-length and sessions-per-user charts, not CPI. The provider explicitly said the page cannot support the global gaming-CPI claim. | Quarantined fail-closed; no CPI fact admitted |

The four admitted facts were source-hash bound and retained the following
physical pages: `finance-latam-installs-growth-2025` p35,
`ecommerce-deal-discovery-cpi` p29, `ai-dynamic-segmentation` p9, and
`global-app-installs-2025` p6. Their protected metric structures and
`verified-fact:*` evidence identities are present in the retained artifact.
Because visual admission did not produce a complete report payload, no final
HTML, grounding result, publication-readiness result, or final editorial
quality claim exists for this run. The four provisional fact projections in
`artifacts.json` are evidence of safe partial admission only.

### Before/after and failure ledger

| Stage / observation | Evidence and disposition |
| --- | --- |
| Retained empty candidate checkpoint | The original raw provider response was not retained, so explicit `[]` versus missing root cannot be distinguished. The checkpoint was accepted without recovery; the existing bounded recovery/fallback path remains the safe interpretation. |
| Location-only candidate output | The later Adjust run had three present roots that normalized only to unsafe page/location IDs. Bounded recovery exhausted and fidelity-approved fallback supplied candidates; no location ID was promoted. |
| Noncanonical editorial-plan IDs | The prior `927555cc` replay failed coverage because the plan used stale IDs absent from current findings. Boundary validation in `f47a38e0` rejects these IDs before selection. |
| Grounding recovery exhaustion | A prior run made parse-valid but contract-invalid primary/repair/regeneration responses; bounded attempts ended in fail-closed grounding rather than accepting an incomplete result. |
| Verified-fact regeneration rebind | `1c7164f2` exposed that physical-page verified-fact spans were excluded by the alternative rebind boundary. `c8a09eaf` fixes the earlier, narrower package-empty case for non-quarantined wording warnings and adds a focused regression. The c8 provider run quarantined candidates before this path was reached, so no live post-fix rebind claim is made. |
| c8 visual admission | Page-11 binding conflict and page-20 wrong-metric evidence were both rejected; the workflow terminated at pre-validation with `report_payload_incomplete`. This is provider/result variance plus fail-closed admission, not evidence for weakening the boundary. |

The affected focused suite passed **220 tests**. Hosted CI run
`40310685397` for `c8a09eaf` passed all jobs, including tests, both mutation
partitions, and `release_evidence`. Local Ruff still reports only the
pre-existing findings in the long regeneration module/test split; no new-line
Ruff finding was introduced. The branch retains the protected unrelated ZIP
modification outside this clean verification worktree.

**Verdict:** **PASS** for the demonstrated minimal regeneration root-cause
fix, focused regression, source-hash check, bounded retry behavior, and
fail-closed visual admission. **PARTIAL/NO-GO** for the requested successful
post-fix Adjust E2E: the provider run ended before grounding/readiness and did
not produce a final report. No live selection or editorial-quality
improvement is claimed. E18 remains **Active/PARTIAL**, Step 2 remains
**PARTIAL/NO-GO**, and Step 3 remains unstarted/not ready.

### c8 artifact references

- Cohort result: `C:\ml-adjust-acceptance-final-runs-20261026d\frozen-reliability-j0em527l\cohort_result.json`
- Partial artifacts and visual admission audit: `C:\ml-adjust-acceptance-final-runs-20261026d\frozen-reliability-j0em527l\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-00r0qiz5\output\mobile-app-trends-2026-pdf\report_analysis\artifacts.json`
- Findings and fidelity ledger: `C:\ml-adjust-acceptance-final-runs-20261026d\frozen-reliability-j0em527l\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-00r0qiz5\output\mobile-app-trends-2026-pdf\report_analysis\evidence_fidelity.json`
- Provider usage ledger: `C:\ml-adjust-acceptance-final-runs-20261026d\frozen-reliability-j0em527l\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-00r0qiz5\state\llm_cost_ledger.jsonl`
- Full-page visual review images: `C:\ml-adjust-acceptance-final-runs-20261026d\frozen-reliability-j0em527l\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-00r0qiz5\verified_claims_visual_canary\a5407b768f97\crop_refine_pages\page-10.png` and `page-19.png`
