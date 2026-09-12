# Step 10 retained IAS regression — no-go evidence

This directory records the Step 10B provider-safe regression attempted on the
exact Step 10A-green tree, `876c602c2b877fc90db165e96aa2d3bbef9f2b37`.

The historical IAS artifact is preserved in place as the before-state. It was
not rewritten, normalised, or supplied synthetic provenance. The current
deterministic retained-claim validator therefore fails it closed before a
bounded regeneration candidate can be constructed: the historical artifact
predates mandatory `soft_copy_claim_provenance`.

`before_claim_validation.json` is the separately retained output of
`validate-retained-claims`; `manifest.json` records fixture identities,
historical grounding failures, the attempted checks, and the resulting blocker.
No live canary was run.
