# PDF page reconciliation Phase 1 pilot

## Scope and implementation

This is the standalone Phase 1 pilot on implementation commit
`0f3bb5c3` (`pdf-page-reconciliation-v5`, schema `1.1`) in branch
`codex/pdf-page-reconciliation-deterministic-inference`. It maps one-based
physical PDF pages to visible printed labels using native PyMuPDF text and
bounded local sequence inference. It does not add OCR, vision, LLMs, network
calls, downstream consumers, production caches, checkpoints, or publication
flows.

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

No sequence gap, restart, boundary extrapolation, inference, or downstream
behavior changed.

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

## Validation and Phase 2 hold

TDD evidence:

```text
RED: python -m pytest -q tests/test_pdf_page_reconciliation.py -k "structured_footer or crossing_footer"
2 failed, 3 passed before the production change
GREEN: same focused selection
6 passed, 30 deselected
```

Local validation:

```text
python -m pytest -q tests/test_pdf_page_reconciliation.py
36 passed in 2.94s

python -m pytest -q tests/test_pdf_page_reconciliation.py tests/test_pdf_text_service.py tests/test_pdf_contents_service.py tests/test_claim_validation_source_pages.py tests/_test_evidence_pack_generator/cases_05_findings_targeted_retrieval.py
72 passed in 6.15s

python -m pytest -q tests/contracts/test_contract_roundtrip.py
2351 passed in 5.67s

python scripts/ci/check_contract_schemas.py --snapshot docs/quality/contract_schemas.json
python scripts/ci/check_architecture_imports.py
python scripts/ci/check_role_io_boundaries.py
python scripts/ci/check_service_boundary_map.py
python scripts/ci/check_documentation.py --check-generated
python -m ruff check src/services/_pdf/page_artifacts.py src/services/_pdf/page_reconciliation.py src/contracts/pdf_page_reconciliation.py tests/test_pdf_page_reconciliation.py
python -m ruff format --check src/services/_pdf/page_artifacts.py src/services/_pdf/page_reconciliation.py src/contracts/pdf_page_reconciliation.py tests/test_pdf_page_reconciliation.py
python -m mypy src/services/_pdf/page_artifacts.py src/services/_pdf/page_reconciliation.py src/contracts/pdf_page_reconciliation.py
git diff --check
```

All listed local commands passed. No dependency, service, external client,
prompt, downstream consumer, or Phase 2 workflow changed.

The authoritative v4 hosted test log for run `39210327978` reports
`4/4 workers [7675 items]` and `7675 passed in 460.04s`; the earlier `7699`
figure in the release summary was incorrect and is not used as the v4 test
count here. The final v5 hosted run will be recorded below after the pushed
implementation is checked on its exact SHA.

Hosted exact-SHA v5 evidence: pending final push.

Phase 2 downstream adoption and duplicated-logic removal remains **Blocked
pending measured approval**. Stop after this Phase 1 correction; do not change
existing consumers.
