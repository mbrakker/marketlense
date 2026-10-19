# PDF page reconciliation Phase 1 pilot

## Scope and implementation

This is the standalone Phase 1 pilot for implementation commit
8ad17d9076c503559cae5c9cc81d4dffd4bcf4c0 (pdf-page-reconciliation-v4,
schema 1.1). It maps one-based physical PDF pages to visible printed labels
using positioned native PDF text and bounded local sequence inference. It does
not call OCR, LLMs, File Search, vector stores, network services, report
processing, evidence-pack generation, claim validation, production caches,
checkpoints, or publication flows. The JSON output is written only by the
diagnostic runner to its explicit output directory and is not consumed by any
downstream producer.

The v3 fail-closed rules remain unchanged: a weak candidate must belong to a
signed ascending physical-page/printed-label sequence of at least three stable
margin pages, or have an independent strong visible anchor. Two weak labels
cannot validate one another, descending sequences do not qualify, and weak
numbering restarts remain unresolved. Explicit Page N/P. N, publisher
copyright conventions, and valid Roman labels remain strong; ambiguous
prefixed and separator-trailing tokens require the same corroboration rules.
When a page has multiple weak candidates, only one candidate with a unique
compatible sequence may be selected. A page with multiple distinct normalized
labels and at least one strong label contributes no candidate to direct
confirmation or sequence corroboration. Strong and weak candidates for the
same normalized label remain compatible, and all-weak unique sequence
disambiguation remains supported.

The v4 change is a narrow extraction correction for structured lower-page
footers. It reuses the existing extracted text-block pairs and recognizes a
footer line ending in REPORT | N, or a footer marker ending in | with exactly
one same-baseline numeric line to its right. The line must be in the existing
visible-footer band; the label must be a unique positive Arabic token and not
a year. A footer marker without a unique number remains unresolved. A
structured candidate is not added when the existing extractor already found
the same normalized label, so existing candidate provenance is preserved where
possible. No inference gap bound or boundary extrapolation rule changed.

Every directly verified mapping retains bounded source geometry: physical page,
extracted label line, visible header/footer band, source text-block bounding
box, and bounding_box_scope=text_block. The schema remains 1.1; the algorithm
is pdf-page-reconciliation-v4, so stale v3 caches are rejected.

## Diagnosis of all 23 baseline unresolved pages

The baseline was the pushed v3 output at 1687cc1: 65 verified, 4 inferred,
and 23 unresolved across the 92-page cohort. Each unresolved page was rendered
with its nearest verified or inferred neighbors and inspected at full-page and
footer/header resolution.

| Report | Physical page | Diagnosis | Recoverability |
| --- | ---: | --- | --- |
| Global Food and Drink | 1 | Cover/web landing page; no printed pagination visible | No |
| Global Food and Drink | 2 | Web landing/content page; no printed pagination visible | No |
| Global Food and Drink | 3 | Web landing/content page; no printed pagination visible | No |
| Global Food and Drink | 4 | Web landing/content page; no printed pagination visible | No |
| Global Food and Drink | 5 | Consulting/contact page; no printed pagination visible | No |
| Global Food and Drink | 6 | Analyst/contact page; no printed pagination visible | No |
| Global Food and Drink | 7 | Form/contact page; no printed pagination visible | No |
| Global Food and Drink | 8 | Closing web/contact page; no printed pagination visible | No |
| Capgemini | 1 | Cover page; no printed pagination visible | No |
| Capgemini | 15 | Closing cover page; no printed pagination visible | No |
| IAS | 1 | Report cover; no printed pagination visible | No |
| IAS | 8 | Footer label 8 visible, but merged with a long survey-question text block | Yes; structured footer extraction |
| IAS | 9 | Footer label 9 visible, but native block extraction suppresses the long footer block | Yes; structured footer extraction |
| IAS | 10 | Footer label 10 visible as a standalone token beside the footer marker; weak until neighboring labels are recovered | Yes; existing sequence corroboration |
| IAS | 11 | Footer label 11 visible, but merged with a long source/question text block | Yes; structured footer extraction |
| Julius Baer | 1 | Cover/marketing-material page; no printed pagination visible | No |
| Julius Baer | 2 | Front-matter image page; no printed pagination visible | No |
| Julius Baer | 31 | Photo/layout page; no printed pagination visible | No |
| Julius Baer | 32 | Standalone footer token 32 visible at a document boundary, but no independent two-sided corroboration | No; ambiguous boundary label |
| Julius Baer | 33 | Layout/photo page; no printed pagination visible | No |
| Julius Baer | 34 | Standalone footer token 34 visible at a document boundary, but no independent two-sided corroboration | No; ambiguous boundary label |
| Julius Baer | 35 | Section/legal layout page; no printed pagination visible | No |
| Julius Baer | 36 | Legal closing page; no printed pagination visible | No |

