# E13 Repair Benchmark Evidence

This package freezes seven real historical failed repair cases in three
identity-separated cohorts. Every retained baseline attempt was rejected;
none was removed because it failed. The JSON manifests pin original promoted
artifacts, initial validation, six evidence packs, source run/audit references,
prompt identity, mutation scope, historical outcomes, and compatible identity
fields. They retain only references, hashes, identifiers, and bounded audit
fields. Source artifacts, rendered prompts, and full candidate audits remain
in their isolated local run storage.

## Frozen cohorts

| Manifest | Cases | Covered failure classes | Baseline success@3 | Baseline usage |
| --- | ---: | --- | ---: | --- |
| [`baseline-a21-five.json`](baseline-a21-five.json) (`d23482c46e0d8498bdf5dd0727472dfbc5c8da17d80443fba2ab43a0d68f12c4`) | 5 | summary, insight/metric, quote, Expert View, LinkedIn | 0/5 | 32 calls, 235,970 input + 51,700 output tokens, USD 0.109236; attempt-level attribution unavailable |
| [`baseline-mobile-editorial.json`](baseline-mobile-editorial.json) (`83b73c0b8fd0fe9dd6e54450fe7db132f5aea9c0bb495b7a01631dbdb0c4c428`) | 1 | summary, insight/metric, Expert View, public-editorial hard failure | 0/1 | 11 calls, 119,933 input + 23,322 output tokens, USD 0.051973; attempt-level attribution unavailable |
| [`baseline-doubleverify-linkedin-public-editorial.json`](baseline-doubleverify-linkedin-public-editorial.json) (`a586f229704a04aa2ebdda6bbcd5bdf7de74974bd15b5405ad64fbd5b8fc7363`) | 1 | summary, insight/metric, Expert View, LinkedIn, public-editorial hard failure | 0/1 | unavailable; no repair-attributable usage ledger was retained |

These manifests are deliberately separate. Their configuration, policy,
schema, validator, and build identities do not form one compatible baseline.
The first two have an unavailable historical validator identity. The third
pins its source result's Git SHA as the build attestation for audits from the
same workflow run; the validator identity is unavailable there as well. The
repair-response schema did not exist at any of these source commits, so its
historical identity is explicitly `unavailable`. The current aggregate schema
identity includes that response schema, which keeps every historical
comparison fail-closed.

## Measurement status

The implementation commit must be measured after it is committed, using its
exact full SHA. Each manifest is replayed independently by
`scripts/quality/replay_validation_repair_benchmark.py` through the existing
production validation-regeneration loop, with the same scoped validation and
artifact-regeneration model service clients used by the report workflow. The
provider schema projection uses the API-supported strict subset; the full
canonical schema remains authoritative when the response is validated. The
repair decision's fixed `replace` operation is explicitly typed as a string
for strict structured output. The response contract is identified as v3; its
failure class is derived from the planner's issue list. Replacement values
cross that provider boundary as JSON-encoded strings and are parsed before
the existing deterministic patch checks. The scorecard retains its normal
validation, evidence, mutation-scope, promotion, and rollback gates. It does
not author replacement copy or raise the configured retry limit.

The exact implementation SHA, per-cohort final metrics, per-failure-class
results, commands and test outcomes, and acceptance-criteria disposition will
be added here after the frozen replays and required quality gates complete.
No success, compatibility, or closure claim is made before those results are
retained.
