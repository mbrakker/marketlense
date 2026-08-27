# Publishing

> **Documentation type:** Current reference
> **Canonical topic:** Publishing workflow
> **Update trigger:** Publish contract, validation gate, WordPress projection, or rollback procedure changes.

The publishing orchestrator sends validated report and approved projection payloads through the canonical WordPress service. It owns publish state transitions and idempotency; WordPress does not create new analysis or intelligence at runtime.

Canonical report post type: `ml_report`. New report publishing must not target core `post`, except for explicit one-time migration or repair flows.

Use `python -m src.cli publish-wp` after required configuration and validation are in place. `--draft` requests drafts for newly created posts, while `--force-report-cards` is reserved for canonical report-card remediation. Detailed setup, packaging, verification, and rollback guidance is in [WordPress operations](../ops/wordpress.md).

For report routes, `publish_readiness.json` is required. It is a signed/hash-verified decision over the exact rendered HTML and the normalized final WordPress body projection, including semantic/grounding state, evidence and figure linkage, public-surface checks, artifact/configuration/policy hashes, producer revision, and expiry. With `publish.validation_policy: block`, a missing, expired, altered, failed, or incompatible readiness artifact prevents WordPress side effects. Publication verifies the retained decision before uploads and verifies the completed media projection before the post write; it never reruns a parallel editorial checker. See [public editorial quality](../quality/public-editorial-quality.md) for the rule inventory and retained repair diagnostics.

When ordinary ingest encounters a non-ready retained Report package, it writes
the typed `publish_readiness_refresh_plan.json` beside the canonical readiness
artifact and uses the existing lineage-enforced report recovery path before a
later publication attempt. This automatic refresh performs no WordPress action:
it only reuses a proven checkpoint, then produces a new canonical readiness
decision. A `missing_unverifiable` decision is persisted as blocked and cannot
fall back to an implicit full package reuse. Publication remains separately
approval-gated.

Every `PublishOutcome` retains an ordered, persisted transaction proof alongside the terminal disposition. The finite dispositions are `preflight_passed`, `preflight_blocked`, `existing_post_matched`, `post_created`, `post_updated`, `idempotent_checksum_skip`, `already_published_state_skip`, `authenticated_lookup_matched`, `authenticated_content_readback_verified`, `metadata_readback_verified`, `readback_failed`, `rollback_started`, `rollback_completed`, and `rollback_failed`; successful paths are never collapsed to a generic `completed` result. Before candidate-specific lookups or mutations, an authenticated target-schema preflight verifies that each candidate post type exposes its required proof metadata. A failing schema check blocks every candidate of that type with no WordPress write request. The proof is stored in the canonical publication idempotency record with only bounded field-status checks and hashes, not raw post content or source text.

A bounded release canary must separately verify a created post through authenticated `context=edit` REST readback, then repeat the exact package with zero requested and actual post writes. Its readback checks post ID, post type, status, report/file identity, raw-content checksum, canonical URL, Open Graph URL when WordPress exposes it, source-attribution metadata, taxonomy assignments, featured/card media associations, and the prior captured rendered-content hash when supported. The first verified readback captures the rendered hash; later idempotent readbacks must match it. Candidates with a matching idempotency record remain eligible for authenticated lookup/readback, but skip taxonomy resolution as well as post mutation, because an `ensure` request may itself write. This verification is permitted only against an explicitly configured sandbox target.

Queue-driven Report, Signal, and Briefing publication is approval-gated. Report
rendering writes the canonical readiness decision, then records one immutable
readiness package containing the exact HTML and readiness references. Signal and
Briefing generation persist source-linked packages, and `cover_generation`
freezes their mandatory card assets. `publication_readiness` records
`awaiting_review`; an explicit approval writes one `wordpress_publish` outbox
event. The Report worker rechecks approval and the two-surface package checksum,
then calls the existing report publisher with exactly that one candidate and
readiness reference. It never scans `output_dir`. A cohort manifest resolves
only admitted Report members before candidate construction.

`publish-wp --cohort-manifest <path>` is an all-or-nothing publication binding,
not a best-effort filter. Before the first WordPress schema, taxonomy, lookup,
media, or post operation, every admitted member must resolve to exactly one
existing Report HTML artifact. Its manifest and report-store mappings must agree;
the Report and embedded source identities must match the member; source mapping
must be current and compatible; persisted state and `publish_readiness` must
pass. Missing, duplicate, changed, stale, incompatible, unready, or ambiguous
members abort the whole attempt—none are silently excluded and no unrelated
artifact can enter the candidate set. The ordered resolved set is persisted at
`<output_dir>/cohorts/<cohort_id>/publication_candidate_set.json` with the
manifest SHA-256, cohort ID, configuration and policy hashes, per-artifact HTML
and readiness hashes, and a deterministic `candidate_set_hash`. Re-resolving
unchanged inputs produces the same ordered membership and hash; changed mapping
or membership changes that hash or fails binding.

All workers recheck approval, checksum, taxonomy/media/idempotency and readback
before writing. A verified Briefing or Signal post schedules the separate
`wordpress_projection` queue, which rebuilds the public intelligence projection
through the existing WordPress projection boundary. Live workers remain feature
gated. `queue-approve-publication --dry-run --yes` records the same durable
approval without a WordPress write; it does not fabricate a published event or
projection.
