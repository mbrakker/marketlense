# PDF page reconciliation Phase 1 pilot

## Scope and implementation

This is the standalone Phase 1 pilot on the current deterministic candidate
(`pdf-page-reconciliation-v6`, schema `1.1`) in branch
`codex/pdf-page-reconciliation-deterministic-inference`. It maps one-based
physical PDF pages to visible printed labels using native PyMuPDF text and
bounded local sequence inference. It does not add OCR, vision, LLMs, network
calls, downstream consumers, production caches, checkpoints, or publication
flows. The v5 implementation and its exact-SHA verification head
`9c80a2f6204022248bbd6ef390692242870a3b1b` remain the comparison baseline for
the recovery documented below.

The v5 change is a correctness fix for structured lower-page footers. The
previous helper split a text block into lines but assigned the containing block
bbox to every line. The footer-region check therefore treated body lines in a
large multiline block as footer lines, and numeric matching used block geometry
instead of the marker and number line geometry. A same-number weak candidate
could also be retained instead of the stronger structured-footer candidate.

The correction reuses one native `get_text("dict")` artifact per page and keeps
both the actual line bbox and containing block bbox. Generic margin parsing and
structured-footer parsing now use line geometry for the margin band. Structured
marker/number matching requires a footer-band line, a unique positive Arabic
label, no 1900–2100 year, numeric line `x0` to the right of marker `x1`, and
bottom-edge baseline difference no greater than 3.5 points. `REPORT | N` remains
valid on one line. A structured strong candidate replaces a same-number weak
candidate; unrelated or ambiguous candidates remain unresolved. Persisted
source geometry remains the containing text block with
`bounding_box_scope=text_block`; schema `1.1` is unchanged. The algorithm
version moved from v4 to v5, invalidating v4 caches.

The v6 recovery is deliberately narrower than a general sequence fallback: it
normalizes only a complete margin line whose `U+FFFC`/`U+FFFD` extraction
artifact directly prefixes an Arabic page token. That artifact is retained as
a strong direct-evidence signal, including when the containing text block also
contains source notes. A non-complete artifact-prefixed margin line is treated
as an unresolved conflict and cannot be directly confirmed or sequence-inferred;
ordinary copyright footers remain on the existing parser path. The algorithm
version moved from v5 to v6, invalidating v5 caches. No downstream behavior
changed.

## Native geometry evidence

The IAS fixture is a genuine PDF with mixed native grouping. All values below
are PyMuPDF line bboxes; page height is 405 points and the footer threshold is
`y0 / height >= 0.86`.

| Page | Marker line bbox | Number line bbox | Containing block evidence |
| ---: | --- | --- | --- |
| 8 | `(561.13, 378.35, 681.83, 387.17)` | `(687.36, 378.39, 691.21, 387.21)` | Number is in a multiline body block `(72.89, 375.43, 691.21, 390.19)`; bottom-edge delta `0.04`, number is right of marker |
| 9 | `(561.13, 378.35, 691.21, 387.21)` with `| 9` | — | Footer line is inside multiline block `(72.89, 375.43, 691.21, 390.19)` |
| 10 | `(561.13, 378.35, 681.83, 387.17)` | `(684.19, 378.39, 691.21, 387.21)` | Same containing footer block; bottom-edge delta `0.04`, number is right of marker |
| 11 | `(561.13, 378.35, 691.21, 387.21)` with `| 11` | — | Footer line is inside multiline block `(72.89, 375.43, 691.21, 390.19)` |
| 16 | `(561.13, 378.35, 691.21, 387.21)` with `| 16` | — | Footer line is inside multiline block `(72.89, 375.43, 691.21, 390.19)` |
| 17 | `(561.13, 378.35, 691.21, 387.21)` with `| 17` | — | Footer line is inside multiline block `(72.89, 375.43, 691.21, 390.19)` |

This confirms that native block grouping cannot safely substitute for line
geometry: page 8's printed number shares a block with body questions, while
pages 9, 11, 16, and 17 have footer lines merged into multiline blocks and
page 10 splits marker and number into separate lines in one block.

