# Public Editorial Quality Gate

> **Documentation type:** Current reference
> **Canonical topic:** Canonical report publish-readiness gate
> **Update trigger:** Rule, repair, release-gate, or retained-benchmark changes.

`publish_readiness.json` is the one release decision for each public report. It is produced only after rendering and binds the exact final HTML plus the normalized final WordPress body projection. It includes the report ID, hashes for the retained artifacts, HTML and projection hashes, every rule result, configuration and policy hashes, producer revision, expiry, staleness conditions, classified provenance, and a SHA-256 signature over the artifact itself. WordPress preflight consumes and verifies this artifact; it does not run a separate editorial interpretation of the package.

The existing `public_editorial_quality_before.json`, `public_editorial_quality_after.json`, and regeneration-attempt reports remain private repair diagnostics. They use the same deterministic editorial rules to decide whether a field has enough retained evidence for scoped repair, but they are not independently publishable or a second release policy. The final readiness artifact is authoritative.

`PublicEditorialQualityReport` is a versioned private audit artifact. It records the report ID, stable rule ID, severity, affected artifact and field, retained evidence IDs, deterministic explanation, repair eligibility and status, validator version, and schema version. It is never rendered as reader-facing content.

## Blocking rules

The gate blocks public release unless semantic and grounding validation passed, category decisions agree, every material claim has a valid retained evidence ID, and every regenerated artifact was promoted. It blocks unsupported numeric claims; internal IDs and evidence tokens; placeholders; malformed extraction and OCR fragments; mojibake; missing rendered assets; duplicate boilerplate; filename-style titles and duplicated years; fragments; generic figure labels; unsupported certainty; empty or non-specific decision implications; mechanical labels; literal truncation; private paths and Drive URLs; and invalid public source links.

It inspects headings, body text, captions, quotations, link labels and hrefs, alt attributes, JSON-LD, canonical and Open Graph metadata. A public chart card must be linked end-to-end to an accepted crop candidate, source page, evidence ID, insight ID, caption, and public takeaway. Weak, text-only, or incomplete cards are omitted during rendering and a mismatch between that public projection and the retained card set fails readiness. Cropping is not modified by this gate.

Duplicate detection compares normalized claim-token sets and material-number overlap. Regexes are used only for deterministic syntax defects such as IDs and placeholders; semantic duplication is not determined by a regex alone.

## Provenance and staleness

The retained provenance distinguishes the internal acquisition path, internal archive URL, publisher landing page, original report URL, and MarketLense article URL. Internal locations are recorded only as retained hashes and are never legal public original-source links. A public source hyperlink is allowed only when it matches resolved publisher provenance; otherwise the source section retains safe attribution text without a link.

The readiness decision becomes stale if the final HTML, normalized publication projection, any hashed artifact, configuration, policy, producer revision, or expiry changes. The WordPress projection verifies the same body hash after image URLs are replaced by WordPress media URLs, so the upload step cannot silently change public text, links, or metadata.

## Advisory measurements and repair

The retained report includes non-blocking measurements for insight-role diversity, repeated syntax, excessive verbosity, card-to-insight, figure-to-evidence and figure-to-insight linkage, source-note completeness, and action specificity. They are review signals, not a public score. A public card is accepted only when it carries the retained candidate ID, evidence ID, source page, insight ID, and caption; weak or incomplete cards are omitted by rendering rather than displayed as limited evidence. A source section without a public original-source link must instead state that no verified publisher source link is available; a local path, Drive URL, or unverified URL is never an acceptable substitute.

## Repair and waivers

Only a failed field with retained source text, explicit evidence ID, and a supported existing regeneration target may be regenerated. Passing fields remain unchanged. If that grounding is absent, the repair diagnostic records `abstained`, does not use a generic replacement, and the final readiness artifact remains failed.

The former `ingest.validation.public_editorial_quality.disabled_rule_waivers` setting applies only to retained repair diagnostics. It cannot waive the signed final HTML/projection decision or allow WordPress to reinterpret a failed artifact.

## CI and human review

`python -m scripts.ci.check_public_report_quality --minimum-reports 15` renders the retained golden corpus, requires zero active render/editorial blockers, and compares advisory coverage and duplicate counts to `public_editorial_quality_baseline.json`. Run the blinded human-review template in [public-editorial-human-evaluation.md](public-editorial-human-evaluation.md) on the retained 30-report corpus before declaring the editorial-quality acceptance criterion complete.
