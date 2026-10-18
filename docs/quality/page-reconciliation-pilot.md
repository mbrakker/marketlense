# PDF page reconciliation Phase 1 pilot

## Scope and implementation

This is the standalone Phase 1 pilot for final implementation commit
`4c3427c7b72eb2eb52ce577490510d00f159368f` (`pdf-page-reconciliation-v2`,
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
unique compatible sequence may be selected.

Every directly verified mapping now retains bounded source geometry: physical
page, extracted label line, visible header/footer band, the source text-block
bounding box, and `bounding_box_scope=text_block`. The scope is explicit so a
multiline block is never represented as an exact single-line box. Inferred
mappings retain only bounded sequence anchors. The persisted schema and
algorithm versions were advanced so old caches are rejected.

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
| `2026_Global_Food_and_Drink_Predictions.pdf` | `e3f5aee8bea7930284ee91a6d64d545c7ad362adb556de688bcb2f1909a7c75c` |
| `CAPGEMINI - 2026-Retail-Trends_ACIG.pdf` | `e3bcf304e0367ed9e8fe945501d2f638b221073c3ed403515e2f2bf4397c44a8` |
| `IAS - Industry_Pulse_Report_2026_ACIG.pdf` | `b7ab6a1e395643026f3693ab5109a8342c5d6f1cacb8200b6c6edbbbafee9e7f` |
| `JULIUS BAER - Secular-outlook-2026_ACIG.pdf` | `7ec94cabb605a1d20058c116cf5302f6ddd234f6df07169d5ea64ed825dafe06` |

## Committed golden PDFs and measurements

Source hashes were computed from the committed files under
`tests/fixtures/pdf_benchmark/golden/`. Fresh timings are the three final
forced-run CLI measurements; the median is the middle raw CLI measurement, not
the process-startup wall time. Peak RSS was sampled from the standalone runner
process with `psutil`; it is a practical process measurement, not a memory
limit or a claim about native-library peak allocation.

| PDF | SHA-256 | MD5 | Pages | Before V/I/U | After V/I/U | Fresh runs (ms) | Median (ms) | Warm cache (ms) | Peak RSS fresh/warm (MB) |
| --- | --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| `2026_Global_Food_and_Drink_Predictions.pdf` | `0d10fa30d4df83b8ec74a63db363b5bd98eb52497e5cc9a2300152d9713d6b16` | `b3cb5f66cccda4420be21b2b407b3c59` | 8 | 0/0/8 | 0/0/8 | 214.21, 241.63, 216.60 | 216.60 | 10.75 | 84.66/73.03 |
| `CAPGEMINI - 2026-Retail-Trends_ACIG.pdf` | `72a04abd394dfcb6b14288b97548669501e70c087eb6cee8bc8b9a66589cb0c7` | `c1cbe57c96a1d81476730e83828d07d9` | 15 | 12/0/3 | 13/0/2 | 71.60, 65.32, 64.70 | 65.32 | 17.23 | 76.68/73.22 |
| `IAS - Industry_Pulse_Report_2026_ACIG.pdf` | `8b05b13067748baebff51844a702a05dd6eb560706db5fa94b2ee5badbd672cd` | `fccf7f92dc7e14a27ee6a90daf16705a` | 33 | 31/1/1 | 26/2/5 | 589.35, 616.71, 654.85 | 616.71 | 25.71 | 87.12/73.01 |
| `JULIUS BAER - Secular-outlook-2026_ACIG.pdf` | `156032ae914753000d51085c5e1c6e2f2d4680b9d046bb18df6cefcb265ce193` | `468e8c08c83182f4803e07f5357c9160` | 36 | 26/2/8 | 26/2/8 | 144.98, 134.66, 134.26 | 134.66 | 26.81 | 78.97/73.32 |
| **Cohort total** |  |  | **92** | **69/3/20** | **65/4/23** |  |  |  |  |

The lower verified percentage is intentional. The corrected algorithm rejects
weak self-corroboration and avoids false verification even when that lowers
coverage. The Capgemini count increases from 12 to 13 only after resolving a
real conflict: physical page 12 contains chart-card numeral `04` and the
actual footer `12`; the unique `11 -> 12 -> 13` margin sequence selects `12`.

## Rendered-page review

I rendered and inspected every mapping classified `verified` or `inferred`:
69 mappings across the four PDFs. The exact page identities were:

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
60 passed

python -m pytest -q tests/contracts/test_contract_roundtrip.py
2375 passed

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

Hosted CI run [39171924785](https://github.com/mbrakker/marketlense/actions/runs/39171924785)
passed on the final implementation SHA. It recorded 7,669 passing tests,
86% total coverage, both mutation partitions passed, the PDF candidate
benchmark passed, and release evidence assembled successfully. The run also
passed the architecture, service-boundary, documentation, contract-schema,
typing, and repository quality gates.

Phase 2 downstream adoption and duplicated-logic removal is **blocked pending
measured approval**. No existing evidence-pack or claim-validation consumer was
changed, and this Phase 1 JSON is not on a production default path.