## Diagnosis and recoverability

The original v3 cohort had 23 unresolved pages. The v4 correction recovered IAS
8–11 and promoted IAS 16–17, leaving 19 intentionally unresolved pages. v5
does not increase coverage; it makes the evidence for structured labels direct
and prevents the remaining geometry false-positive class.

| Report | Physical pages | Diagnosis | Decision |
| --- | --- | --- | --- |
| Global Food and Drink | 1–8 | Covers, web/content, contact, and closing pages without printed pagination | Remain unresolved |
| Capgemini | 1, 15 | Cover and closing cover without printed pagination | Remain unresolved |
| IAS | 1 | Report cover without printed pagination | Remain unresolved |
| IAS | 8–11 | Visible structured footer labels recovered from native line geometry | Verified; no status change from v4 |
| IAS | 16–17 | Visible structured footer labels already promoted by v4 and rechecked | Verified; no status change |
| Julius Baer | 1–2 | Cover/front matter without printed pagination | Remain unresolved |
| Julius Baer | 31, 33, 35–36 | Photo/layout/legal pages without printed pagination | Remain unresolved |
| Julius Baer | 32, 34 | Standalone boundary tokens without two-sided independent anchors | Remain unresolved |

The v5 synthetic genuine-PDF tests additionally cover: valid same-baseline
marker/number blocks, different-line rejection within one block, body numbers
in a crossing multiline block, multiple numeric candidates, left-of-marker
ordering, missing numbers, explicit `REPORT | N`, and mixed strong/weak
fail-closed conflicts. Existing tests retain IAS 8–11/16–17 verification and
Capgemini physical page 12 as label 12 rather than chart numeral 04.

The six new geometry regressions live in the dedicated
`tests/test_pdf_page_reconciliation_geometry.py` module so the repository's
first-party test-file ownership threshold remains satisfied.

## Golden-PDF cohort and changed mappings

Source hashes are from the committed files under
`tests/fixtures/pdf_benchmark/golden/`. V/I/U means verified/inferred/unresolved.

| PDF | SHA-256 | MD5 | Pages | v4 V/I/U | v5 V/I/U | Fresh v5 runs (ms) | v5 median (ms) | v5 warm (ms) | v4 median/warm (ms) |
| --- | --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| 2026_Global_Food_and_Drink_Predictions.pdf | `0d10fa30d4df83b8ec74a63db363b5bd98eb52497e5cc9a2300152d9713d6b16` | `b3cb5f66cccda4420be21b2b407b3c59` | 8 | 0/0/8 | 0/0/8 | 185.53, 171.27, 171.46 | 171.46 | 16.39 | 170.42/10.19 |
| CAPGEMINI - 2026-Retail-Trends_ACIG.pdf | `72a04abd394dfcb6b14288b97548669501e70c087eb6cee8bc8b9a66589cb0c7` | `c1cbe57c96a1d81476730e83828d07d9` | 15 | 13/0/2 | 13/0/2 | 75.38, 73.65, 68.59 | 73.65 | 16.95 | 67.21/11.21 |
| IAS - Industry_Pulse_Report_2026_ACIG.pdf | `8b05b13067748baebff51844a702a05dd6eb560706db5fa94b2ee5badbd672cd` | `fccf7f92dc7e14a27ee6a90daf16705a` | 33 | 32/0/1 | 32/0/1 | 687.30, 627.04, 587.15 | 627.04 | 42.38 | 593.83/27.59 |
| JULIUS BAER - Secular-outlook-2026_ACIG.pdf | `156032ae914753000d51085c5e1c6e2f2d4680b9d046bb18df6cefcb265ce193` | `468e8c08c83182f4803e07f5357c9160` | 36 | 26/2/8 | 26/2/8 | 148.93, 151.12, 159.34 | 151.12 | 30.50 | 137.12/26.94 |
| **Cohort total** |  |  | **92** | **71/2/19** | **71/2/19** |  |  |  |  |

