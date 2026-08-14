# Acquisition failure remediation CTO evidence

## Scope and integrity

- Frozen cohort: 30 unique failed-acquisition candidates.
- Immutable manifest SHA-256: `1c41324dbb009a223c8add82b7dc949e7fd59895c0137f72a599794a6882425e`.
- No discovery, source substitution, processing, or WordPress publication was performed.
- Five historical candidates with a later verified artifact were excluded from the frozen failure cohort.

## Outcomes

The first complete diagnostic replay reached five verified native PDF artifacts,
eight explicitly non-native onsite HTML captures, four submitted email delivery
requests with no report received in the 180-second window, eleven email-gate
terminal states, and two browser timeouts. The Drive credential-path correction
made the diagnostic run executable from its dedicated worktree.

The final custom-select replay was stopped by operator direction after four of
six Jungle Scout candidates reached terminal states. Two in-flight candidates
remain `stopped_by_operator` / `unverified`; they are neither successes nor
recovered failures. This bundle therefore records a remediation investigation,
not a completed 30-candidate recovery run.

## Implemented fixes

1. Resolve relative credential paths against the explicitly supplied dotenv
   owner directory, preserving clean-worktree operation.
2. Use a publisher-scoped identity override for the authorized Jungle Scout
   business profile fields.
3. Bound longer waits to email form and mailbox-delivery routes only.
4. Traverse open shadow roots and recognize custom combobox/listbox controls
   in the shared browser form helper. Configured values are still selected only
   when a live visible option matches and persists.

## Evidence files

- `failed_acquisition_manifest.json`: immutable cohort and original attempts.
- `diagnostic_before_path_resolution_fix/`: preflight failure evidence.
- `diagnostic_after_credential_fix/`: complete 30-candidate diagnostic replay.
- `replay_research_identity/`, `replay_complete_identity/`, and
  `replay_shadow_dom_fix/`: targeted replays and their terminal outcomes.
- `replay_custom_select_fix/acquisition_attempts.jsonl`: four completed and
  two interrupted members from the final targeted replay.

## Verification

Focused tests passed before the last live replay:

```
python -m pytest tests/test_browser_download_helpers.py tests/test_acquisition_failure_remediation.py -q
# 12 passed
```

The bundle is intentionally explicit about unresolved external/custom-control
and mail-delivery blockers. It does not claim full recovery or autonomous
acquisition closure.
