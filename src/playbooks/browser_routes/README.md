# Browser Route Playbooks

Marketlense browser route playbooks are file-based, reviewable acquisition guides for recurring publisher/report patterns. The format follows the browser-harness domain-skill idea of small opt-in playbooks with URL patterns, reusable route steps, traps, and version history, but stores only Marketlense contract fields and has no runtime dependency on browser-harness.

Each playbook is a separate YAML file in this directory. Playbooks are selected
before `browser-use` prompt rendering and cited as `playbook_id@version`. A
fresh publisher-specific playbook may execute before Browser Use only when
every step has a supported action, a deterministic selector, and either an
`expected_url_contains` or `expected_text` postcondition. Generic (`*`) and
incomplete historic playbooks remain prompt guidance rather than execution
authority.

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
- `steps`: ordered actions with `action`, `target`, and `verification`. Promoted
  verified steps additionally retain observed executable `selector_type`/`selector`, a
  `value_reference` such as `${identity.delivery_email}` instead of an identity value,
  and observed `expected_url_contains` or `expected_text` postconditions when present.
- `traps`: prompt-safe traps to avoid.
- `evidence_notes`: durable rationale for why this pattern is reusable.
- `source_evidence`: reviewable evidence labels.
- `private_api_evidence`: optional validated network-learned private API evidence. These entries are used only for deterministic HTTP-first attempts before browser preflight, browser launch, or Browser Use and must document endpoint pattern, method, request shape, JSON response pointer, accepted status codes, observed success count, and fallback route family.
- `history`: version/change metadata.

Production deterministic execution checks the postcondition after every step
and converts a completed run into the normal browser-result contract before
the existing artifact/submission finalizer runs. A missing selector or
postcondition, unsupported action, locator error, postcondition mismatch, or
failed artifact/submission verification records a bounded drift reason and
falls back to Browser Use; it never produces a terminal acquisition failure by
itself. A successfully finalized playbook records
`avoided_browser_use_model_call: true` and makes zero Browser Use model calls.

Before a deterministic playbook begins, the browser runtime makes one bounded,
optional consent preflight: it clicks a visible control whose normalized label
is exactly `Reject all`. It never accepts cookies, fills consent controls, or
turns the dismissal into acquisition success. A missing or nonstandard banner
is ignored and the normal deterministic route/fallback behavior remains in
force.

An isolated-worker navigation that has rendered the target page but does not
settle within 15 seconds is treated as an unsettled navigation, not a reason
to abandon the deterministic route. The worker continues on that current page
through the same consent preflight and action-level postconditions; the normal
route budget and final verification still govern the terminal outcome.

Role/name locators are exact: they must resolve exactly one current accessible
element, never a fuzzy or first-control match. `fill` and `type` support only
the native `textbox`/`searchbox` form controls; `select` supports only native
`<select>` controls observed as `combobox` or `listbox`. Any custom-control,
missing, or ambiguous match is drift and resumes Browser Use on the current
session. Promotion rejects action/locator combinations outside this executor
capability before writing an active playbook.

Stale behavior is controlled by `browser_download.route_playbook_stale_policy`. `fallback` logs stale matches and continues normal scoped discovery. `fail` raises a typed `browser_route_playbook_stale` error so stale guidance cannot silently influence acquisition.

Validated successful route evidence can be promoted through
`promote_validated_browser_route_result_to_playbook(...)`, which creates or updates a
YAML file with version/history metadata and returns a unified diff for review. Promotion
does not trust model-supplied `locator_evidence` or `postcondition_evidence`. It is
all-or-nothing and consumes only browser-runtime action records, each of which pairs a
successfully resolved locator with the immediate browser URL/title state after that one
action. Terminal or global evidence cannot validate an earlier action. If an execution
record is missing, incomplete, multi-action, or unverified—including a final email
submit—promotion returns the typed `not_promotable` status and writes nothing. It retains
the original step prose and evidence labels for audit, but ranks runtime-observed
locators as role, label, name, data attribute, CSS, then visible text. Fill/select steps
are promotable only with a safe `${identity.<key>}` reference; personal values are never
written to a playbook.
Report-download orchestration controls this with
`browser_download.route_playbook_promotion_mode`: `disabled` logs explicit skip records,
`dry_run` logs review diff metadata without writing, and `write` persists the reviewable
YAML file after verified/recovered browser-route evidence with structured steps.

Network-learned private API evidence is stored in separate YAML files under `private_api/`. The report-download orchestrator can promote this evidence automatically when `browser_download.private_api_playbook_promotion_mode` is `dry_run` or `write`: verified downloaded browser runs replay safe same-host GET endpoint candidates without cookies or auth headers, accept only JSON responses that expose the verified PDF URL through a stable pointer, store repeated observations in `publisher_private_api_candidates`, and promote only after the configured success and distinct-source thresholds. Operators can still call `promote_private_api_evidence_to_browser_playbook(...)` or `python -m src.cli promote-private-api-playbook --request-json <path>` for reviewed backfills. At runtime the browser-download service runs this validation before browser preflight, browser launch, or Browser Use; it validates the endpoint status, response markers, JSON pointer result, and final PDF artifact before accepting the deterministic route. Stale or rejected evidence logs a fallback reason and continues through the normal browser acquisition route.
