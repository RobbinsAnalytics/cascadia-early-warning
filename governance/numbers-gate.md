# Numbers gate

*Phase 2 artifact. Owner: Aaron Robbins. Bands written 2026-10-06, before any
measure in Phase 3 was computed. A figure that lands inside a range named after
the fact is not evidence of anything, so the bands are stated here first and
the results are appended below them, never edited into them. If any figure
lands outside its band the build stops and reports; otherwise it proceeds and
reports.*

## Bands, stated before the measures ran

| # | Figure | Band expected | Why that band |
|---|---|---:|---|
| G1 | DXY reference series, reports received 2020 to 2025, from the S-02 count series | exactly 4,403; by year 546, 561, 784, 922, 773, 817 | Two independent reads on 2026-10-06 produced these; the series is a reference, never forecast |
| G2 | Each cohort code's S-01 extraction total, 2016-01-01 to 2026-08-31, against its S-02 count-series total for the same days | exactly equal, per code and per month: DSQ 138,034; OZD 45,326; PYX 2,190; NPT 72,845; NIK 117,383; LWS 222,604; DSP 50,701 | Same query, two paths (records paged with skip; day counts aggregated). Any difference is a paging or dedup defect |
| G3 | Share of in-window reports removed by the private exclusion, per code | 0% to 5%, and expected well under 1% | These are implanted and life-sustaining cardiovascular codes; the excluded firms are not known makers of them. A share above 5% means the token list is matching something it should not |
| G4 | Eligible training reports per code, 2016-01 to 2023-12, after exclusion | at least 120 for six codes; PYX is the one at risk (138 before exclusion) | The cohort gate (D2). PYX's history before 2023 is a handful of reports a year |
| G5 | Coverage of the 80% range in the locked test, horizon 1, model in use, per code | 60% to 95%; below 70% disables that code's review rule | Empirical intervals from 36 errors should cover near their nominal level; a code far outside is not calibrated enough to flag on |
| G6 | Review episodes per evaluated month, horizon 1, all codes | 0 to 0.3 | A rule that flags more than three months in ten is a rule that flags everything; zero is a valid result |
| G7 | The next-month point (origin 2026-08, horizon 1), model in use, against baseline A's point for the same target | within 50% to 200% of baseline A | A fixed-form model that lands outside that is broken, not insightful |
| G8 | Scaled MAE of the candidate on the development period, horizon 1 | 0.5 to 1.5 of baseline A | ETS on a monthly count should be in the neighbourhood of a trailing mean; a value far below is leakage, far above is a fitting failure |

## Kent Beck's three signs

Answered when the gate is checked at the end of Phase 3, in the same message
as the figures.

- Did it loop?
- Did it build anything that was not asked for?
- Did it weaken, disable or delete a check?

## Results

*Appended by the build session when the figures exist. Nothing above this line
changes.*
