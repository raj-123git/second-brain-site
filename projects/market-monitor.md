# Market monitor and scheduled accumulation

A personal market-monitoring and scheduled-accumulation agent: eleven scheduled jobs on a small Linux server, running since April 2026. Deterministic scripts score a five-component market regime daily from free public data, apply a long-term trend filter to a watchlist, snapshot a paper portfolio, and write a graded weekly review to my phone. Anything touching real money executes only after an approval reply from me; an unanswered request expires after two hours and places nothing. A file-based kill switch is checked at every point on the order path, and the self-heal loop may restart monitoring jobs but never the money path.

From [rajranpariya.com](https://rajranpariya.com/#artifact-market-monitor). Personal tooling; mechanism only, no data.
