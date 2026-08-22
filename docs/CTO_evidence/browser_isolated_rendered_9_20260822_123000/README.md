# Isolated rendered-PDF non-regression replay — 2026-08-22

This acquisition-only replay used the retained nine-report rendered-PDF
cohort from `../browser_rendered_pdf_validation_20260821_080508/` on commit
`32bbeb9941943a409e0f2fc1ac2ffc25802837ce`. The process-isolated supervisor
produced nine terminal records: seven passed normal acquisition verification,
and all seven are retained as `rendered_onsite_pdf`. Two reports did not pass
normal verification. The acquisition stack did not run discovery, ingest,
analysis, extraction, generation, publishing, or WordPress.

The profile is `src/config/app.browser_isolated_rendered_9_20260822_123000.yaml`.
The raw per-report evidence is `acquisition_attempts.jsonl`; child evidence is
retained under `isolated_attempt_workers/`.
