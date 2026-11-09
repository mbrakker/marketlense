# Sanitized live inspection notes

## Scope

The run used the exact frozen Activate and Adjust source identities listed in
`source_identity_manifest.json`, full provider-backed processing, GPT-6 Luna
High routing from the existing runner, isolated fresh state, and no publication
or WordPress writes. This note intentionally excludes raw model responses,
rendered prompts, source excerpts and copyrighted PDF content.

## Handoff inspection

* Both reports passed source admission and verified-facts admission: 10/10
  evaluated and admitted, 0 quarantined for each report.
* Both reports reached `artifact_generation` successfully and therefore
  exercised the corrected verified editorial-plan normalization. The accepted
  plan contains seven themes in each report and the artifact projection
  materialized seven final insight items in each report.
* The plan validator derived mechanical candidate bindings from the admitted
  candidate/evidence relationship. No model-invented candidate binding was
  promoted. The transform-version bump invalidates incompatible cached plans.
* Both reports stopped before final readiness/rendering; an exact HTML-file
  check found no generated HTML under either isolated output tree.

## Terminal failures

The failure is not an unexplained process exit. The authoritative validation
projection reports `validation_grounding_invalid_json` caused by incomplete
`public_item_coverage` in a grounding batch:

* Activate: missing/ambiguous item
  `soft_copy:expert_comment:8f99ed4197a3ac39`.
* Adjust: missing/ambiguous item `insight:insight-09:now_what`.

The stage ledger records both `grounding_validation` and `semantic_validation`
as failed, `regeneration` as skipped with `no_actionable_repair`, and the
terminal stage as `semantic_validation`. This is the intended fail-closed
handoff: the incomplete verdict did not become a verified factual result.

The same validation projections retain two independent editorial-quality
issues: Activate's support mismatch for `insight:finding-05:text`, and
Adjust's semantic redundancy in the `insight-09` so-what. Neither issue was
silently converted to a pass.

## Before/after interpretation

The prior retained failures stopped at `editorial_plan_invalid` for Activate
and at an earlier editorial-plan failure in the corrected Adjust rerun. On the
current SHA, both reports reach the verified plan and downstream grounding.
This demonstrates a real upstream handoff improvement, not a complete E2E
acceptance: grounding coverage and public-editorial quality still block
readiness, and no live improvement is claimed for those downstream failures.

No final insight, source binding, canonical artifact or readiness state was
promoted from this failed run.
