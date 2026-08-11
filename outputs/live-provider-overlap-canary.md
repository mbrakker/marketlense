# Controlled live-provider overlap canary

Classification: **PROVEN**

This controlled canary measures the potential benefit of advancing independent report work while another task waits for the live OpenAI provider. It does **not** benchmark the currently serial production workflow supervisor.

| Profile | Median wall time | P95 | Median queue wait | Median provider call | Median cost/sample | Quality |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Serial (1 worker) | 9681.076 ms | 11466.210 ms | 3084.586 ms | 3190.767 ms | $0.00084325 | True |
| Capped parallel (3 workers) | 3497.394 ms | 4363.794 ms | 0.358 ms | 3179.522 ms | $0.00084325 | True |

- Preflight JSON-quality gate: **True**.
- Median speedup: **2.768x** (+176.81%).
- Cost non-regression: **True** (parallel median cost is within 1% of serial).
- Quality non-regression: **True** (every response exactly matched its required JSON).
- Measurement: one preflight; 2 warmups plus 7 measured samples/profile; 3 independent requests/sample; `gpt-5-mini`; 512 maximum output tokens; no semantic cache.

## Interpretation

A `PROVEN` outcome demonstrates provider-wait overlap potential only. Real pipeline benefit still requires an implementation that avoids the prior local SQLite-contention regression, followed by a full workflow benchmark.

Full redacted telemetry: [`live-provider-overlap-canary.json`](live-provider-overlap-canary.json).