The v5 change preserves every printed label, status, and method across the
cohort. Fifteen IAS mappings changed only in evidence provenance:
physical pages `2–7, 10, 12–15, 18–31` now use direct structured-footer
evidence without v4 weak-sequence anchors. IAS 8, 9, 11, 16, and 17 were
already direct in v4 and remain unchanged; IAS 10 is now direct rather than
sequence-supported. Source block geometry remains identical in scope and
contract shape. No Global, Capgemini, or Julius mapping changed.

The v4 JSON hashes were:

| PDF | v4 JSON SHA-256 |
| --- | --- |
| Global | `8334c9a6f955a6d97971c36bb0b292f5cf07ea5daceb9cdebe494e170e87bb16` |
| Capgemini | `a1e9a72374896b9c3b36960eaf2691ec319405281e4e78f4c6abd684b18f6c20` |
| IAS | `042ae0e336bd52245b55d59a8b83b2f568530ca6975c7e525aedb78b870742ee` |
| Julius | `3c0fbb59082fe70ced53bf61529384709a2dd478a6fd3e511b7867c246a0ebef` |

The three final forced v5 runs per PDF produced byte-identical JSON. The v5
JSON SHA-256 identities are:

| PDF | v5 JSON SHA-256 |
| --- | --- |
| Global | `74c51b5def3bd499f5737dadd37251d145568713722793035f62e80a516aa7ec` |
| Capgemini | `13a3466c414b8a8a2b63610a9bc861b468f2297b7b995cb6f199796a9951cfb2` |
| IAS | `0b616b862fb74d4eb00ab465def21a136c09cbc74c48e3b616d137648cf7e79b` |
| Julius | `b244f50d75e41564c2b86b8ed82f569802bf1b2e2e89dce586063ff93e0d8e62` |

The line-record pass adds measurable local work: fresh medians range from
`+0.6%` to `+10.2%` versus the retained v4 medians, and warm runs remain below
`43 ms`. No performance optimization is claimed; this is an accuracy-first
correction with bounded runtime cost.

## Rendered-page review

Rendered full pages and footer strips were inspected for the changed IAS
pattern, including pages 8–11 and 16–17. The footer marker and printed number
are visibly aligned on the rendered pages. IAS p10 shows the footer `10`, and
IAS p16/p17 show `16`/`17`. Capgemini p12 visibly shows footer `12`; the large
chart numeral `04` is not used as a page label. The 71 verified outcomes are
71 rendered true positives with 0 false positives. The 2 inferred Julius
labels (physical pages 7 and 13) remain sequence-supported but not visibly
independent. No incorrect inference was identified.

## Frozen 20-report cohort validation

The existing frozen cohort at
`scripts/quality/frozen_reliability_cohort_20.json` was evaluated without
running the broader frozen-reliability workflow. All 20 canonical source paths
resolved locally, all 20 paths were unique, and every PDF MD5 matched the
frozen `content_md5`; no member was substituted or unavailable. The matrix used
the same source bytes for v4 baseline commit `fe0f26e` and v5 candidate commit
`aed19aa`. Raw JSON outputs and rendered contact sheets were retained outside
Git under the temporary evaluation root; no PDFs or bulky images were added to
the repository.

V/I/U means verified/inferred/unresolved. Fresh columns are the median of three
forced executions in milliseconds; warm columns are the valid cache-hit run
against the third fresh output directory.

