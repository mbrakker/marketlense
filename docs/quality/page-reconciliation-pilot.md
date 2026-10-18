# PDF page reconciliation Phase 1 pilot

## Scope and implementation

This is the standalone Phase 1 pilot for commit
`c6fca0eb4b24f6b9483bb6cd75c772b3ec692a1d` (`pdf-page-reconciliation-v1`). It
maps one-based physical PDF pages to visible printed labels using positioned
native PDF text and bounded local sequence inference. It does not call OCR,
LLMs, File Search, vector stores, network services, report processing,
evidence-pack generation, claim validation, caches, checkpoints, or publication
flows. The JSON output is written only by the diagnostic runner to its explicit
output directory and is not consumed by any downstream producer.

The runner was invoked as:

```powershell
python scripts/quality/reconcile_pdf_pages.py --pdf "<golden-pdf>" --output-dir "<temporary-diagnostic-directory>" --force
python scripts/quality/reconcile_pdf_pages.py --pdf "<golden-pdf>" --output-dir "<temporary-diagnostic-directory>"
```

The first command was repeated three times for fresh measurements. The second
command measured warm-cache reuse. The canonical JSON contains only the source
MD5, algorithm/schema versions, page mappings, bounded evidence, and coverage
counts/percentages; elapsed time is printed only in the runner summary.

## Committed golden PDFs

| PDF | SHA-256 | MD5 | Physical pages | Verified | Inferred | Unresolved | Fresh runs (ms) | Fresh median (ms) | Warm cache (ms) |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| `2026_Global_Food_and_Drink_Predictions.pdf` | `0d10fa30d4df83b8ec74a63db363b5bd98eb52497e5cc9a2300152d9713d6b16` | `b3cb5f66cccda4420be21b2b407b3c59` | 8 | 0 (0.00%) | 0 (0.00%) | 8 (100.00%) | 302.11, 255.79, 398.19 | 302.11 | 12.33 |
| `CAPGEMINI - 2026-Retail-Trends_ACIG.pdf` | `72a04abd394dfcb6b14288b97548669501e70c087eb6cee8bc8b9a66589cb0c7` | `c1cbe57c96a1d81476730e83828d07d9` | 15 | 12 (80.00%) | 0 (0.00%) | 3 (20.00%) | 100.76, 96.85, 127.18 | 100.76 | 11.48 |
| `IAS - Industry_Pulse_Report_2026_ACIG.pdf` | `8b05b13067748baebff51844a702a05dd6eb560706db5fa94b2ee5badbd672cd` | `fccf7f92dc7e14a27ee6a90daf16705a` | 33 | 31 (93.94%) | 1 (3.03%) | 1 (3.03%) | 949.40, 870.66, 820.24 | 870.66 | 24.58 |
| `JULIUS BAER - Secular-outlook-2026_ACIG.pdf` | `156032ae914753000d51085c5e1c6e2f2d4680b9d046bb18df6cefcb265ce193` | `468e8c08c83182f4803e07f5357c9160` | 36 | 26 (72.22%) | 2 (5.56%) | 8 (22.22%) | 240.92, 193.66, 279.59 | 240.92 | 26.09 |

These are parser coverage measurements, not an automated accuracy claim.

## Visual and label review

I rendered and inspected representative source pages with PyMuPDF, including
cover/no-label pages, ordinary footers, transitions, inferred pages, long lower
margin blocks, and ambiguous pages. The checked physical pages were:

- Capgemini: 1, 2, 10, 13
- IAS: 2, 8, 33
- Julius Baer: 6, 7, 12, 13
- Mintel save-as-PDF artifact: 1

Among the seven checked mappings classified `verified` (Capgemini 2/10/13,
IAS 2/33, and Julius Baer 6/12), incorrect verified mappings were **0 / 7**.
The other five checked pages were intentionally unresolved or inferred: cover
pages without labels, Julius Baer page 7 with no visible footer, IAS page 8
whose footer number is embedded in a longer native text block, and Julius Baer
page 13 whose rendered number was not independently available as a short native
margin block. The conservative result keeps these separate from `verified`.

The review found and fixed one real false-positive pattern before the final
measurements: Capgemini physical page 10 contains a chart/card numeral `03` in
a long lower-page block next to the actual footer `10`. Weak standalone tokens
from blocks with more than two lines are now excluded, while the short footer
block remains verified. Repeated fresh runs produced the same mappings and the
same coverage statistics. The warm-cache path reused the MD5-bound JSON without
rewriting it.

## Limitations and Phase 2 hold

The pilot covers the four committed golden PDFs. The exact retained five-report
cohort referenced by the broader quality evidence was not available as a
complete retained-PDF set, so it was not substituted with a different cohort.
The manual denominator above is representative, not document-wide accuracy.
Image-only labels and labels unavailable as short native text remain unresolved
or bounded-inferred because Phase 1 deliberately has no OCR.

Phase 2 downstream adoption and duplicated-logic removal is **blocked pending
measured approval**. No existing evidence-pack or claim-validation consumer was
changed, and this Phase 1 JSON is not on a production default path.
