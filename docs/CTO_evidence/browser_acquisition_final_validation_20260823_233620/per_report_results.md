# Per-report acquisition results

The exact frozen title/URL cohort is retained in
[baseline_evidence/baseline_manifest.json](baseline_evidence/baseline_manifest.json).
`Verified` is normal artifact verification, not route inference. Agent calls and
duration are task-scoped values from the final acquisition records.

| Candidate | Publisher | Current route | Verified | Format | Agent calls | Duration |
| --- | --- | --- | --- | --- | ---: | ---: |
| `fac_eda48226bd40dd9fece75890` | BlueCore | `browser_onsite_report` | yes | pdf | 0 | 9.463 s |
| `fac_0294383b7bf86f9bcc6fbf06` | Brand Finance | `browser_listing_hub` | no | none | 5 | 354.455 s |
| `fac_10a7fd2d5e39d5c484777954` | Brand Finance | `browser_onsite_report` | yes | pdf | 0 | 8.842 s |
| `fac_fa1889b4c19f0f238659145e` | Criteo | `browser_preflight_terminal_static_archive` | no | none | 0 | 18.772 s |
| `fac_26fd23fd3cf0198081e38c28` | Criteo | `browser_preflight_js_pdf_probe` | yes | pdf | 0 | 23.305 s |
| `fac_b4408981245f7cedaad405c2` | Kenshoo Skai | `browser_onsite_report` | yes | pdf | 0 | 12.662 s |
| `fac_0ef70242a602b9ed7641c056` | Adjust | `browser_preflight_js_pdf_probe` | yes | pdf | 0 | 32.976 s |
| `fac_8dfcbf4e6cab96beeec896dc` | Adjust | `report_page_pdf_link_probe` | yes | pdf | 0 | 6.434 s |
| `fac_b42ceee7557c1317ef2c2ad6` | Algolia | `browser_onsite_report` | yes | pdf | 0 | 9.423 s |
| `fac_8e7eb10d2c9e0bfa0ab228ff` | Algolia | `report_page_pdf_link_probe` | yes | pdf | 0 | 5.916 s |
| `fac_f2a23a6db782909156ca996f` | Bain & Company | `browser_onsite_report` | yes | pdf | 0 | 8.181 s |
| `fac_266ccff285b4aadcfd6b5151` | BCG | `browser_onsite_report` | yes | pdf | 0 | 21.727 s |
| `fac_8dc34ec7ffcca9fc7f349331` | BlueCore | `browser_onsite_report` | yes | pdf | 0 | 18.993 s |
| `fac_489b10b8fee8b3591af2ce51` | Bright Local | `browser_onsite_report` | yes | pdf | 0 | 9.217 s |
| `fac_3e630244e5c22fe8fa787255` | GWI | `browser_pdf_click` | yes | pdf | 3 | 212.869 s |
| `fac_4da62bac17be2e7185090695` | GWI | `browser_email_form` | no | none | 0 | 23.051 s |
| `fac_c0e4c925c1ed4ce6149711b8` | GWI | `browser_email_form` | no | none | 0 | 26.956 s |
| `fac_6f994caaf9a413e4038f18f1` | GWI | `browser_email_form` | no | none | 0 | 27.239 s |
| `fac_9d4d17626b51fdefb56842cb` | Barclays | `unresolved` | no | none | 0 | 0.002 s |
| `fac_82f650b19147f442363508b2` | Barclays | `browser_onsite_report` | yes | pdf | 0 | 8.093 s |
| `fac_79d2b1c0c59436f8eacd7de4` | Jungle Scout | `browser_onsite_report` | yes | pdf | 0 | 16.931 s |
| `fac_92baa3a4f4faa888ade7d54f` | Jungle Scout | `browser_onsite_report` | yes | pdf | 0 | 14.138 s |
| `fac_057817530e711866e5fea457` | Jungle Scout | `browser_onsite_report` | yes | pdf | 0 | 27.945 s |
| `fac_74ff8c2c4382773a4f8d5f55` | Jungle Scout | `browser_onsite_report` | yes | pdf | 0 | 11.357 s |
| `fac_80dc158f27be79e08f090b8c` | Jungle Scout | `browser_onsite_report` | yes | pdf | 0 | 15.049 s |
| `fac_c21286d0bf9647749fa4dae3` | Jungle Scout | `browser_onsite_report` | yes | pdf | 0 | 11.351 s |
| `fac_6dae1d79b7340a3e0fd5055b` | Jungle Scout | `browser_onsite_report` | yes | pdf | 0 | 12.786 s |
| `fac_248c234f4d797e8eca595ff3` | Jungle Scout | `browser_onsite_report` | yes | pdf | 0 | 13.452 s |
| `fac_0a2d080a0bcc92e54f50e171` | Jungle Scout | `browser_onsite_report` | yes | pdf | 0 | 10.873 s |
| `fac_05b9e5cae6b0bbaf35801e27` | Jungle Scout | `browser_onsite_report` | yes | pdf | 0 | 11.185 s |

Failures retained in the denominator:

- Brand Finance `fac_029…`: `browser_download_agent_timeout` after five Agent calls.
- Criteo `fac_fa188…`: `external_source_unavailable` /
  `blocked_static_archive` after terminal static-archive preflight; no Agent
  call was made and the frozen candidate remains a failure in the denominator.
- GWI `fac_4da…`, `fac_c0e…`, and `fac_6f9…`: `email_required` after deterministic
  email-form handling, with no Agent calls.
- Barclays `fac_9d4…`: `report_download_candidate_rejected_mixed_content_hub`, with
  zero external work; it was not substituted with an arbitrary report.
