# PDF page reconciliation Phase 1 pilot

## Scope and implementation

This is the standalone Phase 1 pilot for final implementation commit
`764ddbaf3895298f203a10d396ede37b30e22f3c` (`pdf-page-reconciliation-v3`,
schema `1.1`). It maps one-based physical PDF pages to visible printed labels
using positioned native PDF text and bounded local sequence inference. It does
not call OCR, LLMs, File Search, vector stores, network services, report
processing, evidence-pack generation, claim validation, production caches,
checkpoints, or publication flows. The JSON output is written only by the
diagnostic runner to its explicit output directory and is not consumed by any
downstream producer.

The correction makes weak-label verification fail closed: a weak candidate must
belong to a signed ascending physical-page/printed-label sequence of at least
three stable-margin pages, or have an independent strong visible anchor. Two
weak labels cannot validate one another, descending sequences do not qualify,
and weak numbering restarts remain unresolved. Explicit `Page N`/`P. N`,
publisher copyright conventions, and valid Roman labels remain strong;
ambiguous prefixed and separator-trailing tokens require the same corroboration
rules. When a page has multiple weak candidates, only one candidate with a
unique compatible sequence may be selected. The final correction also fails
closed when a page has multiple distinct normalized labels and at least one is
strong: the page contributes no candidate to direct confirmation or sequence
corroboration. Strong and weak candidates for the same normalized label remain
compatible, and all-weak unique sequence disambiguation remains supported.

Every directly verified mapping now retains bounded source geometry: physical
page, extracted label line, visible header/footer band, the source text-block
bounding box, and `bounding_box_scope=text_block`. The scope is explicit so a
multiline block is never represented as an exact single-line box. Inferred
mappings retain only bounded sequence anchors. The schema remains `1.1`; the
algorithm is now `pdf-page-reconciliation-v3`, so stale v2 caches are rejected.

The runner was invoked with three forced fresh executions and one warm-cache
execution per PDF:

```powershell
python scripts/quality/reconcile_pdf_pages.py --pdf "<golden-pdf>" --output-dir "<temporary-diagnostic-directory>" --force
python scripts/quality/reconcile_pdf_pages.py --pdf "<golden-pdf>" --output-dir "<temporary-diagnostic-directory>"
```

The canonical JSON contains only source identity, schema/algorithm versions,
page mappings, bounded geometry/evidence, and coverage counts/percentages;
elapsed time is printed only in the runner summary. The three fresh JSON
outputs were byte-deterministic for every PDF. Their JSON SHA-256 identities
were:

| PDF | JSON SHA-256 after each of three fresh runs |
| --- | --- |
| `2026_Global_Food_and_Drink_Predictions.pdf` | `51caeae0746d87fdafaa6ae2364c966b4f380fc81c04aae10dc322958f3cb4b0` |
| `CAPGEMINI - 2026-Retail-Trends_ACIG.pdf` | `3592cef54d641a7a8eb0510a15b0cd277aedafa3d64f2e670b8396062feec0da` |
| `IAS - Industry_Pulse_Report_2026_ACIG.pdf` | `ccc987d13b67d45871800619d0702006bcfcf68505aefe94f86533f16b56a889` |
| `JULIUS BAER - Secular-outlook-2026_ACIG.pdf` | `3e57a41cba4e29515fe21f70962366bef00d44429eaf2d616c23ceda38d91126` |

## Committed golden PDFs and measurements

Source hashes were computed from the committed files under
`tests/fixtures/pdf_benchmark/golden/`. Fresh timings are the three final
forced-run CLI measurements; the median is the middle raw CLI measurement, not
the process-startup wall time. Peak RSS was sampled from the standalone runner
process with `psutil`; it is a practical process measurement, not a memory
limit or a claim about native-library peak allocation.

| PDF | SHA-256 | MD5 | Pages | Before V/I/U | After V/I/U | Fresh runs (ms) | Median (ms) | Warm cache (ms) | Peak RSS fresh/warm (MB) |
| --- | --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| `2026_Global_Food_and_Drink_Predictions.pdf` | `0d10fa30d4df83b8ec74a63db363b5bd98eb52497e5cc9a2300152d9713d6b16` | `b3cb5f66cccda4420be21b2b407b3c59` | 8 | 0/0/8 | 0/0/8 | 444.68, 247.13, 184.37 | 247.13 | 18.90 | 84.62/73.00 |
| `CAPGEMINI - 2026-Retail-Trends_ACIG.pdf` | `72a04abd394dfcb6b14288b97548669501e70c087eb6cee8bc8b9a66589cb0c7` | `c1cbe57c96a1d81476730e83828d07d9` | 15 | 12/0/3 | 13/0/2 | 66.33, 69.73, 72.82 | 69.73 | 19.24 | 76.69/73.51 |
| `IAS - Industry_Pulse_Report_2026_ACIG.pdf` | `8b05b13067748baebff51844a702a05dd6eb560706db5fa94b2ee5badbd672cd` | `fccf7f92dc7e14a27ee6a90daf16705a` | 33 | 31/1/1 | 26/2/5 | 708.84, 749.30, 687.33 | 708.84 | 28.01 | 86.88/72.90 |
| `JULIUS BAER - Secular-outlook-2026_ACIG.pdf` | `156032ae914753000d51085c5e1c6e2f2d4680b9d046bb18df6cefcb265ce193` | `468e8c08c83182f4803e07f5357c9160` | 36 | 26/2/8 | 26/2/8 | 203.72, 173.78, 308.04 | 203.72 | 32.71 | 77.89/73.60 |
| **Cohort total** |  |  | **92** | **69/3/20** | **65/4/23** |  |  |  |  |

