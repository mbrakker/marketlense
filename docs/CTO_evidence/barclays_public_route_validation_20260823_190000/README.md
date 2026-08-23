# Barclays public-route validation — 2026-08-23

Validation target: public Barclays Investment Bank insight pages, without
Browser Use Agent execution, form submission, account creation, or Barclays
Live login.

Starting commit: `5865de7d20c07635c22da404154a25084b32022e`.

## Results

| Public route | Expected acquisition | Observed route | Verified local artifact |
| --- | --- | --- | --- |
| `https://www.ib.barclays/our-insights/3-point-perspective/uk-public-m-and-a-five-questions-clients-are-asking-in-2026.html` | Publisher PDF link | `report_page_pdf_link_probe` | `out/barclays_public_pdf_live_validation_20260823_190000/2026%20UK%20Public%20M%26A%20Trends%E2%80%8B.pdf` — 520,331 bytes, SHA-256 `4cae6da4182f65c2d65a0639028c43e503e049bd26ab93732738549baa3bce98` |
| `https://www.ib.barclays/our-insights/3-point-perspective/the-return-of-equity-issuance-whats-driving-this-wave.html` | Public online article rendered locally | `browser_onsite_report` / `rendered_onsite_pdf` | `out/barclays_public_detail_live_validation_20260823_190000/onsite_capture.rendered.pdf` — 317,011 bytes, SHA-256 `d366985b597e1839f87e2f0cf48c9822bedf8b44e92845da9fb16a65606e54ad` |

Both routes passed their normal PDF signature and on-site route verification.
The public article contains a short `enable JavaScript` noscript message;
substantial public report content remained available, so that incidental copy
was not treated as an access block. No model call or browser launch was needed
for either deterministic validation route.

The generic historical candidate `https://www.ib.barclays/research.html` was
not retried as a substitute report. It remains a listing-level, title-less
candidate: the new deterministic on-site-rendering eligibility rule explicitly
excludes generic hubs and does not select an arbitrary insight or the Barclays
Live portal.

Focused regression coverage:

```text
pytest -q tests/test_browser_report_download_service/test_onsite_and_terminal.py -k 'public_detail_without_candidate_trace or ambiguous_listing_hub or javascript_interstitial'
# 3 passed (including a short JavaScript-interstitial rejection)

pytest -q tests/test_browser_report_download_doc_type_predictor.py
# 4 passed
```
