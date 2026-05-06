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
- `private_api_evidence`: optional validated network-learned private API evidence. These entries are used only for deterministic HTTP-first attempts before browser-use and must document endpoint pattern, method, request shape, JSON response pointer, accepted status codes, observed success count, and fallback route family.
- `history`: version/change metadata.

Stale behavior is controlled by `browser_download.route_playbook_stale_policy`. `fallback` logs stale matches and continues normal scoped discovery. `fail` raises a typed `browser_route_playbook_stale` error so stale guidance cannot silently influence acquisition.

Validated successful route evidence can be promoted through `promote_validated_browser_route_result_to_playbook(...)`, which creates or updates a YAML file with version/history metadata and returns a unified diff for review. Promotion rejects unverified or unsuccessful route results.

Network-learned private API evidence is stored in separate YAML files under `private_api/`. Promote it with `promote_private_api_evidence_to_browser_playbook(...)` only after repeated validated successes, documented request shape, and an explicit fallback route family. At runtime the browser-download service validates the endpoint status, response markers, JSON pointer result, and final PDF artifact before accepting the deterministic route; stale endpoints log a fallback reason and continue to the normal browser route.
