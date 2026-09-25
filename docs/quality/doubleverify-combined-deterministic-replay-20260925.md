# DoubleVerify combined deterministic replay

The retained DoubleVerify candidate path was replayed from the original
artifacts using the production planner, handlers, candidate validator, and
candidate-audit writer. The replay used a fresh output/cache directory on code
SHA `96fb3014be8c44cd7501da03130767f755b3fbf4` (requested starting HEAD
`3637bda9e04da2c8c33cc8af059b4a1656dfe27d`).
It made zero provider or model calls, edited no candidate artifact by hand, and
did not promote or publish the final candidate.

The original Expert View and LinkedIn metric-label issues selected the same
three distinct strategies for both targets: `REGENERATE_ITEM/current_evidence`,
`REBIND_EVIDENCE/alternative_evidence`, then
`REMOVE_CLAIM/safe_removal`. Retained attempts 1 and 2 remain rolled back.
Attempt 1's prior `grounding:metadata.title` outcome is not reproducible from
the current grounding payload: the canonical normalized title and publisher
are omitted from probabilistic grounding. Retained attempt 2 still rejects the
unsupported LinkedIn values `125` and `82`.

Attempt 3 reached candidate validation and wrote its audit successfully with
zero candidate-integrity issues, zero scope issues, and a passing audit status.
Final provenance covers the public copy exactly. Claim counts are summary
`7→7`, Expert View `4→0`, and LinkedIn `12→11`; the summary and 11 retained
LinkedIn claims remain. Neither `125` nor `82` appears in the final LinkedIn
copy. Both `topics_covered` and `claim_ledgers` remain unchanged on this
soft-copy-only repair.

Public editorial quality passes, retained-claim validation found zero
unsupported factual claims, and canonical metadata identity was unchanged.
There are 22 unresolved factual claims because semantic model validation was
intentionally not called. This replay does not claim publication readiness;
it verifies the deterministic repair path and supports proceeding to one final
isolated live closure canary. The retained full attempt-2 validation contains
both numeric rejection messages. A separately reconstructed inline smoke
using a generic test report payload saw only `82`; it is recorded as a
non-equivalent diagnostic, not substituted for the retained production result.

The JSON record contains issue IDs, allowed paths, metadata values, usage,
validation outcomes, artifact hashes, warnings, and retained output paths:
[doubleverify-combined-deterministic-replay-20260925.json](doubleverify-combined-deterministic-replay-20260925.json).
