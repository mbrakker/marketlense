# Browser Use context-reduction validation — 2026-08-20

## Decision

Do not enable generic Browser Use prompt-context removal or browser-state/history
bounding for the retained `browser_pdf` route. The implementation experiment was
rolled back completely after the live quality/cost gate failed.

## Live evidence

The same retained public route and unchanged `gpt-5-mini` model were exercised
in isolated local output/state directories. Drive upload and publication were
disabled. The full-context control completed in three Agent calls with input
tokens of `15,669`, `20,369`, and `20,767` (`56,805` total).

The reduced-context experiment removed duplicate route prose, used a history
limit of six and a clickable-state limit of 1,000, and recorded `reduced` mode
for every call. It completed successfully only after thirteen Agent calls with
`275,104` total input tokens: a 384% increase over the control. An earlier
reduced run timed out, confirming that the reduction can also regress latency.

The route therefore does not meet the required meaningful token reduction or
non-regression threshold. It is not evidence of retained-corpus success-rate
preservation and must not be used to justify a default rollout.

## Follow-up constraint

Any future attempt must first replace the relevant residual browser work with
verified deterministic route execution, or provide a route-specific compact
action representation that preserves navigation intent. It must then pass a
retained-corpus comparison with per-step input-token accounting before any
default is changed.
