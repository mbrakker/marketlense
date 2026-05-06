# Browser Route Playbooks

Marketlense browser route playbooks are file-based, reviewable acquisition guides for recurring publisher/report patterns. The format follows the browser-harness domain-skill idea of small opt-in playbooks with URL patterns, reusable route steps, traps, and version history, but stores only Marketlense contract fields and has no runtime dependency on browser-harness.

Each playbook is a separate YAML file in this directory. Playbooks are selected before `browser-use` prompt rendering, cited as `playbook_id@version`, and treated as route guidance rather than proof that the current page still behaves the same way.

Required fields:

- `schema_version`: currently `1.0`.
- `playbook_id`: stable ID for prompts, logs, and review.
- `version`: semantic version.
- `status`: `active` or `deprecated`.
- `updated_at`: UTC ISO date or timestamp.
- `stale_after_days`: age limit before stale handling applies.
- `publisher_pattern`: human-readable publisher/domain pattern.
- `host_patterns`: host suffix/glob patterns; `*` is publisher-agnostic.
- `url_path_markers`: lowercase URL path/query markers used for selection.
- `route_family`: planned browser route family such as `browser_pdf_click`, `browser_email_form`, or `browser_onsite_report`.
- `route_kind`: expected result kind such as `pdf_download`, `email_delivery`, or `onsite_report`.
- `summary`: prompt-safe route guidance.
- `steps`: ordered actions with `action`, `target`, and `verification`.
- `traps`: prompt-safe traps to avoid.
- `evidence_notes`: durable rationale for why this pattern is reusable.
- `source_evidence`: reviewable evidence labels.
- `history`: version/change metadata.

Stale behavior is controlled by `browser_download.route_playbook_stale_policy`. `fallback` logs stale matches and continues normal scoped discovery. `fail` raises a typed `browser_route_playbook_stale` error so stale guidance cannot silently influence acquisition.

Validated successful route evidence can be promoted through `promote_validated_browser_route_result_to_playbook(...)`, which creates or updates a YAML file with version/history metadata and returns a unified diff for review. Promotion rejects unverified or unsuccessful route results.
