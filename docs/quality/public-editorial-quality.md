# Public Editorial Quality Gate

> **Documentation type:** Current reference
> **Canonical topic:** Deterministic public-report editorial release gate
> **Update trigger:** Rule, repair, release-gate, or retained-benchmark changes.

Every public report is evaluated twice: before any validation-driven repair and again after the last repair. Each evaluation is retained as `public_editorial_quality_before.json`, `public_editorial_quality_after.json`, or a numbered regeneration-attempt artifact alongside the report analysis packs. The canonical `validation.json` receives enabled blocker findings, so the existing WordPress preflight blocks publication under `publish.validation_policy: block` until the post-repair result passes.

`PublicEditorialQualityReport` is a versioned private audit artifact. It records the report ID, stable rule ID, severity, affected artifact and field, retained evidence IDs, deterministic explanation, repair eligibility and status, validator version, and schema version. It is never rendered as reader-facing content.

## Blocking rules

The gate blocks public release for unsupported numeric claims; material claims without retained evidence linkage; internal IDs; placeholders; malformed extraction and OCR fragments; missing rendered assets; exact or high-confidence duplicate insights; fragments; generic figure labels when a descriptive caption exists; generic fallback boilerplate; certainty unsupported by evidence status; and empty or non-specific decision implications.

Duplicate detection compares normalized claim-token sets and material-number overlap. Regexes are used only for deterministic syntax defects such as IDs and placeholders; semantic duplication is not determined by a regex alone.

## Advisory measurements

The retained report includes non-blocking measurements for insight-role diversity, repeated syntax, excessive verbosity, chart-to-insight linkage, source-note completeness, and action specificity. They are review signals, not a public score.

## Repair and waivers

Only a failed field with retained source text, explicit evidence ID, and a supported existing regeneration target may be regenerated. Passing fields remain unchanged. If that grounding is absent, the gate records `abstained`, does not use a generic replacement, and remains blocked for editorial resolution.

To disable a rule during staged rollout, add its exact stable rule ID and a non-empty release-waiver reason under `ingest.validation.public_editorial_quality.disabled_rule_waivers`. Empty entries do not disable a rule. Waived rule IDs are logged without report text.

## CI and human review

`python -m scripts.ci.check_public_report_quality --minimum-reports 15` renders the retained golden corpus, requires zero active render/editorial blockers, and compares advisory coverage and duplicate counts to `public_editorial_quality_baseline.json`. Run the blinded human-review template in [public-editorial-human-evaluation.md](public-editorial-human-evaluation.md) on the retained 30-report corpus before declaring the editorial-quality acceptance criterion complete.
