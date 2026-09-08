# IAB Europe AdEx title-resolution audit — 2026-09-08

## Scope

The source PDF was
`IAB_Europe_AdEx_Benchmark_2025_updated.pdf` (MD5
`a972f75a2d2441ca8f8371f53adcbec2`). Its embedded PDF title is
`PowerPoint Presentation`; the cover visibly states `AdEx Benchmark 2025
Report`, and page 2 calls it IAB Europe's AdEx Benchmark Report.

## Result

Before this change, the embedded PDF metadata title was selected as
`PowerPoint Presentation`. After the change, the deterministic source resolver
returned:

```json
{
  "title": "AdEx Benchmark 2025 Report",
  "edition": "2025",
  "publisher_candidate": "IAB Europe",
  "confidence": "medium",
  "candidate_source": "source_content",
  "issues": []
}
```

The fresh isolated full pipeline completed with `status: processed` and
`publish_readiness_status: pass`. Its rendered validation artifact is
`out/title_resolution_iab_validation/fresh_pipeline_full/output/iab-europe-adex-benchmark-2025-updated-pdf.html`.
The final values were:

| Surface | Value |
| --- | --- |
| HTML title, OG title, Twitter title | `AdEx Benchmark 2025 Report \| IAB Europe \| MarketBearing` |
| H1 and JSON-LD `headline` | `AdEx Benchmark 2025 Report` |

The SEO suffix is the established renderer convention; each surface uses the
same resolved canonical report title and none contains `PowerPoint
Presentation`.

## Independent identity audit

An independent `gpt-5.6-terra` image-and-source-evidence audit returned
`verdict: PASS` and `exact_semantic_identity: true`. It identified the source
title and resolved title as `AdEx Benchmark 2025 Report`, edition `2025`, and
publisher candidate `IAB Europe`; it explicitly rejected `PowerPoint
Presentation` as generic application metadata. Request ID:
`resp_0fa05e82e1babbdc006a9fecc0539487d2ad786861d95b01b1`.

## Automated validation

`131` focused tests passed across title resolution, the bounded identity call,
source preparation, rendering, LLM routing, prompt fixtures, and title
recovery. The cases cover PowerPoint and Word generic metadata, missing
metadata, filename fallback, edition/year insertion, ambiguity, and subtitles.
The full IAB run additionally verified source checkpoint persistence and a
publication-ready rendered artifact.

## Regression sweep

The retained Batch 4 source PDFs resolved to their visible identities:

| Source | Resolved title |
| --- | --- |
| IAB Europe Guide to AI in Retail & Commerce Media | IAB Europe's Guide to AI in Retail & Commerce Media |
| IAB Europe AdEx 2025 | AdEx Benchmark 2025 Report |
| Nielsen Consumer Outlook | Consumer Outlook: Guide to 2026 |
| Digital 2022: Sweden | DIGITAL 2022: SWEDEN |
| Activate Technology & Media Outlook 2021 | ACTIVATE TECHNOLOGY & MEDIA OUTLOOK 2021 |

An additional retained benchmark source-resolution sweep resolved the visible
identities:
`Technology & Media Outlook 2025 eCommerce`, `Technology & Media Outlook
2026`, `Trust or trepidation? How Brits feel about generative AI in media`,
and `Internet Advertising Revenue Report Full-year 2024 results`. The
resolver rejects cover publisher marks (`ACTIVATE CONSULTING`) and country
brands (`GREAT BRITAIN`) as titles.