| # | Report identity | Frozen MD5 | Pages | v4 V/I/U | v5 V/I/U | v4 fresh / warm ms | v5 fresh / warm ms |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | Final Web Version Report Consumer Trends 2026 | `81af3890cd84ece81ef16e1aabda8027` | 82 | 80/0/2 | 80/0/2 | 1888.58 / 50.73 | 1908.23 / 39.15 |
| 2 | Activate `d8ca0bf6efb9c703343867f6df0f26a2553aa78f` | `cbb6e7df67412186b8bc094a424ac890` | 140 | 0/0/140 | 0/0/140 | 4845.64 / 286.39 | 4896.66 / 33.92 |
| 3 | DV QualityandAttentionBenchmark Q1 2026 | `e854b71d6fb10333b47fd518a6e51cf9` | 12 | 12/0/0 | 12/0/0 | 382.43 / 19.79 | 433.22 / 10.32 |
| 4 | 2026 Global M&A Outlook | `2acb4a56e14add5d7717f34c378f9091` | 42 | 40/0/2 | 40/0/2 | 1319.11 / 30.28 | 1530.34 / 22.50 |
| 5 | Trends and Predictions 2026 | `4b763ae2286ca69fe8acb63b17508dfb` | 47 | 45/0/2 | 45/0/2 | 440.57 / 34.96 | 397.23 / 25.38 |
| 6 | 2026 global payments and fraud report | `11b0b55157f7d0636815ad72435e1cf5` | 4 | 0/0/4 | 0/0/4 | 179.21 / 8.72 | 167.44 / 6.08 |
| 7 | mobile-app-trends-2026-pdf | `b638414df0b1fccea1cd8a93eaf8f5aa` | 41 | 39/0/2 | 39/0/2 | 192.52 / 26.98 | 211.74 / 21.36 |
| 8 | Algolia `2026%20B2C%20ecommerce%20AI%20trends eBook EN 2` | `86858bdcb370266f26c29b40316a4db0` | 29 | 0/0/29 | 0/0/29 | 769.35 / 37.66 | 776.47 / 25.65 |
| 9 | How to win with tech | `77bc67b2bc98187d9d589a4e69fd85f7` | 1 | 0/0/1 | 0/0/1 | 185.74 / 8.26 | 169.23 / 5.23 |
| 10 | ebook 0225 future commerce new modes guide en us | `0a019f840c3f89ad0a9672e058d1ff83` | 10 | 0/0/10 | 0/0/10 | 230.22 / 19.57 | 236.54 / 12.36 |
| 11 | The Advertiser Guide to New and Emerging Channels for 2023 | `979a63a1633a7f2ccc5123540a079d79` | 9 | 8/0/1 | 8/0/1 | 73.68 / 10.10 | 74.57 / 8.47 |
| 12 | q1 2026 emerging retail and consumer trends | `b10ed6c82b76739a806a9f10ec0b9723` | 11 | 9/0/2 | 9/0/2 | 343.38 / 16.36 | 350.82 / 12.31 |
| 13 | g0 ec trends report 2026 | `9b97626fc83c086961a7416d65e05faa` | 78 | 74/2/2 | 74/2/2 | 1676.91 / 53.88 | 1770.06 / 43.99 |
| 14 | EMPLIFI Digital Authenticity AI 2026 | `f62048b469dd784e6e7c0349c8b92f9b` | 21 | 19/0/2 | 19/0/2 | 570.14 / 27.87 | 570.01 / 18.25 |
| 15 | EX Trends AMR 020326 | `fb16d52bb8f60827077c38d6c3f22607` | 31 | 30/0/1 | 30/0/1 | 491.29 / 27.52 | 489.77 / 21.42 |
| 16 | Retail Marketing Trends: How To Win in 2026 | `8ef1021c332aa85ba008da58ff8ec866` | 22 | 21/0/1 | 21/0/1 | 365.86 / 26.64 | 363.04 / 18.67 |
| 17 | docu 202601 active ownership report q4 en | `5ceb3b4498de7288ce5a42546d137262` | 30 | 29/0/1 | 29/0/1 | 772.37 / 20.71 | 786.77 / 17.39 |
| 18 | attachment The Sales Signals Playbook 4 | `f1652970000cfe246c944412e0b1e4fe` | 11 | 11/0/0 | 11/0/0 | 593.09 / 12.27 | 589.91 / 11.55 |
| 19 | 2026 Global Connected Consumer Trends Report | `076eca6d31e0c1dcddf0f991b3000b40` | 21 | 0/0/21 | 0/0/21 | 121.41 / 14.18 | 130.51 / 14.12 |
| 20 | 2026 Global Food and Drink Predictions | `b3cb5f66cccda4420be21b2b407b3c59` | 8 | 0/0/8 | 0/0/8 | 171.18 / 8.22 | 171.12 / 7.80 |
| **Total** | **20 reports** |  | **650** | **417/2/231** | **417/2/231** |  |  |

