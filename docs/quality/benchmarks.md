# Benchmarks

> **Documentation type:** Current reference
> **Canonical topic:** Benchmark methodology
> **Update trigger:** Benchmark corpus, baseline, comparator, or threshold change.

MarketLense uses retained fixture corpora and generated outputs to detect regressions in candidate extraction, crop refinement, prompt fixtures, public rendering, and selected routing paths. Baseline and allowlist files under `docs/quality/` are inputs to their corresponding scripts; generated result payloads belong in runtime output or CI artifacts.

Benchmark commands and current enforcement are maintained by the CI workflow and the non-regression policy. Do not paste benchmark result tables into the root README or release summaries. Record approved exceptions in the policy-controlled allowlist or release-evidence mechanism.

See [non-regression policy](non-regression-policy.md) and [release gates](release-gates.md).
