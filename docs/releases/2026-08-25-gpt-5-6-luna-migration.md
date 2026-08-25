# 2026-08-25 GPT-5.6 Luna migration and live validation

All configured generative OpenAI routes now resolve to `gpt-5.6-luna`; the
browser and publisher-discovery OpenRouter routes use
`openai/gpt-5.6-luna`. `text-embedding-3-small` remains the dedicated
embedding model. The operator rate card includes the matching direct and
OpenRouter identities.

The isolated live profile
`gpt_5_6_luna_live_validation_20260825` processed the retained public Adjust
PDF through acquisition, ingest, selection, analysis, validation, and render.
It made 41 live direct-provider calls, all to GPT-5.6 Luna, totaling 323,325
input and 45,040 output tokens at an estimated USD 0.118712. The resulting
71,767-byte report passed final semantic and grounding validation; its four
remaining notices are informational metric-timeframe matches at confidence
1.00.

One initial taxonomy response failed JSON validation. The existing
structured-output repair and targeted regeneration paths each completed with
valid schema output; the final report validation passed. No fixture was
created or changed.

Direct OpenAI and OpenRouter Luna canaries both returned schema-valid output.
Browser diagnostics passed all seven checks. Publish validation was rerun with
the WordPress target and username explicitly empty, confirming that the CLI
fails during local configuration validation before any WordPress request. An
earlier profile-only preflight performed one duplicate lookup because empty
overlay values intentionally fall back to environment values; the zero-write
budget stopped the run before any WordPress write. The configuration procedure
now records the required no-target invocation.

On the retained prompt corpus (79,527 tokens), the expected priced cost fell
from USD 0.079716 to USD 0.050324: USD 0.029392, or 36.87%, lower. This is a
rate-card comparison; it does not claim an end-to-end latency improvement.