The historical v5 cohort aggregate is 417 verified (`64.15%`), 2 inferred
(`0.31%`), and 231 unresolved (`35.54%`). The mutually exclusive unresolved
classification is 13 conflict pages, 2 native-metadata pages, and 216
no-visible-label pages. The raw evidence-kind counts were 13 conflict, 2
native metadata, and 218 `no_visible_label` records because the two metadata
pages also carry `no_visible_label` evidence. Every response contains exactly
one mapping for each physical page. All 40 fresh v4/v5 response sets passed schema `1.1`,
algorithm-version, input-MD5, filename-MD5, and page-completeness checks.
Each report produced byte-identical JSON across its three fresh runs. The
corrected warm rerun produced 40/40 cache hits, 20 for each version; the first
warm attempt used separate empty directories and was discarded as invalid cache
evidence.

The v5 aggregate fresh median was `415.23 ms` versus v4 `403.74 ms` (+2.85%).
The valid warm medians were `17.82 ms` for v5 and `23.68 ms` for v4. Two small
reports had relative fresh increases above 10% (DV +13.28%, +50.79 ms; M&A
16.01%, +211.23 ms); the cohort-level absolute overhead is bounded and no
material reliability or runtime regression was observed. No performance
optimization is claimed.

Accepted labels were decimal only: no Roman or prefixed labels were accepted.
All verified numeric labels have physical-page offset `0` except Reuters
physical pages 3–47, which visibly carry printed labels 1–45 (offset `-2`).
No numbering restart was inferred. The two inferred mappings are DHL physical
pages 49 and 60; both rendered pages visibly show the proposed footer labels,
but they remain sequence-supported rather than promoted to direct verification.
The 13 conflict pages and two native-metadata pages remain unresolved. In
particular, DHL physical page 27 visibly contains footer `27` alongside `X`,
and Contentstack physical pages 4 and 10–20 contain competing footer labels;
none was promoted.

The v4/v5 page-level comparison found zero changed label identities, statuses,
methods, evidence records, or source geometry across all 650 pages. Therefore
there were no changed mappings requiring a correction classification; the
classification set is empty. The rendered v5 contact-sheet review covered all
419 verified/inferred mappings and all 15 unresolved pages with visible,
conflicting, or metadata evidence. The remaining 216 mutually exclusive
no-visible-label pages were not individually rendered; the raw
`no_visible_label` count was 218 because it overlapped the two metadata pages.
No
incorrect verified or inferred mapping was identified in the inspected
denominator. This is a bounded page-label accuracy statement, not a claim that
every no-visible-label page has been exhaustively hand-reviewed.

The four committed golden-PDF regressions remain unchanged at 71 verified, 2
inferred, and 19 unresolved; their earlier rendered review and geometry
evidence remain in this document. The 20-report cohort adds real source
diversity and confirms fail-closed abstention on conflicts, but it does not
replace the IAS-specific geometry fixtures.

**20-report evaluation verdict: PASS for v5 detection, inference, and
abstention within the stated visual-review denominator. Phase 2 approval
remains blocked; no downstream integration is authorized.**

## Deterministic unresolved-page recovery (v6 candidate)

The v6 candidate was evaluated against the same 20 frozen PDFs and the same
650 source pages. All 20 frozen MD5 values matched; no PDF was substituted.
The only recoverable defect was in Activate: physical pages 2–139 visibly
carry labels 1–138, but PyMuPDF exposed the marked-content `ActualText`
prefix (`U+FFFC`) immediately before each numeric glyph. The v6 change removes
that artifact only when it prefixes a valid margin page token and promotes
that artifact-prefixed token to strong direct footer evidence. It does not
infer a label from page position alone.

