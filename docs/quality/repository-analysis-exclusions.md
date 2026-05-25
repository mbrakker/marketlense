# Repository Analysis Exclusions

Repository analysis tools use `scripts/repository_analysis_exclusions.py` as the shared policy for paths that should not affect maintainability and quality signals.

Included first-party roots are:

- `src/`
- `tests/`
- `scripts/`
- `Wordpress/`

Excluded paths include generated, vendored, temporary, cache, runtime, replay, and local reproduction trees such as `.codex_tmp/`, `.pytest_tmp*/`, `tmp_*`, `mutation_cov_*`, `state/`, `out/`, `cache/`, and `tools/browser-use/`.

When adding an exclusion:

- Prefer a narrow top-level runtime/temp prefix or generated directory name.
- Do not add `src`, `tests`, `scripts`, or `Wordpress` to broad deny lists.
- Add or update a regression test in `tests/test_repository_analysis_exclusions.py`.
- Add an expiry note in the TODO/backlog if the exclusion is temporary rather than durable tooling policy.

`python scripts/count_long_files.py --min-lines 500` reports first-party sections separately and prints skipped-path counts by exclusion reason so local audits can verify that generated or vendored trees are not polluting the signal.