No longer interpolation or boundary extrapolation was justified. The only
recoverable unresolved cases were IAS pages 8-11. IAS pages 16-17 were also
visually inspected: their labels are visibly present in the same structured
footer pattern and were promoted from sequence-inferred to directly verified.
The Julius Baer 32/34 tokens were deliberately not promoted because the
document ends after an incomplete/ambiguous sequence and there are no two
direct anchors that establish continuity.

## Cohort comparison

Source hashes were computed from the committed files under
tests/fixtures/pdf_benchmark/golden/. V/I/U means verified/inferred/unresolved.

| PDF | SHA-256 | MD5 | Pages | Before V/I/U | After V/I/U | Fresh v4 runs (ms) | v4 median (ms) | v4 warm cache (ms) | v3 median/warm (ms) |
| --- | --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| 2026_Global_Food_and_Drink_Predictions.pdf | 0d10fa30d4df83b8ec74a63db363b5bd98eb52497e5cc9a2300152d9713d6b16 | b3cb5f66cccda4420be21b2b407b3c59 | 8 | 0/0/8 | 0/0/8 | 168.70, 170.42, 171.53 | 170.42 | 10.19 | 247.13/18.90 |
| CAPGEMINI - 2026-Retail-Trends_ACIG.pdf | 72a04abd394dfcb6b14288b97548669501e70c087eb6cee8bc8b9a66589cb0c7 | c1cbe57c96a1d81476730e83828d07d9 | 15 | 13/0/2 | 13/0/2 | 67.21, 67.27, 66.52 | 67.21 | 11.21 | 69.73/19.24 |
| IAS - Industry_Pulse_Report_2026_ACIG.pdf | 8b05b13067748baebff51844a702a05dd6eb560706db5fa94b2ee5badbd672cd | fccf7f92dc7e14a27ee6a90daf16705a | 33 | 26/2/5 | 32/0/1 | 593.83, 600.67, 589.51 | 593.83 | 27.59 | 708.84/28.01 |
| JULIUS BAER - Secular-outlook-2026_ACIG.pdf | 156032ae914753000d51085c5e1c6e2f2d4680b9d046bb18df6cefcb265ce193 | 468e8c08c83182f4803e07f5357c9160 | 36 | 26/2/8 | 26/2/8 | 137.04, 137.12, 137.86 | 137.12 | 26.94 | 203.72/32.71 |
| **Cohort total** |  |  | **92** | **65/4/23** | **71/2/19** |  |  |  |  |

The v4 change improved or preserved the status counts on every PDF. It did
not alter any printed label identity. IAS pages 8-11 changed from unresolved
to verified; IAS pages 16-17 changed from inferred to verified because the
rendered footer numerals were directly recovered. Existing IAS sequence
evidence anchors became longer where the newly recovered pages extended the
same verified sequence; no label or status outside those six IAS pages changed.
The fresh median and warm-cache measurements are no slower than the retained
v3 measurements for any PDF.

The three fresh v4 JSON outputs were byte-deterministic in separate output
directories. Their SHA-256 identities were:

| PDF | JSON SHA-256 |
| --- | --- |
| 2026_Global_Food_and_Drink_Predictions.pdf | 8334c9a6f955a6d97971c36bb0b292f5cf07ea5daceb9cdebe494e170e87bb16 |
| CAPGEMINI - 2026-Retail-Trends_ACIG.pdf | a1e9a72374896b9c3b36960eaf2691ec319405281e4e78f4c6abd684b18f6c20 |
| IAS - Industry_Pulse_Report_2026_ACIG.pdf | 042ae0e336bd52245b55d59a8b83b2f568530ca6975c7e525aedb78b870742ee |
| JULIUS BAER - Secular-outlook-2026_ACIG.pdf | 3c0fbb59082fe70ced53bf61529384709a2dd478a6fd3e511b7867c246a0ebef |