| # | Report | Pages | v5 V/I/U | v6 V/I/U | Changed pages |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | Final Web Version Report Consumer Trends 2026 | 82 | 80/0/2 | 80/0/2 | 0 |
| 2 | Activate | 140 | 0/0/140 | 138/0/2 | 138 |
| 3 | DV QualityandAttentionBenchmark Q1 2026 | 12 | 12/0/0 | 12/0/0 | 0 |
| 4 | 2026 Global M&A Outlook | 42 | 40/0/2 | 40/0/2 | 0 |
| 5 | Trends and Predictions 2026 | 47 | 45/0/2 | 45/0/2 | 0 |
| 6 | 2026 global payments and fraud report | 4 | 0/0/4 | 0/0/4 | 0 |
| 7 | mobile-app-trends-2026-pdf | 41 | 39/0/2 | 39/0/2 | 0 |
| 8 | Algolia | 29 | 0/0/29 | 0/0/29 | 0 |
| 9 | How to win with tech | 1 | 0/0/1 | 0/0/1 | 0 |
| 10 | ebook 0225 future commerce new modes guide en us | 10 | 0/0/10 | 0/0/10 | 0 |
| 11 | The Advertiser Guide to New and Emerging Channels for 2023 | 9 | 8/0/1 | 8/0/1 | 0 |
| 12 | q1 2026 emerging retail and consumer trends | 11 | 9/0/2 | 9/0/2 | 0 |
| 13 | DHL eCommerce | 78 | 74/2/2 | 74/2/2 | 0 |
| 14 | EMPLIFI Digital Authenticity AI 2026 | 21 | 19/0/2 | 19/0/2 | 0 |
| 15 | EX Trends AMR 020326 | 31 | 30/0/1 | 30/0/1 | 0 |
| 16 | Retail Marketing Trends: How To Win in 2026 | 22 | 21/0/1 | 21/0/1 | 0 |
| 17 | docu 202601 active ownership report q4 en | 30 | 29/0/1 | 29/0/1 | 0 |
| 18 | attachment The Sales Signals Playbook 4 | 11 | 11/0/0 | 11/0/0 | 0 |
| 19 | Contentstack | 21 | 0/0/21 | 0/0/21 | 0 |
| 20 | Mintel | 8 | 0/0/8 | 0/0/8 | 0 |
| **Total** | **20 reports** | **650** | **417/2/231** | **555/2/93** | **138** |

The v6 unresolved pages are mutually exclusive: 13 conflicts, 2 native PDF
metadata pages, and 78 pages with no visible label. The two metadata pages
also retain `no_visible_label` as a second evidence record. Activate physical
pages 1 and 140 remain unresolved because they have no printed label. DHL is
unchanged: physical page 27 remains a conflict beside the `X` marks, physical
page 1 has no visible label, and physical pages 49 and 60 remain inferred.

The remaining named blockers are intentional. Algolia's visible multi-digit
footer suffixes use vector artwork for the second digit, so text extraction
does not provide a safe complete token and no OCR/vision fallback is allowed.
Contentstack places two logical page labels on each physical spread (for
example `04/05`), so one-label-per-physical-page reconciliation would invent
an assignment. Mintel's eight pages have no visible pagination. These pages
remain unresolved rather than being mathematically extrapolated.

All 138 new Activate mappings were rendered in six footer contact sheets and
visually inspected; every physical page 2–139 shows the matching visible
footer number 1–138, including the pages whose footer shares a source-note
text block. No existing 20-report mapping changed, and no false positive was
identified. The four committed golden PDFs remain exactly 71 verified, 2
inferred, and 19 unresolved: v6 JSON matches v5 byte-for-byte after removing
only the algorithm-version field, with no label, status, method, evidence, or
geometry changes.

Three forced v6 outputs per report were byte-identical and the valid warm run
produced 20/20 cache hits. The final corrected v6 run's median of per-report
fresh medians was `440.11 ms` versus `415.23 ms` for v5. Valid warm-cache median was
`28.66 ms` for v6 versus `17.82 ms` for v5; the absolute difference was
`10.84 ms`, and no performance optimization is claimed.

**v6 recovery verdict: PASS for the deterministic Activate recovery and
fail-closed abstention on Algolia, Contentstack, Mintel, and DHL edge cases.
Phase 2 remains blocked pending measured approval; no downstream integration
is authorized.**

