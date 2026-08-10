# 2026-08-10 20-Report Full-Funnel Reliability Run — Not Released

> **Producer revision:** `ef0da57423d1ec039c148b378a5f110b5f11ee8e`
> **Run namespace:** `reliability_full_20260810_62d021b3b57440eb8113ff5d5e105578`
> **Validation run:** `validation:312089980ce549c6c4a4f9ad7c39c57d63f44b8a5c6c6ef8dc357292a03bc032`
> **Evidence:** [strict CTO bundle](../CTO_evidence/reliability_full_20260810_62d021b3b57440eb8113ff5d5e105578/README.md)

The immutable 20-member cohort completed with typed terminal outcomes, but did
not meet the required reliability gate: 1 report became publish-ready and 19
ended in permanent ingestion failures. No WordPress write, authenticated
readback, or repeat-publication pass was performed; a partial cohort was not
published.

The dominant failure was `public_metadata_governance_blocked` (12 reports).
The run also exposed that direct-drive cohort admission allowed unresolved
publisher/source identity, which is inconsistent with the admission contract
and made those members ineligible for public metadata. The evidence retains
this failed attempt and its costs rather than replacing cohort members or
weakening a publication gate. The follow-up must correct source-identity
admission and perform a new isolated run; this record is not a release
approval.