## Rendered-page review

The four newly recovered unresolved pages, IAS physical pages 8-11, were
rendered and inspected with pages 7 and 12 as surrounding anchors. Each shows
the expected visible footer label. Page 10 is the existing weak standalone
candidate; once pages 8, 9, and 11 are extracted, the unchanged local sequence
logic confirms 10. IAS physical pages 16 and 17 were also rendered with pages
14, 15, and 18; both visibly show footer labels 16 and 17, so direct
verification is now justified.

The retained Capgemini review remains valid: physical page 12 still shows the
actual footer 12, while chart card numeral 04 remains a misleading unrelated
number. The v4 parser does not change that mapping.

Final rendered outcomes:

| Outcome | Denominator | Result |
| --- | ---: | --- |
| Verified labels matching the rendered page | 71 | **71 true positives, 0 false positives** |
| Inferred labels with no incorrect sequence result identified | 2 | **0 incorrect inferences** |
| Remaining unresolved physical pages | 19/92 | Intentional abstention for unnumbered covers/layout pages or unsupported boundary labels |

The two remaining inferred labels are Julius Baer physical pages 7 and 13.
They are sequence-consistent and show no conflicting labels, but their rendered
pages do not independently display the numerals. No incorrect verified or
inferred mapping was identified.

## Validation and Phase 2 hold

TDD evidence:

~~~text
RED: python -m pytest -q tests/test_pdf_page_reconciliation.py -k "ias_footer_labels or footer_marker_without_unique"
1 failed, 1 passed, 28 deselected

GREEN: same focused selection
2 passed, 28 deselected
~~~

Focused and affected regressions passed:

Hosted exact-SHA CI evidence for 8ad17d9076c503559cae5c9cc81d4dffd4bcf4c0:

~~~text
https://github.com/mbrakker/marketlense/actions/runs/39208170106
7699 passed; pytest exit code 0; coverage 85907/99537 lines (86.31%)
17 mutation targets / 68 mutants / 67 killed; 2 mutation partitions passed
10/10 quality stages passed; PDF candidate benchmark passed
Release evidence passed: 11/11 required artifacts, 0 issues, 0 waivers
~~~

~~~text
python -m pytest -q tests/test_pdf_page_reconciliation.py
30 passed

python -m pytest -q tests/test_pdf_page_reconciliation.py tests/test_pdf_text_service.py tests/test_pdf_contents_service.py tests/test_claim_validation_source_pages.py tests/_test_evidence_pack_generator/cases_05_findings_targeted_retrieval.py
66 passed

python -m pytest -q tests/contracts/test_contract_roundtrip.py
2351 passed
~~~

Local quality gates passed:

~~~text
python scripts/ci/check_contract_schemas.py --snapshot docs/quality/contract_schemas.json
python scripts/ci/check_architecture_imports.py
python scripts/ci/check_role_io_boundaries.py
python scripts/ci/check_service_boundary_map.py
python -m ruff check src/contracts/pdf_page_reconciliation.py src/services/_pdf/page_reconciliation.py scripts/quality/reconcile_pdf_pages.py tests/test_pdf_page_reconciliation.py
python -m ruff format --check src/contracts/pdf_page_reconciliation.py src/services/_pdf/page_reconciliation.py scripts/quality/reconcile_pdf_pages.py tests/test_pdf_page_reconciliation.py
python -m mypy src/contracts/pdf_page_reconciliation.py src/services/_pdf/page_reconciliation.py scripts/quality/reconcile_pdf_pages.py
~~~

No new dependency, LLM/provider call, production pipeline change, or downstream
consumer was added. OCR, image-label recovery, boundary extrapolation, longer
gap interpolation, and generic scoring remain intentionally out of scope.

The feature branch is codex/pdf-page-reconciliation-deterministic-inference.
The code commit is 8ad17d9076c503559cae5c9cc81d4dffd4bcf4c0. Hosted CI run
39208170106 passed on that exact SHA with 7699 tests, 86.31% coverage,
17/68/67 mutation results, all ten quality stages, and 11/11 release-evidence
artifacts with zero issues or waivers. Phase 2 downstream adoption and
duplicated-logic removal remains blocked pending measured approval. No
existing evidence-pack, claim-validation, DocMap, orchestrator, or publication
consumer changed.
