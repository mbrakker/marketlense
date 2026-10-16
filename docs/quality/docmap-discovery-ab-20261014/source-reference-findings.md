# DocMap discovery experiment: source reference findings

These propositions were independently checked against the frozen original PDFs, including rendered chart labels where text extraction could detach a value from its subject. They form a report-specific reference set for semantic comparison; model wording and the baseline outputs are not the reference. `p.` means physical PDF page, followed by printed page in parentheses only when different. Forecasts, expectations, and respondent intentions remain qualified as such.

## Frozen source identities

| Report | PDF SHA-256 |
|---|---|
| Capgemini | `612f362e1bff3c307e4db4aed38414f7b3ac85dd5cba4742ef78625cd225ef3e` |
| Activate | `5f960886c6d6ee8cf355b4d469a6c1bc12080cd85351b4cb457c8565ae9dd4f2` |
| KPMG | `a97f4478327c50e9815102de229ad35bc22c3dce8f88cd49a75027e16ea08589` |
| Reuters Institute | `f746133b3d66479b716e61cbaf3771b45b035fdf7801251511cc7ba510413a52` |
| Adjust | `ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3` |

## Reference propositions

### Capgemini

| ID | Source-verified proposition | Source pages | Scope / guardrail |
|---|---|---|---|
| CAP-1 | 74% cite a competitor's lower regular price as a reason to switch; 71% cite an unannounced reduction in pack size or quality. | 10–11 | Stated switching reasons, not observed switching rates. |
| CAP-2 | In October 2025, 49% report buying smaller quantities and 48% report choosing cheaper alternatives. | 21–22 | Separate responses. The report associates smaller quantities with consumption control and cheaper alternatives with managing budgets. |
| CAP-3 | 59% notice a size decrease when price is unchanged; 66% prefer a small price increase to an undisclosed size cut; 64% consider same-price smaller packs unfair. | 14–15 | Three related but distinct measures; do not merge their denominators or meanings. |
| CAP-4 | For performance-critical categories, 77% avoid private labels and 70% worry cheaper substitutes may underperform. | 23 | Keep the category context (including electronics and baby care) attached. |

### Activate

| ID | Source-verified proposition | Source pages | Scope / guardrail |
|---|---|---|---|
| ACT-1 | Consumer internet/media revenue is forecast to grow about $302B in 2017E–2021E, at 4.1% CAGR versus about 3% GDP CAGR. | 5 (printed 4) | Forecast and report-defined revenue scope, not realized growth or all technology revenue. |
| ACT-2 | In the U.S. 2017 top quartile, heavy video users account for 61% of viewing time and 34% of consumer spend; heavy audio users account for 64% of listening time and 47% of spend. | 15 (printed 14); 17 (printed 16) | Bind each format, population, and measure correctly. The video values are 61/34, not 66/61. |
| ACT-3 | Among creators with 50M+ YouTube views in Q2 2017, 24% of creators account for 71% of views; the Facebook cohort is 26% of creators and 77% of views. | 53 (printed 52) | Keep platform and creator-share/view-share pairs together. |
| ACT-4 | The U.S. top quartile of gamers accounts for 70% of game-play time and 63% of consumer spend. | 18 (printed 17) | 2017 survey; values describe the top 25% of gamers, not shares of users. |

### KPMG

| ID | Source-verified proposition | Source pages | Scope / guardrail |
|---|---|---|---|
| KPMG-1 | PE respondents expect a mean 7.3 deals in 2026 versus 5.2 for corporate respondents. | 15 | Plans/expectations, not completed transactions. |
| KPMG-2 | The report presents carve-outs and separation as a structural 2026 feature and an expanded opportunity for buyers and sellers. | 13 | Qualitative thesis, not a measured increase in deal volume. |
| KPMG-3 | AI-enabled analysis can make previously uneconomical diligence and benchmarking work viable, including review across many contracts or comparables. | 26 | Capability/potential, not measured realized productivity or financial return. |
| KPMG-4 | Expected next-deal size is mostly below $1B: chart buckets sum to 81% of corporate and 94% of PE respondents. | 16 | Derived from displayed rounded categories; respondent expectations, not realized size. |
| KPMG-5 | Carve-out acquisitions are under consideration for 55% of PE respondents versus 21% of corporate respondents; minority-to-majority investment is 50% versus 18%. | 17 | Plans under consideration, not executed deals. |
| KPMG-6 | Expected pipeline volume in 2026 vs. 2025 is much/slightly higher for 62% in APAC, 43% in EMEA and 58% in the Americas. | 11 | Correct chart mapping: APAC 62%, EMEA 43%, Americas 58%. Expectations, not realized pipeline growth. |
| KPMG-7 | Respondents cite carve-out execution challenges: operational disentanglement 52%, valuation complexity 43%, IT/data separation 40%, talent retention 32%, regulatory hurdles 25%. | 31 | Source chart outcomes, not a forecast of realized failure. |
| KPMG-8 | Software and knowledge-services stocks lost nearly $1T in market value over several weeks in early 2026; the report attributes repricing to changed multiples and AI-shortened confidence in future cash flows rather than collapsing revenues. | 28 | Market repricing and report interpretation, not proof that AI caused realized revenue losses. |

