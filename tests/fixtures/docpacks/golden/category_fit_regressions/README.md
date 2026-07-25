# Category-fit regression corpus

These cases are compact, field-preserving projections of retained provider
outputs.  They intentionally retain only the report-context fields consumed by
the category-fit boundary and the category candidate under test; they are not
hand-authored report scenarios.

| Case | Retained source |
| --- | --- |
| `high_fit_supported_no_exclusion` | `out/reliability_canary_20260722_retry4/activate-technology-and-media-outlook-2024-pdf/report_analysis/{report_context,context_category_fit}.json` |
| `activate_social_video_contradiction` | `out/reliability_canary_20260722_retry4/1nrxx69qt4pqye59eei2cs6waozet9cb5/report_analysis/{report_context,context_category_fit}.json` |
| `creator_influencer_category` and `social_commerce_category` | `out/live_validation_20260719/influencer-portfolio-ebook-0426-pdf/report_analysis/{report_context,context_category_fit}.json` |
| `secondary_creator_content` | `out/reliability_canary_20260722_retry7/d8ca0bf6efb9c703343867f6df0f26a2553aa78f-pdf/report_analysis/{report_context,context_category_fit}.json` |
| `explicit_exclusion_conflict` | Pre-existing regression `tests/test_context_category_fit_generator.py::test_fit_report_categories_rejects_topic_exclusion_conflict` |
| `low_fit_rejection` | `out/reliability_canary_20260722_retry4/1nrxx69qt4pqye59eei2cs6waozet9cb5/report_analysis/{report_context,context_category_fit}.json` |

The source SHA-256 values are recorded in `cases.json`. The corpus preserves
each source candidate's category ID, fit score, decision under test, and
evidence direction while reducing unrelated provider text. A decision is set
to the recorded contradictory state only when that is the behavior under test;
no scenario or report content is invented.
