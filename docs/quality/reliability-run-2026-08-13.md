# Frozen 20-report reliability run — 2026-08-13

> **Record type:** Retained operational evidence. This is a partial-run record,
> not a release approval or a claim of end-to-end success.

## Identity and control

- Isolated profile: `reliability_full_20260812_507aa72521514a27a98edf8ed85244aa`.
- Immutable cohort ID:
  `e451b3a175d827d61ad1a020f252152db829b3814b3f12e7117320964f42134c`.
- Validation run ID:
  `validation:92cdd2e1e862f9099e85723468418d33cadfb5b501cd7869b8ab7f7bf24b4be7`.
- Frozen at `2026-08-13T11:26:06Z`; the linked validation manifest was created
  at `2026-08-13T11:29:56Z`.
- The source universe was used before Drive persistence. The cohort was frozen
  at 20, all acquisitions were successful, and no member was replaced.
- Publisher cap was 3: the retained counts are Cardlytics 3, cdn.sanity.io 3,
  Adjust 2, BCG 2, Bain & Company 2, BlueCore 2, and one each for the remaining
  six publishers.
- Sandbox WordPress publish pacing was configured at 120 seconds between
  actual report publishes.

The live state manifests retained with this run are
`state/<profile>/frozen_cohort_20.json`, `drive_cohort_persistence.json`, and
`validation_cohort_20_publish_paced_12.json`. They contain checksums,
timestamps, source identities, selected routes, Drive IDs, and per-report
processing outcomes. The repository evidence below duplicates the bounded IDs
and terminal dispositions so that this run can be audited without source text
or secrets.

## Discovery, route selection, acquisition, and Drive persistence

All 20 source records were acquired from the configured source universe and
then uploaded and verified in the run-owned Drive folder
`1e18jyDtAq_I2qL1MH4-HKVH1ftJHzo3a`. The routes exercised six materially
different families.

| Source record | Publisher | Selected route | Drive ID | Persistence |
| --- | --- | --- | --- | --- |
| 1 | cdn.sanity.io | `direct_pdf_probe` | `1NY43tL30T-fd44U6i5-ZznkAx0LQSkDQ` | passed |
| 2 | cdn.sanity.io | `direct_pdf_probe` | `1PoXml-tpkL2VDMUgxtj0Tx2e46jccDKW` | passed |
| 3 | cdn.sanity.io | `direct_pdf_probe` | `1597Id8743JAsW3SHd_3WWngRk6X726VX` | passed |
| 4 | Algolia | `report_page_pdf_link_probe` | `166LocR4HCDzBwTfl1dOf6YIdxQZd_u4K` | passed |
| 7 | Bain & Company | `report_page_pdf_link_probe` | `1injIblyoZsMhFhcsDxFw8uk0IsWHRQmh` | passed |
| 8 | Bain & Company | `report_page_pdf_link_probe` | `1y5uWIo-HpEOojg4vdc9dW1e28KIN2z85` | passed |
| 10 | BCG | `browser_preflight_js_pdf_probe` | `1Qz2Eay-EiRMMcygOTT9cD_C4_PiMPUpp` | passed |
| 11 | Adjust | `report_page_pdf_link_probe` | `1LylPDHZYO6pHhUHA-jxNBbflfc1Fr7nC` | passed |
| 12 | Brand Finance | `browser_listing_hub` | `1hkdASxtqI_n27kMgLtlHN6uXxB4XxvxZ` | passed |
| 13 | Adjust | `browser_listing_hub` | `1f0jh1SIfd39hxQN21wvQT0mH2IgGklbu` | passed |
| 15 | 39560757.fs1.hubspotusercontent-na1.net | `direct_pdf_probe` | `1bU1ji5HVxHwPxtdT365UVZ5N10zy0dCE` | passed |
| 16 | BlueCore | `browser_pdf_click` | `1ojaFaRfntjV4BUHPlgrVedwQQ5ycyzeh` | passed |
| 17 | BlueCore | `browser_pdf_click` | `1vTf0IkhAnB2XHQQmR0-HcoQeEEslv7M2` | passed |
| 21 | Cardlytics | `direct_pdf_probe` | `1iwZS85W9sg1rYwLikwgmi0vmtyh6lUnO` | passed |
| 22 | BCG | `browser_preflight_js_pdf_probe` | `1BKhlmuwCgFMbADrdvP8tB-EvGHFgc7uF` | passed |
| 23 | Cardlytics | `report_page_pdf_link_probe` | `1USCHRNH8yLwKgWFGFp_bU7hfZBeVfv3n` | passed |
| 24 | Cardlytics | `report_page_pdf_link_probe` | `1pL6t1hhdun3Iqenliwi-odc2Rr-EHKx4` | passed |
| 25 | Criteo | `browser_tracker_redirect` | `1eD6vUZEICQWi6cI8uKNZuL1idkv-kAfk` | passed |
| 61 | iAB | `browser_preflight_js_pdf_probe` | `1V8a4cBK4U3VNAAJVVZsoTnxJib9rmpjW` | passed |
| 69 | iAB Europe | `report_page_pdf_link_probe` | `1IEcPHWWv97RKsUCF1Qzt2BH7T54aDeq1` | passed |

## Processing and readiness

- Processing and editorial generation: **passed for 18/20** without replacing
  cohort members.
- Readiness: **passed for 18/20**.
- `1Qz2Eay-EiRMMcygOTT9cD_C4_PiMPUpp`: **failed** at readiness with
  `publish_readiness_failed` (strict public-readiness/grounding requirements).
- `1injIblyoZsMhFhcsDxFw8uk0IsWHRQmh`: **failed** at readiness with
  `publish_readiness_failed` (conflicting `$90B` and `$35B` exit figures).

