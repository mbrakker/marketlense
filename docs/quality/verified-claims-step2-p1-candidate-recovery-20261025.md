# Verified Claims Step 2 — P1 candidate-generation and recovery evidence

Date: 2026-10-25
Producer commit: `5182502dc3e7efbea4c13cb5e7c4437a6f7f2769`
Scope: one fresh provider-backed Adjust run, shadow-only, no publication writes.

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

## Artifact references

- Fresh cohort result: `C:\ml-step1-adjust-p1-live\tmp\verified-claims-p1-recovery-20261025\frozen-reliability-9jjh7yog\cohort_result.json`
- Final artifacts: `C:\ml-step1-adjust-p1-live\tmp\verified-claims-p1-recovery-20261025\frozen-reliability-9jjh7yog\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-mzh1tlid\output\mobile-app-a5407b768f97\report_analysis\artifacts.json`
- Candidate checkpoint: `C:\ml-step1-adjust-p1-live\tmp\verified-claims-p1-recovery-20261025\frozen-reliability-9jjh7yog\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-mzh1tlid\output\mobil-a5407b768f97\report_analysis\prompt_family_report_vs_artifacts_insights_candidates.json`
- Validation result: `C:\ml-step1-adjust-p1-live\tmp\verified-claims-p1-recovery-20261025\frozen-reliability-9jjh7yog\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-mzh1tlid\output\mobile-app-a5407b768f97\report_analysis\validation.json`
- Publication-readiness result: `C:\ml-step1-adjust-p1-live\tmp\verified-claims-p1-recovery-20261025\frozen-reliability-9jjh7yog\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-mzh1tlid\output\mobile-app-a5407b768f97\report_analysis\publish_readiness.json`
