# Retained PDF candidate benchmark corpus

This committed corpus contains the three real PDFs exercised by
`docs/quality/pdf_candidate_extraction_benchmark_baseline.json`.

| File | SHA-256 |
| --- | --- |
| `CAPGEMINI - 2026-Retail-Trends_ACIG.pdf` | `72a04abd394dfcb6b14288b97548669501e70c087eb6cee8bc8b9a66589cb0c7` |
| `IAS - Industry_Pulse_Report_2026_ACIG.pdf` | `8b05b13067748baebff51844a702a05dd6eb560706db5fa94b2ee5badbd672cd` |
| `JULIUS BAER - Secular-outlook-2026_ACIG.pdf` | `156032ae914753000d51085c5e1c6e2f2d4680b9d046bb18df6cefcb265ce193` |

The benchmark validates each file hash before comparing candidate count,
signature, degraded-page count, and runtime against the committed baseline.