The lower verified percentage is intentional. The corrected algorithm rejects
weak self-corroboration and avoids false verification even when that lowers
coverage. The Capgemini count increases from 12 to 13 only after resolving a
real conflict: physical page 12 contains chart-card numeral `04` and the
actual footer `12`; the unique `11 -> 12 -> 13` margin sequence selects `12`.
The final mixed strong/weak correction produced no mapping changes in this
four-PDF cohort.

## Rendered-page review

I rendered and inspected every mapping classified `verified` or `inferred`:
69 mappings across the four PDFs. The exact page identities were:

The final correction changed no mapping identity or status, so the rendered
review remains applicable without a new page-specific discrepancy.

- Capgemini: verified physical pages 2-14; unresolved 1 and 15.
- IAS: verified 2-7, 12-15, and 18-33; inferred 16 and 17; unresolved 1 and
  8-11.
- Julius Baer: verified 3-6, 8-12, and 14-30; inferred 7 and 13; unresolved
  1-2 and 31-36.
- Global Food and Drink: unresolved physical pages 1-8; no mapping was
  classified verified or inferred.

The manually measured outcomes are:

| Outcome | Denominator | Result |
| --- | ---: | --- |
| Verified labels matching the rendered page | 65 | **65 true positives, 0 false positives** |
| Inferred labels with no incorrect sequence result identified | 4 | **0 incorrect inferences** |
| Inferred labels with a visibly readable printed numeral | 2/4 | IAS physical pages 16 and 17; the numeral is embedded in a longer footer line |
| Inferred labels without a visible numeral to independently confirm | 2/4 | Julius Baer physical pages 7 and 13; anchors are compatible and the pages show no conflicting label |
| Unresolved physical pages | 23/92 | Intentional abstention for cover/image/layout pages or insufficient short native margin evidence |

The review covered front matter and cover pages, missing labels, section
transitions, misleading chart/card numerals, long footer blocks, and conflicting
labels. No incorrect verified mapping was found. The two Julius Baer inferred
pages are sequence-consistent but remain a residual limitation because the
rendered pages do not independently display their numerals.

## Validation and Phase 2 hold

Focused and affected downstream regressions passed:

```text
python -m pytest -q tests/test_pdf_page_reconciliation.py tests/test_pdf_text_service.py tests/test_pdf_contents_service.py tests/test_claim_validation_source_pages.py tests/_test_evidence_pack_generator/cases_05_findings_targeted_retrieval.py
64 passed

python -m pytest -q tests/test_pdf_page_reconciliation.py
28 passed

python -m pytest -q tests/contracts/test_contract_roundtrip.py
2351 passed

python -m ruff check src/contracts/pdf_page_reconciliation.py src/services/_pdf/page_reconciliation.py scripts/quality/reconcile_pdf_pages.py tests/test_pdf_page_reconciliation.py
python -m ruff format --check src/contracts/pdf_page_reconciliation.py src/services/_pdf/page_reconciliation.py scripts/quality/reconcile_pdf_pages.py tests/test_pdf_page_reconciliation.py
python -m mypy src/contracts/pdf_page_reconciliation.py src/services/_pdf/page_reconciliation.py scripts/quality/reconcile_pdf_pages.py
python scripts/ci/check_contract_schemas.py --snapshot docs/quality/contract_schemas.json
python scripts/ci/check_documentation.py --check-generated
```

The implementation has no new dependency, no LLM/provider call, no production
pipeline change, and no downstream consumer. The exact retained five-report
cohort referenced by broader quality evidence was not available as a complete
retained-PDF set, so it was not substituted with a different cohort. OCR,
image-label recovery, and generic scoring remain intentionally out of scope.

The four new regressions cover mixed strong/weak conflicts, exclusion of
conflicted pages from neighboring sequence corroboration, same-label strong
and weak candidates, and unique disambiguation among all-weak candidates.

Hosted CI run [39203836364](https://github.com/mbrakker/marketlense/actions/runs/39203836364)
passed on implementation SHA `764ddbaf3895298f203a10d396ede37b30e22f3c`.
It recorded 7,673 passing tests, 86.30% total coverage, both mutation
partitions passed, the PDF candidate benchmark passed, and release evidence
assembled successfully. The run also passed the architecture, service-boundary,
documentation, contract-schema, typing, and repository quality gates.

Phase 2 downstream adoption and duplicated-logic removal is **blocked pending
measured approval**. No existing evidence-pack or claim-validation consumer was
changed, and this Phase 1 JSON is not on a production default path.
