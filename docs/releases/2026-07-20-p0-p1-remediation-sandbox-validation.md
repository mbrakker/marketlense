# 2026-07-20 P0/P1 Remediation and Sandbox Validation

> **Documentation type:** Release history / live-validation record
> **Repository commit at execution start:** `f18eaf32`
> **Execution date:** 2026-07-20 (Europe/Paris)
> **Configuration:** `MARKET_LENSE_CONFIG_PROFILE=remediation_full_20260720`, [`src/config/app.remediation_full_20260720.yaml`](../../src/config/app.remediation_full_20260720.yaml)
> **Scope:** isolated discovery-to-sandbox-publication validation using real retained and newly acquired project artifacts. The configured WordPress target is the authorized sandbox.

## Controls exercised

- Report-analysis queue leases are 3,600 seconds (60 minutes), preventing the worker lease from pre-empting a bounded long-running report analysis.
- The profile has no PDF-count budget: both relevant `max_pdfs` values are `null`. Admission is governed by the canonical forecast and the $6 spend cap.
- The runtime, paths, state, output, cache, reports, and cost ledgers are isolated under the `remediation_full_20260720` namespace.
- The normal deterministic validation, public-editorial gate, publication preflight, WordPress lookup, and durable idempotency state all remained enabled.

## Live outcome

The run performed real publisher discovery (24 inventory reports, 20 newly qualified) and a real PDF acquisition with Drive archival. It then exercised report ingestion, analysis, validation, rendering, card generation, and publication against the isolated state.

An initial real model response surfaced an unsupported optional enum label. The normalizer was corrected to remove only unrecognised optional labels while retaining strict validation for required public fields. A later render-reuse recovery found a missing report-card manifest. The render generator now invalidates that incomplete reuse, rebuilds the cover set and manifest, and reports public-metadata governance failures as typed render failures rather than successful renders. Optional placeholder card metadata is normalized to omission before the public manifest is validated. A five-item rescan then exposed a missing-checkpoint recovery defect; force-card recovery now requests `analysis_complete` only for an existing rendered package, while new files run the normal pipeline.

The initial package had a passing semantic `validation.json`, a passing `public_editorial_quality_after.json`, and all three required card-cover assets. It was submitted through the canonical publishing orchestrator to the configured sandbox. Durable publication state recorded one `ml_report` post; a repeat publish was skipped as `already_published`, and a canonical authenticated post lookup read the same post back.

The final bounded cohort used the real CLI entrypoint with `--force-report-cards --rescan --limit 5`. Its first attempt safely found that force-card recovery was requesting `analysis_complete` for new files; the corrected path completed all five reports in 46.23 minutes. Every package passed both validation gates and retained all required cover assets. Canonical publication created three new sandbox posts and detected two matching existing posts. Repeating the same five paths made zero new WordPress writes: three exact checksum idempotency lookups returned their previously published outcomes and two state-level checks returned `already_published`.

## Cost and regression evidence

- Isolated LLM ledger: 159 completed calls, 1,883,341 total tokens, and **$1.152941** estimated spend, below the configured $6 cap.
- Focused affected regression suite: **122 passed** in 31.27 seconds. The only warnings were seven upstream Python 3.16 deprecation warnings from the vendored browser dependency.
- Changed-source Ruff check passed after formatting; `git diff --check` passed.

The run confirms two concrete qualitative improvements: an incomplete report-card asset set can no longer appear as a successful render or be sent to publication, and force-card recovery no longer requests a nonexistent checkpoint for new inputs. The system rebuilds a complete manifest-backed package when safe, otherwise retains a typed failure before any WordPress write.

No credentials, raw source URLs, source text, prompts, or model responses are retained in this record.