## Validation and Phase 2 hold

TDD evidence:

```text
RED: python -m pytest -q tests/test_pdf_page_reconciliation.py -k replacement_character_prefixed_footer_labels
1 failed, 30 deselected before the production change
GREEN: python -m pytest -q tests/test_pdf_page_reconciliation.py -k replacement_character_prefixed_footer_labels
1 passed, 30 deselected
SAFETY RED: python -m pytest -q tests/test_pdf_page_reconciliation.py -k replacement_character
2 failed, 1 passed before the safety correction
SAFETY GREEN: python -m pytest -q tests/test_pdf_page_reconciliation.py -k replacement_character
4 passed
FINAL SAFETY EDGE GREEN: python -m pytest -q tests/test_pdf_page_reconciliation_marked_content_safety.py
1 passed
```

Local validation:

```text
python -m pytest -q tests/test_pdf_page_reconciliation.py tests/test_pdf_page_reconciliation_geometry.py
37 passed in 3.06s

python -m pytest -q tests/test_pdf_page_reconciliation.py tests/test_pdf_page_reconciliation_marked_content_safety.py tests/test_pdf_page_reconciliation_geometry.py tests/test_pdf_text_service.py tests/test_pdf_contents_service.py tests/test_claim_validation_source_pages.py tests/_test_evidence_pack_generator/cases_05_findings_targeted_retrieval.py
77 passed in 6.88s

python -m pytest -q tests/contracts/test_contract_roundtrip.py
2351 passed in 8.70s

python scripts/ci/check_contract_schemas.py --snapshot docs/quality/contract_schemas.json
python scripts/ci/check_architecture_imports.py
python scripts/ci/check_role_io_boundaries.py
python scripts/ci/check_service_boundary_map.py
python scripts/ci/check_documentation.py --check-generated
python -m ruff check src/services/_pdf/page_artifacts.py src/services/_pdf/page_reconciliation.py src/contracts/pdf_page_reconciliation.py tests/test_pdf_page_reconciliation.py tests/test_pdf_page_reconciliation_geometry.py
python -m ruff format --check src/services/_pdf/page_artifacts.py src/services/_pdf/page_reconciliation.py src/contracts/pdf_page_reconciliation.py tests/test_pdf_page_reconciliation.py tests/test_pdf_page_reconciliation_geometry.py
python -m mypy src/services/_pdf/page_artifacts.py src/services/_pdf/page_reconciliation.py src/contracts/pdf_page_reconciliation.py
git diff --check
```

All listed local commands passed. No dependency, service, external client,
prompt, downstream consumer, or Phase 2 workflow changed.

The authoritative v4 hosted test log for run `39210327978` reports
`4/4 workers [7675 items]` and `7675 passed in 460.04s`; the earlier `7699`
figure in the release summary was incorrect and is not used as the v4 test
count here. The final v5 hosted run
[`39216527888`](https://github.com/mbrakker/marketlense/actions/runs/39216527888)
passed on exact SHA
`9c80a2f6204022248bbd6ef390692242870a3b1b`: `7681 passed in 433.60s`,
global coverage `86.31%` (`85932/99564`), and all configured coverage gates
passed. Both mutation partitions passed with 17 targets, 68 mutants, and 67
killed (98.53%). The ten quality-command stages passed, and the release
manifest/review passed all 11 required artifacts with 0 issues and 0 waivers.
The conditional WordPress staging REST gate was skipped because it was not
configured for this push. An earlier v5 attempt
([`39215380878`](https://github.com/mbrakker/marketlense/actions/runs/39215380878))
failed only the first-party test-file ownership threshold after the six new
geometry tests were initially placed in the existing module; the tests were
moved to the dedicated module above and the exact-SHA rerun passed.

Hosted exact-SHA v5 evidence: passed; release evidence ID `39216527888-1`.

Phase 2 downstream adoption and duplicated-logic removal remains **Blocked
pending measured approval**. Stop after this Phase 1 correction; do not change
existing consumers.
