# Reports DB Data Sources

| field | first choice source if available | fallback option if first choice not available |
| --- | --- | --- |
| `file_id` | `DriveFile.file_id` from ingest pipeline | No fallback (required) |
| `title` | `_derive_title(file_name)` where `file_name` is Drive file name | If name missing: fetch name from Drive metadata, else use `file_id` |
| `publisher` | `doc_map.publisher` (set into `data.publisher` when present) | Empty string -> stored as `NULL` |
| `taxonomy_json` | `data.taxonomy` from taxonomy model output | Empty list `[]` (model failure / invalid schema / no tags) |
| `categories_json` | Category mapping result from taxonomy tags | Empty list `[]` if unmapped / no tags |
| `region` | `data.region` from taxonomy extraction | Empty -> `NULL` |
| `time_period` | `data.time_period` from taxonomy extraction | Empty -> `NULL` |
| `source_url` | `data.source` | Currently defaults empty, so stored as `NULL` |
| `html_path` | Cached HTML path (when cache key matches and file exists) | Fresh render output path from `render_report_service` |
| `md5` | Drive-provided `md5_checksum` | Sidecar MD5 -> computed local file MD5 -> download response MD5 -> `NULL` |
| `page_count` | Cached `pdf_info.page_count` | Direct `extract_pdf_info` result; if invalid then `NULL` |
| `contents_page` | Detected contents page number (cached or live detection) | `0` when not detected / error |
| `pdf_metadata_json` | Cached `pdf_info.metadata` | Direct `extract_pdf_info` metadata; cleaned empty dict `{}` |
| `analysis_mode` | `analysis_mode` in generator (`"vector_store"`) | Service default `"vector_store"` |
| `vector_store_id` | Vector store indexing result ID | `NULL` |
| `evidence_packs_json` | `primary_evidence_paths` from generated/stored packs | Empty dict `{}` |
| `created_at` | DB insert timestamp (`strftime('%s','now')`) | On conflict update: preserved existing value |
| `updated_at` | DB insert/update timestamp (`strftime('%s','now')`) | Always refreshed on upsert |

# HTML Output Data Sources

| field | first choice source if available | fallback option if first choice not available |
| --- | --- | --- |
| `html_path` | Cached HTML at `output/<slug(doc_name)>.html` when cache key matches | Fresh render output from `render_report` |
| `report_title` (`<h1>`, SEO title base) | `request.data["title"]` passed to template as `report_title` | `doc_name` |
| `publisher` (hero/meta) | `data.publisher` | Empty -> UI shows `Unknown publisher` |
| `report_year` | `data.time_period` | Empty (not shown) |
| `region` | `data.region` | Empty (not shown) |
| `source_url` | `data.source` | Empty |
| `canonical_url` | `data.canonical_url` | `source_url` -> empty |
| `tldr_text` | `artifacts.summary.tldr` | `data.tldr` -> `"Not available from text."` when `not_available` |
| `executive_summary` | `artifacts.summary.executive_summary` | `data.commentary` -> empty |
| `claim_evidence_map` | `artifacts.summary.claim_evidence_map` | Empty list |
| `topics_list` | `artifacts.toc_topics` | Empty list |
| `insights_list` | `artifacts.insights_final` | `data.insights` -> empty / placeholder |
| `quotes_list` | `artifacts.quotes_final` | Synthetic quote from `data.quote` (`text/author/page`) |
| `expert_comment` section | `artifacts.expert_comment` | Section hidden |
| `linkedin_post` section | `artifacts.linkedin_post` | Section hidden |
| `commentary` section | `data.commentary` | Hidden if empty (also hidden when expert comment exists) |
| `categories_list` | `data.categories_display` (mapped labels) | `data.categories` (category IDs) |
| `tags_list` | `data.taxonomy` | Empty list |
| `primary_figure` | `data._figure_top` | `data._figure_image` -> none |
| `figure_caption` | `data.figure.title` | `data.figure.evidence` -> template default caption text |
| `figure_gallery` | `data._figure_gallery` | Empty list |
| `contents preview image` | `data._contents_image` (only when `contents_page_number > 0`) | Section hidden |
| `contents page number` | `data.contents_page_number` from TOC detection | `0` |
| `contents heading` | `data.contents_heading` from TOC detection | Empty |
| `not_available` notice flag | `artifacts.source_status.not_available` | `data._text_not_available` -> `False` |
| `fallback_reason` text | `artifacts.source_status.reason` | Empty |
| `primary_image` (OG/Twitter/LD image) | `preview_png` from render request | `primary_figure` -> empty |
| `seo_description` | `tldr_text` | `executive_summary` -> `"Digest for {report_title}"` |
| `robots_content` | `data.robots` | Computed: `index,follow` or `noindex,nofollow` |
| `jsonld.keywords` | `tags_list` | `categories_list` |
| `file_id` (meta/footer) | `DriveFile.file_id` passed to render | No fallback |

# Proposed Updated HTML Sourcing (Editorial + Consistent)

Use one resolved object before rendering (for example `EditorialHtmlViewModel`) and keep the template display-only.

| field | first choice | fallback 1 | fallback 2 |
| --- | --- | --- | --- |
| `headline` | `doc_map.title` | cleaned file name | `file_id` |
| `publisher` | `doc_map.publisher` | existing DB publisher | `"Unknown publisher"` |
| `time_period` | taxonomy `time_period` | `doc_map.time_period` | empty |
| `region` | taxonomy `region` | `doc_map.region` | empty |
| `canonical_url` | `doc_map.source_url` | payload `source` | empty |
| `source_url` | payload `source` | `canonical_url` | empty |
| `tldr` | `artifacts.summary.tldr` | payload `tldr` | empty |
| `executive_summary` | `artifacts.summary.executive_summary` | payload `commentary` | empty |
| `insights` | `artifacts.insights_final[].text` | payload `insights[]` | empty list |
| `quotes` | `artifacts.quotes_final[]` | payload `quote` (single-item list) | empty list |
| `topics` | `artifacts.toc_topics` | empty list | - |
| `categories_display` | mapped category labels | category IDs | empty list |
| `tags` | taxonomy tags | empty list | - |
| `primary_image` | `_figure_top` | `_figure_image` | `preview_png` |
| `figure_caption` | `figure.title` | `figure.evidence` | empty |
| `contents_preview` | `_contents_image` + `contents_page_number > 0` | none | - |
| `not_available_reason` | `artifacts.source_status.reason` | text-density reason | empty |
| `robots` | explicit payload/config | `index,follow` only if substantive content exists | else `noindex,nofollow` |

## Editorial Readability Rules

- Show one neutral availability note only; avoid repeating `"Not available from text"` across sections.
- Hide empty sections instead of rendering placeholders.
- Always display category labels; use raw IDs only when labels are unavailable.
- Normalize text once before render: trim, dedupe, sentence-case fallback reasons, collapse whitespace.
- Prefer short headings: `Summary`, `Key Findings`, `Quotes`, `Source`.

## No Special Effects Rules

- Remove carousel, lightbox, sticky progress bar, and animated reveal behavior.
- Use one static lead image when available.
- Keep sections linear, simple, and print-friendly.

## Suggested Implementation Points

- Build resolved view model in `src/generators/report_generator.py`.
- Keep template logic minimal in `templates/report.html.j2`.
- Pass final resolved fields through `src/services/render_service.py`.
