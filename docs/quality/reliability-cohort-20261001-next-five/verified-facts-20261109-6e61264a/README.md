# Adjust grounding-correction rerun

Run date: 2026-11-09

Producer SHA: `6e61264a89373caaf5c944ac7c57d5977c22c9bc`

This is the required fresh isolated rerun of Adjust after the explicit
absence-marker correction in the semantic disposition contract. The source
PDF SHA-256 is
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3` and the
physical page count is 41. The PDF bytes are retained only in the authorized
local source workspace, not in Git.

## Terminal outcome

| Measure | Result |
| --- | ---: |
| Admission | admitted |
| Terminal result | failed |
| Failure | `artifact_structured_output_invalid` / `editorial_plan_invalid` |
| Recovery attempts | 2 |
| Provider calls | 148 |
| Input tokens | 665,199 |
| Output tokens | 97,268 |
| Estimated cost | $0.130028 |
| Wall-clock | 1,285.047 s |
| Automatic repairs | 0 |
| Final HTML | not generated: editorial plan remained invalid |
| WordPress writes | 0 |

The provider responses were parseable, but the editorial-plan contract remained
invalid after the existing two-attempt bounded recovery. The run stopped before
verified-facts generation and grounding, so it provides no new semantic verdict
for the absence-marker fix. This is retained as a provider/editorial-plan
contract failure, not as evidence that the grounding correction failed.

Safe projections are under `export/reports/`; raw caches, databases, ledgers
and source PDF bytes are excluded. Verdict: **PARTIAL / NO-GO**.
