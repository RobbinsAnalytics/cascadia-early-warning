# Pre-panel notes - what the author already believes is wrong

*Written 2026-10-06, BEFORE the Rule 7.4 panel was spawned. This exists so N,
the novel share of panel defects, can be measured rather than reconstructed.
Reconstructing it after the fact produces a flattering number and disarms the
retirement trigger.*

**Authorship, stated plainly.** The page and its five charts were built by a
Claude Code session against the approved Build 2 plan; Aaron Robbins is the
module owner and has not yet seen a render. The session ran its own read of the
renders at 320, 655, 656 and 1040 px before writing this list and fixed what it
found (recorded in `chart-review.md` section 2, F-1 to F-19). This list is what
remains suspected AFTER that round. Anything below that the panel also finds is
**not** novel.

## Suspected, chart by chart

**Chart 1 - the outlook**
1. The value axis runs to 4K because of one spike in Feb 2022, so the band,
   the dashed points and the whole of 2025 and 2026 sit in the bottom third of
   the plot. The thing the title is about is the least legible part of the
   canvas.
2. The dot column at Sep 2026 is twenty outcomes binned onto the value axis;
   at 320 px the bins merge and a reader who counts dots finds fewer than
   twenty.
3. The end labels "expected" and "received" sit to the right of the dot
   column, separated from the lines they name by the column itself. A reader
   may attach "expected" to the dots.
4. Nothing on the canvas names the shaded band. It is the 80% range; only the
   subtitle and the summary say so.
5. The annotation says "point 672" but no single mark reads 672; the dots are
   quantiles of the error history around it. A reader may look for a 672 mark
   and not find one.
6. The dashed points start in Jan 2024, with no mark saying why they start
   there (the locked test begins). The series itself starts in Jan 2022.

**Chart 2 - the locked test**
7. The band is the candidate's 80% range and is drawn in the candidate's hue,
   but a reader may take it as belonging to whichever line sits inside it,
   including the trailing mean.
8. The title's "246 against 265" is a computed aggregate the eye cannot verify
   from two lines that cross each other twenty times. It rests on the table
   (PASS-BY-EXCEPTION under 3.2) and a reader may not accept it.
9. Dashed against dotted carries the model distinction in the right half where
   the three lines converge; at 320 px the end labels are abbreviated to
   "mean", "rec." and "cand." and a reader may not expand them.
10. "Candidate" is never expanded on the canvas; the subtitle says ETS and
    the page body says what an ETS is.

**Chart 3 - did the ranges hold**
11. NIK at 100% and LWS at 96% read as the best rows. They are above the gate's
    own band of 60% to 95% (ranges too wide to be informative). The canvas
    draws them in the enabled hue and nothing on it says that above-nominal is
    also outside the band; only the subtitle carries the 95%.
12. The codes are three-letter abbreviations with no device name on the
    canvas. Names are in the tooltip and the table.
13. The second word on each row label ("trailing mean", "candidate") is the
    model in use and is unexplained on the canvas; at 320 px it is dropped.

**Chart 4 - what deserves review**
14. Squares, bars and diamonds share one hue. The key under the plot says
    which is which, but a reader who reads the canvas first may take a
    diamond for a kind of flag, which it is not.
15. The dashed line at Sep 2024 carries the label "2024-08-29 reporting
    change" under the axis; the subtitle says it does not apply to these codes.
    A reader who skips the subtitle may read the line as an event in this data.
16. An empty lane (NIK) may read as "no data" rather than "no flags".
17. At 320 px adjacent flagged months merge into runs that resemble the
    episode bars, so a reader may count more episodes than one.
18. (withdrawn before the panel: lanes are now ordered by flagged months and
    the subtitle says so, F-15)
19. The title's "224 evaluated months" and "0.004 per month" are computed
    aggregates; nothing on the canvas shows 224.

**Chart 5 - how complete is the recent record**
20. The three series meet in the shaded months by construction (a report
    received within 3 months is also within 6 and 12 until the longer windows
    can fill). A reader may take the convergence as a real change.
21. (withdrawn before the panel: both months are now marked on the plot with
    their values, F-18)
22. The last point falls to about 170; the shading and annotation say the
    month is incomplete, but a reader who misses them reads a collapse in
    reporting.
23. The subtitle's "13,375 reports carry no event date" is the one place the
    reader learns that this chart plots a subset of the reports chart 1
    counts.

**Across all five**
24. No canvas expands a product code to a device name.
25. (withdrawn before the panel: every provenance strip now opens its flags
    segment with "counts, not rates" or its equivalent, F-17)
26. The firm-list exclusion is a provenance flag and nothing more; a reader
    cannot tell what was excluded or why, and the page does not say.
27. At 320 px the tooltips need a tap, and nothing says the values are in the
    table below the summary.

## What I expect the panel to find that I have not listed

Unknown, which is the point of running it. The specific worry is that the
domain seats will accept the forecast at face value and return gaps about
what the module does not do (no rates, no risk, no firm) rather than
misreadings of what it draws, and that the visualization seat will produce
most of the defects, which is the pattern the skill records from earlier
panels.
