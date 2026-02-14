# HTML TODO

Last reviewed: 2026-02-13

## Remaining items (non-template scope)

1. Wire real image dimensions from generation output into template context.
   - Current template now sets explicit `width`/`height` defaults to reduce CLS.
   - Follow-up should pass actual dimensions from the image generation/render pipeline for exact layout reservation.
2. Complete responsive image pipeline for true Core Web Vitals gains.
   - Generate and persist responsive variants (for example: `webp` + multiple widths).
   - Expose those variants to HTML rendering so `srcset`/`sizes` pick smaller assets on mobile.
3. Externalize shared HTML stylesheet for cache reuse (if publish path supports static asset hosting).
   - Current template keeps styles inline for self-contained portability.
   - Follow-up should move stable CSS to a shared file and keep only critical CSS inline.

## Editorial improvements (readability + report data visibility)

Last reviewed: 2026-02-14

1. Replace `Unknown publisher` with publisher attribution resolved from evidence packs (`doc_map.publisher`).
2. Add a compact "Report identity" line under the title: report title, publisher, year, and author (if present).
3. Split current time-period copy into clear fields: "Report focus year" and "Fieldwork dates".
4. Convert "Covered topics / TOC" chips into an ordered chapter list for better scan flow.
5. Show section start pages next to each chapter title using `doc_map.sections.start_page`.
6. Sort displayed sections by page number to reflect actual report reading order.
7. Add a "Methodology at a glance" block (population, sample size, sponsor, sampling note).
8. Add a short "What this digest covers" block sourced from scope objectives and in-scope topics.
9. Add a "Key findings" block from `findings.json` using finding title + concise description.
10. Add a visible "Known limitations" block; if limitations are empty, explicitly state that none were extracted.
11. Surface report contact/source organization details from `doc_map.contact`.
12. If source URL is unavailable, show an explicit note instead of silently omitting source references.
13. Move metadata below TL;DR so readers reach high-value summary content first.
14. Replace generic section kickers ("Section 1", etc.) with semantic labels.
15. Break executive summary into short bullets/paragraph chunks to reduce wall-of-text reading fatigue.
16. Keep each key insight to one crisp sentence; move extended framing into a secondary line.
17. Reformat metric strings to natural language (example: `72% (2025, up from 68% in 2024)`).
18. Add citation micro-lines under insights (evidence id + page where available).
19. Replace `Unknown` quote speaker label with clearer copy: `Unattributed in report`.
20. Move generated "Expert comment" and "LinkedIn post" into an appendix-style optional section so the digest remains report-first.