The ingest replay retained the immutable cohort and made no regeneration or
replacement: `ingest_publish_paced_12.exit.json` records 18 `html_exists`
publish-ready items and the two permanent readiness failures.

## Sandbox WordPress publication and authenticated readback

The target preflight was authenticated and writable before the two publish
passes. Publication then became externally unstable. The first pass created
and authenticated-readback verified five posts; the resumed pass performed a
zero-write idempotency/readback check for those five and verified four further
posts. These nine records are persisted in `index.sqlite`'s `published` table.

| Drive ID | Post ID | Status | Evidence |
| --- | --- | --- | --- |
| `1597Id8743JAsW3SHd_3WWngRk6X726VX` | 1921 | passed | persisted post plus authenticated readback |
| `166LocR4HCDzBwTfl1dOf6YIdxQZd_u4K` | 1926 | passed | persisted post plus authenticated readback |
| `1BKhlmuwCgFMbADrdvP8tB-EvGHFgc7uF` | 1931 | passed | persisted post plus authenticated readback |
| `1IEcPHWWv97RKsUCF1Qzt2BH7T54aDeq1` | 1936 | passed | persisted post plus authenticated readback |
| `1LylPDHZYO6pHhUHA-jxNBbflfc1Fr7nC` | 1941 | passed | persisted post plus authenticated readback |
| `1NY43tL30T-fd44U6i5-ZznkAx0LQSkDQ` | 1949 | passed | persisted post plus authenticated readback |
| `1PoXml-tpkL2VDMUgxtj0Tx2e46jccDKW` | 1954 | passed | persisted post plus authenticated readback |
| `1USCHRNH8yLwKgWFGFp_bU7hfZBeVfv3n` | 1959 | passed | persisted post plus authenticated readback |
| `1V8a4cBK4U3VNAAJVVZsoTnxJib9rmpjW` | 1964 | passed | persisted post plus authenticated readback |
| `1bU1ji5HVxHwPxtdT365UVZ5N10zy0dCE` | 1969 | unverified | post-create event followed by `wordpress_post_create_readback_missing`; no durable published record |
| `1eD6vUZEICQWi6cI8uKNZuL1idkv-kAfk` | 1974 | unverified | post-create event followed by `wordpress_post_create_readback_missing`; no durable published record |
| `1f0jh1SIfd39hxQN21wvQT0mH2IgGklbu` | — | blocked | `wordpress_target_installation_redirect` during WordPress media work |
| `1pL6t1hhdun3Iqenliwi-odc2Rr-EHKx4`, `1iwZS85W9sg1rYwLikwgmi0vmtyh6lUnO`, `1vTf0IkhAnB2XHQQmR0-HcoQeEEslv7M2`, `1ojaFaRfntjV4BUHPlgrVedwQQ5ycyzeh`, `1hkdASxtqI_n27kMgLtlHN6uXxB4XxvxZ`, `1y5uWIo-HpEOojg4vdc9dW1e28KIN2z85` | — | skipped | blocked before their publish attempt |
| `1Qz2Eay-EiRMMcygOTT9cD_C4_PiMPUpp`, `1injIblyoZsMhFhcsDxFw8uk0IsWHRQmh` | — | failed | not publish-ready; no publication attempted |

The resumed run (`2026-08-13T16:45:04Z`–`17:00:20Z`, exit 1) observed the
target redirect to `wp-admin/install.php` while using authenticated REST
requests. The typed non-retryable error is
`wordpress_target_installation_redirect`. This indicates target installation,
database, or host-routing instability, not an application authentication
failure. The guard intentionally stopped publication as required by run
control.

At `2026-08-13T17:14:43Z`, an explicitly authorized retry performed an
authenticated, read-only target preflight before any publication work. It
failed with the same non-retryable `wordpress_target_installation_redirect`.
No report publish was attempted and no WordPress write occurred in that retry.

Earlier transient failures are also retained in `publish_paced_12.stdout.log`:
`wp_media_client_error` for `1NY…`, and `wp_media_upload_failed` after setup
redirects for `1Po…` and `1US…`. Each was subsequently published and verified
only after target preflight succeeded; none was silently reclassified.

## Idempotency and disposition

The resume pass performed authenticated, zero-write idempotent readback for
the first five persisted posts. That is **partial evidence only**. A full
cohort repeat has not run and therefore the zero-duplicate idempotency gate is
**blocked**, not passed.

The overall 20-report end-to-end reliability run is **not complete**:

- 20/20 discovery, acquisition, and Drive persistence passed.
- 18/20 processing/editorial/readiness passed; 2/20 failed typed readiness.
- 9/18 publish-ready reports have persisted publication and authenticated
  readback; 2 are unverified, 1 is blocked at the target, and 6 are unattempted.
- No full authenticated readback or zero-duplicate repeat exists for the
  18-report cohort.

Before safely resuming, the sandbox owner must repair and stabilize the
configured WordPress target so that authenticated REST requests never redirect
to installation/setup. Resume must use this same immutable cohort, begin with
preflight and authenticated readback of posts 1969 and 1974, then continue
only unverified/unattempted members with the 120-second pacing. No member may
be regenerated or replaced.

## Evidence paths

- `state/<profile>/frozen_cohort_20.json`
- `state/<profile>/drive_cohort_persistence.json`
- `state/<profile>/validation_cohort_20_publish_paced_12.json`
- `state/<profile>/ingest_publish_paced_12.exit.json`
- `state/<profile>/publish_paced_12.stdout.log`
- `state/<profile>/publish_resume_paced_12.stdout.log`
- `state/<profile>/publish_resume_paced_12.exit.json`
