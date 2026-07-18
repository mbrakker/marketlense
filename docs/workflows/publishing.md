# Publishing

> **Documentation type:** Current reference
> **Canonical topic:** Publishing workflow
> **Update trigger:** Publish contract, validation gate, WordPress projection, or rollback procedure changes.

The publishing orchestrator sends validated report and approved projection payloads through the canonical WordPress service. It owns publish state transitions and idempotency; WordPress does not create new analysis or intelligence at runtime.

Canonical report post type: `ml_report`. New report publishing must not target core `post`, except for explicit one-time migration or repair flows.

Use `python -m src.cli publish-wp` after required configuration and validation are in place. `--draft` requests drafts for newly created posts, while `--force-report-cards` is reserved for canonical report-card remediation. Detailed setup, packaging, verification, and rollback guidance is in [WordPress operations](../ops/wordpress.md).

For report routes, `validation.json` includes the post-repair deterministic public-editorial release result. With `publish.validation_policy: block`, any enabled editorial blocker or an abstained unresolved repair prevents WordPress side effects. See [public editorial quality](../quality/public-editorial-quality.md) for retained artifacts, rollout waivers, and CI evidence.

Queue-driven Signal and Briefing publication is approval-gated. Generation
persists a source-linked package; `cover_generation` produces the mandatory
card assets and freezes the approval checksum; `publication_readiness` records
`awaiting_review`; and an explicit approval writes one `wordpress_publish`
outbox event. The worker rechecks approval, checksum, taxonomy/media/idempotency
and readback before writing. A verified post schedules the separate
`wordpress_projection` queue, which rebuilds the public intelligence projection
through the existing WordPress projection boundary. Live workers remain feature
gated. `queue-approve-publication --dry-run --yes` records the same durable
approval and executes the publish worker's complete local preflight without a
WordPress write; it does not fabricate a published event or projection.
