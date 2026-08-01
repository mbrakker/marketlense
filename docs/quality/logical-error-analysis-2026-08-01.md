# Logical Error Analysis — 2026-08-01

> **Documentation type:** Point-in-time review
> **Scope:** Repository logic and default fast-suite behavior at the reviewed
> revision
> **Status:** Proposed remediation; this document does not claim the findings
> are fixed

## Method and limits

This review combined the default test suite, the repository's compile, lint,
typing, architecture, contract-schema, service-boundary, and documentation
gates, and focused executable probes of the publish-readiness boundary. A
finding is listed only when repository code or a deterministic reproduction
demonstrated the behavior. Passing gates are not treated as proof that no other
logical errors exist.

The review found four actionable errors. They are ordered by operational risk,
not estimated implementation effort.

## Findings

### LE-1 — A fast cache test expires with wall-clock time and escapes to a live browser

**Priority:** High

**Evidence and impact.**
`test_browser_download_reuses_valid_artifact_acquisition_cache` stores an
expiry of `2026-08-01T00:00:00Z`. The production cache reader correctly rejects
that row after the fixed instant. On 2026-08-01 at 18:22 UTC, the default test
therefore missed the cache, launched the real Browser Use boundary, attempted
browser installation and telemetry network calls, and failed after a timeout.
The observed suite result was `1 failed, 2221 passed, 25 deselected`. This is
both a date-dependent assertion error and a default-suite isolation error:
the test's failure path performs uncontrolled external work instead of failing
immediately at the intended seam.

**Proposed solution.**

1. Generate `expires_at_utc` relative to the test's current UTC time (or inject
   the cache clock if a current clock seam already exists), with enough margin
   for the test duration.
2. Replace the browser/external acquisition public boundary in this test with
   an approved fail-fast fake whose invocation raises an assertion. Keep the
   cache reader and persisted SQLite row real so the primary cache logic is not
   mocked.
3. Assert the cache-hit event or equivalent avoided-acquisition outcome in
   addition to the returned artifact.

**Acceptance criteria.**

- The test passes before and after UTC midnight and does not contain a fixed
  absolute expiry.
- Removing or corrupting the cache row makes the test fail immediately because
  the external-boundary fake was invoked; no browser process, package install,
  telemetry request, or provider request occurs.
- The result still points to the cached file and reports verified artifact
  validation.
- The focused test passes with network access disabled.

### LE-2 — Persisted publish-readiness payload parsing can crash instead of failing closed

**Priority:** High

**Evidence and impact.**
`parse_publish_readiness_payload` checks that `rule_results` is a list and each
result is a mapping, but iterates `item["surfaces"]` without validating that
field. The focused probe
`parse_publish_readiness_payload({"rule_results": [{"surfaces": None}]})`
raises `TypeError: 'NoneType' object is not iterable`. Because this parser reads
a persisted payload used by publication preflight, one malformed or partially
migrated artifact can abort the workflow rather than produce the intended
non-ready decision.

**Proposed solution.**

Validate every nested collection before iteration and parse through the
versioned contract/schema boundary. Unsupported shapes should either return a
contract that verification deterministically rejects (for example with an
empty/unsupported schema and failed rule) or raise the canonical non-retryable
contract `AppError` that the preflight converts to a blocked publication. Do
not silently coerce malformed nested data into a passing decision.

**Acceptance criteria.**

- `surfaces` values of `null`, scalar, mapping, and mixed-element list never
  leak `TypeError`, `AttributeError`, or `ValueError` from publication
  preflight.
- A valid serialized readiness artifact round-trips without field loss and
  retains a valid signature.
- Every malformed payload deterministically blocks publication with a stable
  readiness/contract issue code and no WordPress call.
- Tests cover invalid top-level type, invalid `rule_results`, invalid nested
  `surfaces`, and a valid round trip.

### LE-3 — Category “consistency” passes when either side is absent

**Priority:** High

**Evidence and impact.**
The readiness category rule fails only when both the canonical category list
and artifact category list are non-empty and unequal. Focused probes showed
that `canonical=[] / artifact=["markets"]`,
`canonical=["markets"] / artifact=[]`, and both lists empty all return `pass`.
The first two cases are not consistent: publication has lost one side of the
assignment comparison. A report can consequently receive a passing category
rule without proving that its rendered/retained decision matches the canonical
publication assignment.

**Proposed solution.**

Define the required category presence explicitly at this gate. For report
publication, require both normalized lists to be non-empty and equal. If a
legitimate uncategorized report state exists, represent it with an explicit
contract value and policy rather than overloading an empty collection. Return
distinct stable details for missing canonical assignment, missing artifact
assignment, and mismatch.

**Acceptance criteria.**

- Equal non-empty category sets pass regardless of input ordering or duplicate
  values.
- Missing canonical categories, missing artifact categories, both missing, and
  unequal normalized sets fail closed with stable reason codes/details.
- The publish boundary performs no WordPress write for each failing case.
- Contract and workflow documentation state whether uncategorized reports are
  prohibited or name the explicit supported representation.

### LE-4 — A malformed plural evidence reference crashes readiness evaluation

**Priority:** Medium

**Evidence and impact.**
`_claim_evidence_ids` expands `item.get("evidence_ids")` as an iterable without
checking its type. The focused probe using a claim ledger with
`"evidence_ids": 1` raises
`TypeError: Value after * must be an iterable, not int`. A string would be
accepted character-by-character, producing misleading validation rather than
a clear contract failure. Artifacts are retained boundary data, so invalid
shape must block deterministically rather than crash or be reinterpreted.

**Proposed solution.**

Normalize evidence references with a typed helper: accept a scalar
`evidence_id` and a list/tuple of scalar `evidence_ids`; reject mappings,
strings used as the plural collection, numbers, `null` elements, and nested
collections according to the artifact contract. Surface invalid shape as a
material-evidence rule failure (or canonical contract error) before membership
checks.

**Acceptance criteria.**

- Valid scalar-only, list-only, and combined evidence references normalize to
  the expected set and preserve the existing positive behavior.
- Numeric, mapping, string-as-list, and nested plural references cannot raise a
  built-in exception or be split into character IDs; each blocks readiness
  with a stable contract/material-evidence reason.
- Unknown but well-formed evidence IDs continue to fail the retained-evidence
  membership check.
- Focused tests cover the positive paths and every invalid-shape class.

## Validation observations outside the four findings

- Python compilation, the repository lint gate, architecture-import gate,
  role-I/O boundary gate, contract-schema snapshot gate, service-boundary map
  gate, and documentation gate passed during the review.
- The type gate did not pass in this environment. Most reported errors were
  missing installed `types-PyYAML` and `types-requests` packages even though
  they are declared in `requirements-dev.txt`; it also reported unbaselined
  nullable-value errors in publish readiness and render/category services.
  These diagnostics should be triaged before changing the baseline, but this
  review does not label them as additional runtime errors without a focused
  behavioral reproduction.
- The focused existing publish-readiness tests passed (`7 passed`). They do not
  cover the malformed shapes or missing-side category cases above.

## Recommended remediation order

1. Fix LE-1 first to restore a bounded, deterministic default suite.
2. Fix LE-2 and LE-4 together at the persisted readiness contract boundary,
   while keeping their acceptance cases distinct.
3. Fix LE-3 after confirming the documented product policy for uncategorized
   reports; default to fail-closed if no supported state is documented.
4. Run the focused suites and all fast gates, then run the approved isolated
   discovery → acquisition → ingest → publish validation workflow because the
   readiness fixes affect the publication control path.