### Reuters Institute

| ID | Source-verified proposition | Source pages | Scope / guardrail |
|---|---|---|---|
| REU-1 | Publishers expect search referrals to decline by an average 43% over the next three years. | 12 (printed 10) | Forward-looking respondent expectation, not realized traffic or a forecast for every publisher. |
| REU-2 | Observed Google Search referral traffic fell year-on-year from Nov. 2024 to Nov. 2025: global 33%, U.S. 38%, Europe 17%. | 12–13 (printed 10–11) | Physical p.12 supports the global and U.S. values; the chart on p.13 adds Europe −17%. Distinct from REU-1. The AI Overviews contribution is unclear. |
| REU-3 | For AI licensing income expected in about three years, 49% expect minor income, 20% significant, 20% none, and 11% do not know. | 15 (printed 13) | Publisher expectations; 69% expect some income. Do not describe 49% as significant. |
| REU-4 | Publishers prioritize original/on-the-ground reporting (+91 net), contextual analysis (+82), human stories (+72), and verification (+63); service journalism is −42 net. | 17 (printed 15) | Net “more minus less” scores, not respondent shares. Community/live events are +76 in the chart and +75 in prose; preserve the discrepancy or omit that number. |
| REU-5 | 75% expect AI browsers/agentic apps to have large or very large impact on publishers over the next three years. | 41 (printed 39) | Prospective impact expectation, not observed outcome. |
| REU-6 | Commercial publishers prioritize subscriptions/membership (76%), display (68%), native advertising (64%), and events (54%) as revenue sources. | 38 (printed 36) | Commercial publishers excluding publicly funded broadcasters. Platform-funding value is 36% in prose and 37% in the chart. |
| REU-7 | 53% of surveyed editors, CEOs and digital executives are confident about their own organization's business prospects; separately, 38% are confident about journalism's prospects for the year ahead. | 6 (printed 4); contrast on 5 (printed 3) | Keep the two outlook measures separate. Strategic sample of 280 digital leaders across 51 countries/territories; not a universal forecast. |
| REU-8 | UK regional publisher Newsquest created more than 30 AI-assisted reporter roles; staff use News Creator to draft up to 30 stories per day, which are checked and supplemented. | 19 (printed 17) | Reported operating example, not measured productivity or proof of 30 publishable stories. Preserve human-check step. |

### Adjust

| ID | Source-verified proposition | Source pages | Scope / guardrail |
|---|---|---|---|
| ADJ-1 | Global gaming: strategy sessions +57% with installs flat; casino installs +22% with sessions −5%; slots installs +46% with sessions −5%. | 19 | YoY 2024–25. Acquisition and engagement are distinct; session declines suggest a churn issue but do not prove churn. |
| ADJ-2 | Global gaming CPI rose 30% to $0.56 in 2025; category maxima include slots at $4.47, idle RPG at $3.19, and strategy at $1.03. | 21 | Preserve each CPI's category. |
| ADJ-3 | Global gaming paid/organic ratio rose from 2.07 to 3.33 (+61%); casino reached 11.05, casual 7.16, and slots 5.63. | 22 | These are ratios, not percentages. |
| ADJ-4 | E-commerce installs fell 10% globally while sessions rose 5%; LATAM was +17% installs/+30% sessions and Europe −22%/+6%. | 27 | Keep global and regional measures separate. |
| ADJ-5 | Finance-app installs fell 4% globally while sessions rose 21%; LATAM was +76%/+57%, MENA +42%/+10%, and APAC +5%/+50%. | 34–35 | Regional pairs are installs/sessions. The report's causal explanation is interpretation, not established by these metrics. |
| ADJ-6 | Average e-commerce app session length declined globally from 10.04 minutes in 2024 to 9.6 minutes in 2025. | 28 | The report says shorter sessions may reflect faster purchasing if conversion holds; shorter sessions alone do not establish churn or lower conversion. |
| ADJ-7 | The global median e-commerce paid/organic acquisition ratio rose from 0.48 in 2024 to 0.54 in 2025. | 30 | Ratios, not percentages. Keep e-commerce separate from the shopping-app ratio and preserve regional divergence. |
| ADJ-8 | Only around 31% of marketers report complete satisfaction with their ability to unify and read data across platforms; the report describes cross-platform measurement connecting journeys such as a mobile-web session to an in-app conversion. | 11 | A marketer-reported measurement limitation and the report's proposed remedy; do not present 31% as the share of customers or as an observed conversion effect. |

The Reuters chart/prose discrepancies above are source inconsistencies, not model errors. Reference matching treats equivalent paraphrases as matches only when the subject, measure, population, period, and direction remain intact.
