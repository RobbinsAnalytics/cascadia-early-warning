# Chart review - Cascadia Early Warning

*Visual layer, five detailed charts on one page. Owner: Aaron Robbins.*
*First review 2026-10-06, by the build session, before any render was shown
to Aaron. First build, so one panel; a revision gets the gate and a link.*

**Binding standard, confirmed on disk and quoted by version:**

| Document | Version | Path |
|---|---|---|
| `VIZ-PRINCIPLES.md` | **v2.8** | `cascadia-standards/design-system/` |
| `CHART-REVIEW.md` | **v2.8** (companion to VIZ-PRINCIPLES v2.8) | `cascadia-standards/design-system/` |

The repo copies are canonical and are what this build was reviewed against
(decision record D15).

**Quadrant: EXPLANATORY. Checklist A applies in full.** No reader controls of
any kind: no filters, selectors or tabs. Every finding is fixed in a title
computed at build time. Tooltips exist above 768 px and move no finding.

**Chart class: all five are detailed charts**, read for values. No signature
charts.

**The decision (Rule 0.1), as the page states it:** whose: the owner of a
post-market review queue; horizon: one month, with three as context;
literacy: a reader who works in spreadsheets and reads a trend line, not a
statistician; benchmark: the trailing three-month mean; cadence: monthly as
the source loads; action: open a review or do not.

**Widths reached (K6):** 320, 655, 656 and 1040 px viewports. The page
declares one breakpoint, 560 px, measured on the chart element's own width;
`src/render_charts.py` binary-searched the viewport at which each chart's
host crosses it and found **656 px for all five charts** (host 559 px at 655,
560 px at 656), so the ladder is 320, 655, 656, 1040. Recorded in
`docs/renders/k6-ladder.json`. At 320 px the chart element is 280 CSS px,
below the 320 px floor the theme declares; the charts are read at it anyway.

---

## 0 · READING PANEL (Rule 7.4) - 2026-10-06

```
READING PANEL - Cascadia Early Warning, five charts - 2026-10-06
Decision served (Rule 0.1): the owner of a post-market device review queue
  choosing, monthly, which product codes are reporting as expected and which
  deserve a closer look. Horizon: one month, with three as context. Benchmark:
  the trailing three-month mean. Action: open a review or do not.
Charts panelled: 5   States: default only (the page has no reader controls)
Nature: simulated

  Seat 1  Post-market surveillance manager at a manufacturer of Class III
          cardiovascular devices, 14 years; owns the complaint-handling and
          MDR review queue - simulated - why this seat: she is the owner of
          the decision. She opens the review or does not, and she decides
          it on whether a jump in reports is a product signal or a reporting
          artefact, and on whether her team can clear the queue this month.
  Seat 2  Senior demand-planning analyst at a medical device distributor,
          11 years; signs off on whether a model's back-test is honest
          before the business may use its numbers - simulated - why this
          seat: the decision rests on trusting a forecast, and he is the
          person who says whether the locked test could have been rigged
          and whether a stated range means what it says.
  Seat 3  Director of Quality Systems at a mid-sized device maker, 20 years
          in QA and RA; not an analyst; presents at management review and
          sits across from auditors - simulated - why this seat: the
          decision has to be defensible in a management review, and she is
          the one who asks where a public-data number came from and what
          it leaves out. She also sits where the room's actual literacy
          sits; the other two would flatter the artifact.
  Seat 4  visualization reader - simulated - canvas only; tables and the
          text under the plot excluded by instruction

Blindness asserted: design system [x] · review and build notes [x] ·
                    source data [x] · intended finding from outside the
                    artifact [x] · other seats' output [x]
Blind: NOT CERTIFIED. Each seat was spawned as a separate agent in a single
message, given the ten PNG paths and told to open nothing else on the
machine; transport was not measured, so blindness and parallelism are
self-attestation, as Rule 7.4 says they always are.
Run: parallel [x]   Author's pre-panel notes recorded: [x]
                    (governance/pre-panel-notes.md, 27 suspicions, three
                     withdrawn as fixed before spawning, written before any
                     seat existed; required to compute N)

Widths given to every seat: 1040 px viewport (chart element 1000 CSS px)
                       AND   320 px viewport (chart element 280 CSS px).
Seats were told the second set was "as it appears on a phone" and asked to
say where the two differed. The 655 and 656 px K6 renders were not given.
```

### Per-seat returns

Verbatim, not tidied, with one mechanical exception: the seats wrote em dashes, and this
repository's em-dash gate covers every tracked file, so each em dash in a quote is shown as
a spaced hyphen. No word was changed. Seats 1 to 3 answered the four questions; seat 4
answered its six, mapped here as SENTENCE (what it is about), NUMBER (item
6), QUESTION (what it was asked to take on faith), GAP (what was hard to
read). Each seat also reported where the phone render differed; those
remarks are quoted in the disposition where they became findings.

**Seat 1 · Post-market surveillance manager**

| Chart | Item | Verbatim |
|---|---|---|
| 1 | sentence | *"Someone has built a forecast for how many DSQ reports we'll get in September, and it says about 670 give or take a lot, which honestly is roughly what we've been running since the middle of 2024."* → carries the title's claim: **yes** |
| 1 | number | *"672 for September, and I got it from the title, and again from the blue annotation on the right that says 'point 672'. If I'd had to read it off the chart itself I'd have said 'the dots on the right sit a bit under 1K on the left axis', which is a worse number. The 329 to 838 range is also in the title, not something I could read off the dots."* - located at: **title and annotation; not a mark** |
| 1 | question | *"Who decided the model, and when - the subtitle says 'ETS candidate', so is this still a candidate or is it the one we're meant to be running on? ... that spike around mid-2024 to over 2K sits well outside the shaded band - is that the kind of thing this is supposed to catch, or is that the kind of thing it misses?"* |
| 1 | gap | *"I looked for what 'eligible' means and for how many reports were thrown out by the 'one firm-list exclusion' the source line mentions. I also wanted to see the actual September number to compare against ... then I want to know when it will."* |
| 2 | sentence | *"Over the two-year test period the fancy model was only a little better than just averaging the last three months, and both of them completely missed the May 2024 spike."* → **yes** (the comparison; the 246 and 265 came from the title) |
| 2 | number | *"The May 2024 miss: 2,237 arrived against 749 expected. That's from the orange annotation at the top of the chart with the vertical line pointing down at the peak."* - **annotation with leader** |
| 2 | question | *"If the trailing three-month mean gets within 20 reports a month of the candidate, why are we using the candidate? What does it buy us?"* |
| 2 | gap | *"I looked for how many months were outside the band, and in which direction. The subtitle says 92% covered, so two months missed - May 2024 is one, and I couldn't tell which the other was. I also couldn't tell whether the band is the thing that generates a review flag or just a descriptive ribbon."* |
| 3 | sentence | *"The forecast ranges work for four of the seven codes and fall apart on three, and those three have been switched off."* → **yes** |
| 3 | number | *"PYX at 33% of 24 months - that's the bottom bar, read from the label at the end of the bar"* - **data label on a mark** |
| 3 | question | *"For NPT, OZD and PYX, what are we doing instead? 'Rule off' means nobody is looking at those codes through this system - are they being reviewed by hand, or not at all? And: a few of these say 'trailing mean' and a few say 'candidate' in the row labels - so different codes are on different models? That needed saying up front."* |
| 3 | gap | *"I looked for the number of months, not just the percentage ... I also looked for which of the three disabled codes had the most reports, because a disabled rule on a high-volume code matters more than on a quiet one, and nothing here tells me volume."* |
| 4 | sentence | *"Across seven codes and two and a half years the review rule only ever triggered once, on DSP at the turn of this year, and meanwhile there were two dozen Class I recalls that it mostly didn't line up with."* → **yes** |
| 4 | number | *"One episode in 224 evaluated months - from the title - and the detail from the orange annotation: DSP, Dec 2025 to Jan 2026, 1,751 arrived against 678 expected."* - **title and annotation** |
| 4 | question | *"Is one episode in 224 months the intended sensitivity? Because from where I sit, a rule that fires once in two and a half years across seven codes isn't a review queue, it's a smoke alarm with the battery out. And ... PYX and OZD have squares all over the lane but they're 'rule off' - so those flags don't count, they're just drawn?"* |
| 4 | gap | *"I couldn't tell from the picture whether the recall dates tended to come before or after the flagged months. I also looked for how many Class I recalls fell in a flagged month and didn't find it."* |
| 5 | sentence | *"When you count DSQ reports by when the event happened and only count the ones that arrived within three months, May this year is down about 15% on May last year - and the drop-off at the far right is just reports that haven't arrived yet, not a real decline."* → **yes** |
| 5 | number | *"May 2026: 577, against May 2025: 680. Both from the green labels sitting right next to the two dots on the dark green line."* - **data labels on marks** |
| 5 | question | *"13,375 reports with no event date - is that normal for this code, and is that share rising?"* |
| 5 | gap | *"I looked for a plain statement of what the typical lag is ... I also couldn't find why the 'within 12 months' grey line has spikes (Jan 2022, Jan 2024) that the 3-month line doesn't"* |

**Seat 2 · Senior demand-planning analyst**

| Chart | Item | Verbatim |
|---|---|---|
| 1 | sentence | *"It's a monthly count of DSQ reports going back to 2022 with a one-step-ahead forecast and band laid over the last couple of years, and the call for September is 672 with an 80% range that's wide enough to be honest, 329 to 838."* → **yes** |
| 1 | number | *"672 for September, and 329 to 838 - from the headline, and repeated in the annotation beside the stack of dots ... I could not have read 672 off the dots themselves; the dot stack sits between roughly 300 and 1,300 on the left axis and I'd have guessed the middle one at about 700."* - **title and annotation; not a mark** |
| 1 | question | *"The band only starts at Jan 2024 - what was the model doing before that, and was anything about the fit touched after it saw 2024 onward? The title says 'candidate', which to me means not yet the model of record, so who decides when it graduates?"* |
| 1 | gap | *"A scale on the dots. Twenty dots are supposed to be a quantile spread but there is no marker telling me which dot is the 10th percentile and which is the 90th, so the '80% range' in the headline is a number I have to take from the text, not the picture."* |
| 2 | sentence | *"On a 24-month holdout they locked before running it, the new model beats a three-month trailing mean by a small margin, 246 versus 265 a month, and its 80% band caught 22 of the 24 months."* → **yes** |
| 2 | number | *"The largest miss, May 2024, 2,237 against 749, is the annotation in orange over the spike with a vertical rule down to the dashed point; I could read the spike as a bit over 2K on the left axis and the dashed line below it at roughly 750."* - **annotation and marks** |
| 2 | question | *"'Selection was frozen at 2023-12 and this test ran once' - that is the sentence I care about, and I want to see what evidences it. Is there a commit, a signed file, a date-stamped config? A chart saying 'ran once' is a claim, not a proof. Also: 92% coverage with a mean band width of 1,107 on a series that mostly sits between 600 and 1,300 - the band is nearly the size of the signal."* |
| 2 | gap | *"I looked for the trailing mean's coverage or its band. There's a grey dotted line for it but no range, so the 92% is only comparable to itself."* |
| 3 | sentence | *"The 80% bands worked for four of seven product codes and badly failed for three - PYX only caught a third of months - so the review rule is switched off for those three."* → **yes** |
| 3 | number | *"33% for PYX, the bottom bar, labelled '33% of 24 months, rule off' on the end of the bar; the bar itself ends just past the 30% tick on the bottom axis. And 71% for DSP, whose bar ends right on the orange 'rule disabled below 70%' dashed line - I had to look twice to confirm it's on the right side of it."* - **data labels and marks** |
| 3 | question | *"DSP is at 71% and the cut-off is 70%. That's one month out of 24 ... Was 70% set before the coverage numbers were seen? The subtitle says the gate 'expected 60% to 95%' - so why is the disable line at 70 and not 60?"* |
| 3 | gap | *"for 5 of 7 codes the model 'in use' is the dumb one, and the chart doesn't say why. Also NIK at 100% of 24 months - that's a band that never misses, which usually means the band is too wide, and there's no width shown."* |
| 4 | sentence | *"Over two and a half years across seven codes the alert rule fired exactly once as a real episode, DSP in Dec 2025 - Jan 2026, and the chart also drops Class I recall dates on the same lanes, with a warning that the two are not being claimed as connected."* → **yes** |
| 4 | number | *"1 episode in 224 evaluated months, 0.004 per month - headline. The 1,751 arrived against 678 expected for that episode is the orange annotation above the DSP lane, pointing at the shaded pair of squares around Jan 2026. The 24 Class I recalls I could only count from the paragraph below; I did not count diamonds."* - **title and annotation** |
| 4 | question | *"the three codes with the most flagged months - PYX 10, OZD 9 - are the ones where the rule is off. So the chart shows the noisiest lanes and then tells me they're switched off. What is the chart actually asking me to review? And 'exceeded the 80% range by five or more reports' - where did 'five' come from?"* |
| 4 | gap | *"every mark is 'actual exceeded the range', so there's no mark for coming in under. Is that by design? ... I couldn't tell what a diamond sitting on top of a square means (PYX Feb 2026, DSQ Jun 2024) - same month, or just overlap."* |
| 5 | sentence | *"This is a data-maturity chart - it counts DSQ reports by when the event happened rather than when FDA received them, at three lag cut-offs, and says the recent months look low only because the reports haven't come in yet."* → **yes** |
| 5 | number | *"May 2026: 577 within three months versus May 2025: 680 - headline, and the two labelled dots on the green line near the right side of the plot, roughly at 600 and 700 on the left axis."* - **data labels on marks** |
| 5 | question | *"A quarter of the reports have no event date and are 'counted beside the chart, not in it.' Are they in the forecast in chart 1?"* |
| 5 | gap | *"if May 2026 at 577 is a fair three-month figure then Jun/Jul/Aug 2026 can't be, and the shading starts at Sep 2025 which doesn't match 'three months'. I also couldn't read the difference between the 'within 6' and 'within 12' lines - two greys, one dashed, sitting on each other."* |

Seat 2, across all five: *"every number I'd repeat came from a title,
subtitle, annotation or the paragraph below the chart. None came from
reading an axis. That is fine for a reader; it's less fine for an auditor,
because the picture never let me check the text."*

**Seat 3 · Director of Quality Systems**

| Chart | Item | Verbatim |
|---|---|---|
| 1 | sentence | *"Somebody has built a forecast off openFDA MDR counts for one product code, DSQ, and is telling us to expect roughly 670 reports in September with a band that is wide enough to drive a truck through."* → **yes** |
| 1 | number | *"672, with the 80% range of 329 to 838. I got it from the title line at the top, and it is repeated in the blue annotation ... I could not have read 672 off the axis; the right-hand dots sit somewhere between the 0 and 1K gridlines and that is as close as the plot itself gets me."* - **title and annotation; not a mark** |
| 1 | question | *"What is DSQ, and why this code? If this is going on a management-review slide I need to know whether it covers our products or a competitor's, and 'DSQ' by itself means nothing to the executive team."* |
| 1 | gap | *"There is also no explanation of the big spike in early 2022 near 2.8K ... And 'one firm-list exclusion applied' in the source line is doing a lot of work with no detail; an auditor would stop on that."* |
| 2 | sentence | *"On a two-year hold-out the fancy model beat a three-month trailing average by about 19 reports a month, which is not a lot, and both of them completely missed the May 2024 spike."* → **yes** |
| 2 | number | *"The largest miss: May 2024, 2,237 arrived against 749 expected. That is the orange annotation at the top left of the plot, with a vertical orange line dropping to the May 2024 tick. I can also see the green peak reaching just above the 2K gridline on the left axis, which agrees with it."* - **annotation and mark** |
| 2 | question | *"If the trailing mean gets 265 and the candidate gets 246, why are we carrying the model at all?"* |
| 2 | gap | *"I was looking for a mark on the two months that fell outside the band and did not find one. And I looked for a statement of what 'selection was frozen at 2023-12' actually means in practice, which is the thing an auditor would want evidence of."* |
| 3 | sentence | *"For four of seven product codes the forecast ranges held up well enough to use; for three they did not and the review rule has been switched off for them."* → **yes** |
| 3 | number | *"PYX at 33% of 24 months, rule off. That is the label on the end of the bottom bar, and the bar itself ends just past the 20% tick on the bottom axis, between 20 and 40."* - **data label and mark** |
| 3 | question | *"Who decided 70% was the cut-off, when was that decided, and was it before or after these results came in? If the threshold was set after seeing the numbers I cannot defend it."* |
| 3 | gap | *"I looked for the number of months, not just the percentage ... what happens to the three rule-off codes now; are they being watched by anything, or just dropped? ... 'trailing mean' versus 'candidate' in the row labels tells me different codes are on different models with no explanation of why."* |
| 4 | sentence | *"Over two and a half years and seven codes this review rule has produced exactly one thing worth looking at, DSP in December 2025 into January 2026, and I am not sure that is a sign the rule works or a sign it is tuned too quiet."* → **yes** |
| 4 | number | *"1 episode in 224 evaluated months, 0.004 per month, from the title. On the chart it is the shaded pair of squares on the DSP lane under Feb 2026, with the orange annotation above saying 1,751 arrived against 678 expected."* - **mark and annotation** |
| 4 | question | *"If the rule flagged nothing before any of the 24 Class I recalls, I want someone to say plainly whether that is the expected outcome or a failure, because the first thing anyone in the room will do is try to line up squares and diamonds."* |
| 4 | gap | *"Twenty-four Class I recalls ... the chart gives me no denominator for it ... I also could not tell how many of the 30 flagged months fell in the three 'rule off' lanes, where presumably a flag means nothing; by my count from the paragraph it is 22 of 30, which rather changes the title. And the vertical dashed line is explained as a reporting change 'which does not apply to these codes', which raises the question of why it is on the chart at all."* |
| 5 | sentence | *"This is the one that tells you not to panic about the recent drop: reports take months to arrive, so you can only compare months on the same reporting window, and May 2026 at 577 is down from May 2025 at 680 on a like-for-like three-month basis."* → **yes** |
| 5 | number | *"May 2025: 680 and May 2026: 577. Both are the labelled green dots on the 'within 3 months' line, near the 500-to-1K band on the left axis, and both are also in the title."* - **data labels on marks** |
| 5 | question | *"13,375 eligible reports with no event date ... Are those spread evenly across the years, or are they concentrated somewhere that would move these lines?"* |
| 5 | gap | *"the chart does not say how many months of the three-month line are themselves incomplete; the subtitle only speaks to the 12-month figure. I also looked for which grey line was which ... the two grey series are hard to tell apart."* |

Seat 3, general: *"What none of them tell me is what DSQ, DSP, NIK and the
rest are in plain words, and whether any of these codes are ours. Until I
know that I cannot say which, if any, of these belongs in a management
review."*

**Seat 4 · Visualization reader**

| Chart | Item | Verbatim |
|---|---|---|
| 1 | sentence | *"a monthly count series ... with a dashed blue 'model' line and a pale band tracking it from Jan 2024, and a vertical column of blue dots at the far right that looks like a forecast distribution for the next month."* Title: *"Same picture. The title is more specific than the plot."* → **yes** |
| 1 | number | *"The early-2022 peak: the green line's highest point ... just under the 3K tick, about 2.8K. The headline 672 is not readable from the plot; it comes from the annotation."* - **mark and axis; the headline figure not a mark** |
| 1 | on faith | *"'80% range of 329 to 838': NOT shown. The dot column spans visibly wider than that, roughly 200 to 1,250 against the axis ... the 80% range is not marked inside them."* |
| 1 | hard to read | *"The 'expected' / 'received' labels sit directly beside the dot column ... On first look I read them as labelling the dots ... Y ticks at 1K intervals for a series that lives between 600 and 1,400 ... X-axis ticks are 8 months apart"* |
| 2 | sentence | *"two models vs actual on a test window, with the worst miss called out."* Title: *"The title is about average error. The plot shows the raw series, not errors. That is a real gap"* → **partly** (the comparison, not the figures) |
| 2 | number | *"May 2024 actual: the green peak at the May 2024 tick, just above the 2K line, about 2.2K. The expected for that month: the dashed line's dip at the same tick, about 750. Both readable. The title's 246 and 265 are not."* - **marks** |
| 2 | on faith | *"'246' and '265': NOT visible ... an 8% difference in average error is invisible in this form"* |
| 2 | hard to read | *"The grey dotted line on the pale band is the faintest element and is the one the title compares against. The three end-labels ... are stacked at the right and the lines converge there"* |
| 3 | sentence | *"a ranked horizontal bar chart, seven rows, values from 33% to 100%, two dashed reference lines at 70% and 80%, the three lowest bars in orange tagged 'rule off'"* → **yes** (*"Matches"*) |
| 3 | number | *"NIK 100%: the top bar ends exactly on the 100% axis tick. Readable from the bar alone."* - **mark on the axis** |
| 3 | on faith | *"'locked-test months', '80% ranges': on faith (labels say 'of 24 months', which is the only trace)"* |
| 3 | hard to read | *"The dashed lines run through the value labels ... Row labels carry a second variable ('trailing mean' / 'candidate') with no explanation on the plot ... DSP at 71% versus a 70% cut: the bar end and the line nearly coincide"* |
| 4 | sentence | *"a seven-lane event timeline ... Reads as 'when did each code trip a flag, and when did recalls happen'."* Title: *"the title is a count and a rate; the plot is a timeline you have to count from."* → **yes** |
| 4 | number | *"PYX flagged months: 10, counted as ten filled squares along the top lane ... Readable. The '1,751 against 678' in the annotation is not on the plot."* - **marks** |
| 4 | on faith | *"PYX has adjacent squares at Jan-Feb 2024 and OZD has four consecutive squares Jan-Apr 2024. By the subtitle's own definition ... those look like episodes with no box ... counting diamonds off the plot I get about 21 ... Same-month recalls appear to overprint"* |
| 4 | hard to read | *"Diamond-over-square composites ... The OZD mark at the dashed line (Aug 2024) is half hidden behind it ... no on-plot key ... The episode annotation sits at the top of the plot, two lanes above the DSP box, with no leader."* |
| 5 | sentence | *"three nested lines ... a shaded zone over roughly the last 12 months, the green line plunging in the final two or three months, and two labelled dots a year apart. Reads as a reporting-lag / completeness chart"* → **yes** (*"Matches"*) |
| 5 | number | *"May 2025: 680. The dot on the green line at the May 2025 axis tick, between the 500 and 1K ticks, labelled. Readable, and the only chart of the five where the headline numbers are physically on the plot."* - **mark with data label** |
| 5 | on faith | *"the May 2026 dot sits inside the shaded 'incomplete' zone ... The title then uses one of those months as a comparable figure ... The plot does not say that."* |
| 5 | hard to read | *"'within 6' (grey dashed) and 'within 12' (grey solid) are hard to separate anywhere except the spikes ... The green plunge to ~170 ... is an artefact; the annotation addresses it but sits at the top-right, away from the plunge"* Grayscale: *"Weak. Green solid and grey solid become two solid greys of similar weight."* |

Seat 4, across all five: *"Three of five titles lead with numbers that are
not on the plot ... c2 is the one real form/claim mismatch: an
average-error comparison drawn as fitted lines ... Grayscale: c1, c2, c3, c4
survive; c5 is the only one whose line encoding does not."*

### Disposition

Pooled and deduplicated; sorted by seat count, then chart. Convergence drives
the fix order: four blind readers in the same hole from four directions
outranks one eloquent objection. "Novel" means absent from
`governance/pre-panel-notes.md`, which was written before any seat was
spawned. The machine-readable record is `governance/panel/findings.json`.

| # | Finding, in the reviewer's words | Seats | n | Chart | Defect? | Novel? | Disposition | Rule |
|---|---|---|---|---|---|---|---|---|
| 6 | *"The title is about average error. The plot shows the raw series, not errors ... a reader who trusts the picture over the words will come away with 'both models look about the same'"* | 1,2,3,4 | **4** | 2 | yes | no | **fixed**: the title now leads with what the picture carries ("the candidate's 80% range held 22 of 24 DSQ months") and keeps the error figures as the second clause, a computed aggregate the table carries; the two months outside the band are ringed | 3.2 |
| 9 | *"Row labels carry a second variable ('trailing mean' / 'candidate') with no explanation on the plot ... on a phone you'd not know DSQ is on a different model to NIK"* | 1,2,3,4 | **4** | 3 | yes | no | **fixed**: the subtitle says what the row label names and why; at 320 px the label keeps a declared abbreviation ("DSQ cand.", "NIK mean") instead of dropping it | 3.6 |
| 11 | *"PYX has adjacent squares at Jan-Feb 2024 and OZD has four consecutive squares ... those look like episodes with no box ... by my count from the paragraph it is 22 of 30, which rather changes the title"* | 1,2,3,4 | **4** | 4 | yes | **yes** | **fixed**: flagged months in a lane with the rule off are drawn hollow; lanes with the rule on come first; the subtitle states that 22 of the 30 flagged months fall in the three rule-off lanes and that a hollow square opens no episode | 3.2 |
| 16 | *"The x-axis collapsed to just 'Jan '22' and 'Sep '26', so I could no longer find the 2024 spike by date ... Axis labels collide: 'Jan '24Nov '24' runs together"* | 1,2,3,4 | **4** | 1, 2, 4, 5 | yes | **yes** | **fixed**: at the narrow width tick density is a declared rule keyed to the plot width (at least three labels, first and last and evenly spaced between, never closer than 64 px) in place of the renderer's thinning, which had left two labels touching | K4 |
| 17 | *"The 'rule off' tags disappeared from the lane labels, so on the phone there is no indication which lanes are disabled"* | 1,2,3,4 | **4** | 4 | yes | **yes** | **fixed**: narrow lane labels keep "off" as a declared abbreviation, and the hollow squares carry the distinction in the marks | 5.5 |
| 18 | *"The lanes compressed so hard that squares and diamonds overlap; on OZD and DSQ I could not separate them"* | 1,2,3,4 | **4** | 4 | yes | no | **accepted**: 32 months across 7 lanes in 280 CSS px cannot show every mark apart. Marks are smaller and diamonds are raised off the lane line at that width; the per-lane counts are in the summary and the table, and the chart does not change what it shows by width (K6). Recorded as the limit of this form on a phone | 5.5 |
| 20 | *"'within 6' (grey dashed) and 'within 12' (grey solid) are hard to separate ... Green solid and grey solid become two solid greys of similar weight"* | 1,2,3,4 | **4** | 5 | yes | **yes** | **fixed**: the three windows now differ by dash as well as hue (12 months long-dash, 6 months dotted, 3 months solid), so grayscale keeps the distinction | 5.4 |
| 41 | *"The legend became 'exp.' and 'rec.', which I had to think about for a second ... 'mean' on its own is ambiguous"* | 1,2,3,4 | **4** | 1, 2, 5 | yes | no | **accepted**: a declared abbreviation mapping is what 5.5 asks for where the full label does not fit beside a 150 px plot; the subtitle names both series in full and the note under the plot repeats the figure. The alternative, dropping the label, is the 2.3.6 failure F-14 removed | 5.5 |
| 1 | *"'80% range of 329 to 838': NOT shown. The dot column spans visibly wider than that ... the 80% range is not marked inside them"* | 1,2,4 | **3** | 1 | yes | **yes** | **fixed**: dots inside the 80% range are filled and those beyond it hollow, a tick marks the point, a thin rule spans the range, and the annotation says so ("point 672 is the tick; filled dots span the 80% range, 329 to 838"); the twenty dots are stepped sideways within a bin so all twenty are countable | 3.2 |
| 3 | *"Y ticks at 1K intervals for a series that lives between 600 and 1,400 ... nothing between 0 and 1K to read against"* | 2,3,4 | **3** | 1, 2, 5 | yes | no | **fixed**: the derived tick interval targets seven ticks instead of five (500 on chart 1, 500 on chart 2, 250 on chart 5) | K4 |
| 7 | *"The grey dotted line on the pale band is the faintest element and is the one the title compares against"* | 1,2,4 | **3** | 2 | yes | no | **fixed**: the Rain dotted line is 2.5 px; it keeps its direct label at every width | 2.3.6 |
| 19 | *"the May 2026 dot sits inside the shaded 'incomplete' zone ... The title then uses one of those months as a comparable figure ... The plot does not say that"* | 2,3,4 | **3** | 5 | yes | **yes** | **fixed**: two shadings, the last 3 months darker (every window still filling) over the last 12 lighter (only the 12-month figure), and the subtitle and annotation say which is which | 4.1 |
| 33 | *"A quarter of the reports have no event date and are 'counted beside the chart, not in it.' Are they in the forecast in chart 1?"* | 1,2,3 | **3** | 5 | yes | no | **fixed**: the subtitle says they are counted in charts 1 to 4 by receipt month and left out of this chart only | 4.3 |
| 4 | *"What is DSQ, and why this code? ... 'DSQ' by itself means nothing to the executive team"* | 1,3 | **2** | 1 | yes | no | **fixed** on chart 1, whose subtitle now carries the FDA device name beside the code; charts 3 and 4 keep the codes on their row and lane labels, where seven device names will not fit, and carry the names in the tooltip and the table | 4.3 |
| 5 | *"The band from Jan 2024 is described in the subtitle as an 80% range but has no on-plot legend entry"* | 2,4 | **2** | 1 | yes | no | **fixed**: a subordinate label "80% range from Jan 2024" at the band's first month, reading leftward over the empty months before it | 3.6 |
| 8 | *"The dashed lines run through the value labels: '71% of 24 months' has the 80% line through 'of'"* | 1,4 | **2** | 3 | yes | no | **fixed**: the reference lines are drawn beneath the bars by a custom series and the value labels carry a paper background, so a label masks the line behind it; F-9 had given the labels the background without moving the lines under them | K3 |
| 12 | *"counting diamonds off the plot I get about 21 ... Same-month recalls appear to overprint as one diamond, so 24 cannot be reached from the plot"* | 2,4 | **2** | 4 | yes | **yes** | **fixed**: diamonds are raised above the lane line and same-month events step sideways, so all 24 are drawn apart and a diamond no longer prints over a square | 3.2 |
| 15 | *"the vertical dashed line is explained as a reporting change 'which does not apply to these codes', which raises the question of why it is on the chart at all"* | 3,4 | **2** | 4 | yes | no | **fixed**: the line is gone from the canvas; the subtitle keeps the one sentence a reader who knows the FDA change needs | 3.4 |
| 23 | *"The 'largest miss' annotation moved below the chart, so the peak had no label next to it, and the little orange vertical line was still there but now unexplained until I scrolled"* | 1,3 | **2** | 2 | yes | **yes** | **fixed**: at the narrow width the mark keeps a two-word label, "largest miss", and the full annotation stays as the note under the plot | 5.5 |
| 24 | *"I looked for what 'eligible' means and for how many reports were thrown out by the 'one firm-list exclusion'"* | 1,3 | **2** | 1 | yes | no | **fixed**: the provenance flag now carries the receipt's count, "the firm-list exclusion removed 1 of 649,083 reports" | 4.3 |
| 25 | *"The subtitle says 92% covered, so two months missed - May 2024 is one, and I couldn't tell which the other was"* | 1,3 | **2** | 2 | yes | **yes** | **fixed**: the months outside the band are ringed, and the subtitle says the rings mark them | 3.2 |
| 27 | *"Who decided 70% was the cut-off, when was that decided, and was it before or after these results came in?"* | 2,3 | **2** | 3 | yes | no | **fixed**: the subtitle states that the gate band and the 70% line were written before the test ran; the pre-registration commit is the page's evidence | 4.3 |
| 28 | *"I looked for the number of months, not just the percentage ... '33% of 24 months' I can turn into 8 myself, but I should not have to"* | 1,3 | **2** | 3 | yes | **yes** | **fixed**: the value label reads "33%: 8 of 24 months, rule off" at the design width | 2.9 |
| 32 | *"I couldn't tell from the picture whether the recall dates tended to come before or after the flagged months. I also looked for how many Class I recalls fell in a flagged month"* | 1,3 | **2** | 4 | yes | no | **fixed**: the subtitle carries the pre-registered count, "Of the 24 Class I initiations, 0 were preceded by an episode start" | 4.3 |
| 29 | *"For NPT, OZD and PYX, what are we doing instead? 'Rule off' means nobody is looking at those codes through this system"* | 1,3 | **2** | 3 | no | - | **rejected** as a chart defect: it is a question about policy, not a misreading. The page body now answers it in one sentence ("A code with the rule off is not reviewed by this module, and nothing here stands in for it"), because the seats were right that the page had not said so | - |
| 37 | *"A chart saying 'ran once' is a claim, not a proof"* | 2,3 | **2** | 2 | no | - | **rejected**: the proof is the git log, which the page's chronology section and the validation report cite; a canvas cannot carry a commit history, and the seat's reaction is the argument for keeping that section prominent | - |
| 39 | *"a rule that fires once in two and a half years across seven codes isn't a review queue, it's a smoke alarm with the battery out"* | 1,3 | **2** | 4 | no | - | **rejected**: that is the finding, not a defect. The pre-registration's chance rate (about one episode per hundred evaluated months) is on the page beside the observed 0.004, and the chart reports the result the rule produced rather than a flattering one | - |
| 2 | *"On first look I read them as labelling the dots (upper dots = expected, lower = received), not the two lines"* | 4 | 1 | 1 | yes | no | **fixed**: the dot column is drawn outside the time axis by a custom series, so the end labels sit at their lines' ends with nothing between them | 3.6 |
| 10 | *"NIK at 100% of 24 months - that's a band that never misses, which usually means the band is too wide, and there's no width shown"* | 2 | 1 | 3 | yes | no | **fixed**: the gate's expected band, 60% to 95%, is shaded under the bars and the two bars beyond it are labelled "above the gate band" | 3.2 |
| 14 | *"The episode annotation sits at the top of the plot, two lanes above the DSP box, with no leader"* | 4 | 1 | 4 | yes | **yes** | **fixed**: lanes with the rule on come first, ordered by flagged months, so the episode's lane is the first lane, directly under the annotation's headroom | 3.4 |
| 22 | *"The annotation moves below the plot and is set in green while the dots it describes are blue, so the colour link is lost"* | 4 | 1 | 1 | yes | **yes** | **fixed**: the note under chart 1 takes the Glacier text ink | 3.3 |
| 26 | *"I also couldn't tell whether the band is the thing that generates a review flag or just a descriptive ribbon"* | 1 | 1 | 2 | yes | no | **fixed**: the subtitle states the rule ("flags a month above the band by five or more reports") | 4.3 |
| 21 | *"The green plunge to ~170 ... is an artefact; the annotation addresses it but sits at the top-right, away from the plunge"* | 4 | 1 | 5 | yes | no | **accepted**: anchoring the annotation at the plunge put it over the compared-month labels (K3); it sits at the top of the shaded zone it names, directly above the plunge, and the darker shade now covers the plunge itself | 3.4 |
| 13 | *"There is no on-plot key for square / diamond / shaded box; it lives in the subtitle"* | 4 | 1 | 4 | no | - | **rejected**: the key is the line of flat text directly under the plot inside the chart card, which this seat was instructed to ignore; it travels with the card. The subtitle also defines every mark | 3.6 |
| 30 | *"every mark is 'actual exceeded the range' ... Is that by design? ... where did 'five' come from?"* | 2 | 1 | 4 | no | - | **rejected**: both are pre-registered (`governance/pre-registration.md`) and the subtitle now says the rule is one-sided by design; the origin of the five-report floor is the page body's to explain, not the canvas's | - |
| 31 | *"Twenty-four Class I recalls ... the chart gives me no denominator for it"* | 3 | 1 | 4 | no | - | **rejected**: a denominator would make a rate, which this module refuses on the record (CLAUDE.md constraint 2); the count is context, and the subtitle says so | - |
| 34 | *"why the 'within 12 months' grey line has spikes (Jan 2022, Jan 2024) that the 3-month line doesn't"* | 1 | 1 | 5 | no | - | **rejected**: the chart shows the late-arriving batches that cause them; explaining their cause is outside what the data can say and the module does not claim it | - |
| 35 | *"that spike around mid-2024 ... is that the kind of thing this is supposed to catch, or the kind of thing it misses?"* | 1 | 1 | 1 | no | - | **rejected**: chart 4 answers it (May 2024 is a flagged month for DSQ); a question across charts, not a misreading of this one | - |
| 36 | *"I also wanted to see the actual September number to compare against ... then I want to know when it will"* | 1 | 1 | 1 | no | - | **rejected**: the subtitle says the source had not loaded it; scoring each issued forecast as its month elapses is the live edge (Phase 5), held for Aaron | - |
| 38 | *"I looked for the trailing mean's coverage or its band. There's a grey dotted line for it but no range"* | 2 | 1 | 2 | no | - | **rejected**: one band per chart; the comparison the title makes is on error, and the trailing mean's coverage is in the page's score table | - |
| 40 | *"There is also no explanation of the big spike in early 2022 near 2.8K"* | 3 | 1 | 1 | no | - | **rejected**: the module publishes counts and refuses to attribute them; a cause for a spike would be a claim about devices or firms | - |

### Summary

```
PANEL: 4 seats, simulated · 5 charts · findings 41 · defects 30 · novel 12
       fixed 27 · accepted 3 · rejected 11 · multi-seat defects 24
       D = 6.00 defects/chart · N = 0.40 novel share · R = 0.27 rejected share
```

**Reading these numbers honestly.** D = 6.00 is three times Matter Ledger's
2.00 and is the highest in the estate. Two things drove it: this is a first
build with no earlier round of Aaron's reading, so the panel was the first
outside read of any kind; and the page is denser than earlier modules (a
forecast band, a dotplot, a locked test, a timeline with three mark types),
with more to misread. N = 0.40 is half Matter Ledger's 0.80: the author's own
render review, run twice before the panel and recorded as F-1 to F-19, had
already caught most of what the panel found, which is what the pre-panel
notes exist to show. R = 0.27 is in the same range as before.

**The convergence is the result worth keeping.** Four of four seats fell
into the same holes on five findings: the error-average title over a
series plot (6), the unexplained model label on chart 3 (9), the rule-off
lanes drawn like live ones on chart 4 (11, the panel's sharpest finding and
one the author had not written down), the phone axis (16) and the
indistinguishable grey windows on chart 5 (20). The author's pre-panel
notes had the model label and the abbreviation but not the rule-off
reading, the axis collision or the grayscale failure.

**The visualization-seat ratio, tracked as the skill asks.** Seat 4 raised
20 of the 41 findings and 17 of the 30 defects; the three domain seats
raised 13 defects between them, several substantive (the "which other
month" ring on chart 2, the pre-registration statement on chart 3, the
no-event-date reports' whereabouts on chart 5). Seat 4 alone produced the
finding that chart 4's rule-off squares read as episodes; seat 3 reached
the same place from the paragraph's arithmetic. The domain floor of three
is earning its place; the ratio is below the Deal Desk panel's 13 of 19.

**On the sentence returns.** 15 of 15 domain-seat sentences carried the
title's claim; none was bland and several were sharper than the title
("a smoke alarm with the battery out", "a band wide enough to drive a
truck through", "the one that tells you not to panic about the recent
drop"). Seat 4's chart 2 sentence was the one honest "partly": the picture
carried the comparison and not the figures, which is the finding the
retitle answers.

**What a clean return would have meant.** Nothing: a panel that returns
nothing is recorded as "no findings", never as a pass. This one returned
41 and the clause did not arise.

**Scope.** The panel read static renders at two widths. Tooltips, the
keyboard navigator and the data-table disclosures exist only after an event
and are outside what any seat could see; this record covers the artifact's
static state only (CHART-REVIEW v2.8, 7.4 scope clause).

---

## 1 · Once per publish (K7, K8) - run 2026-10-06

**K7 - the assets the review fetched are the assets that were built: PASS.**
Every asset URL in `docs/index.html` carries `?v=<md5 of the file's bytes>`,
computed by `src/build_page.py` at build time, so a changed stylesheet or
script changes its URL. The render script opens a fresh Chromium context per
run against `http.server`, so no cache survives between runs. The hashes
recorded at this review: `felix.css` 2676472309, `page.js` 7e74d35316,
`cascadia-echarts-theme.js` fe48511d43, `echarts.min.js` 334d8b37c4 (the
`page.js` and `felix.css` tokens moved with every fix below and were
re-read from the page each time).

**K8 - social card and favicon: PASS.** `og:type`, `og:title`,
`og:description` (computed from the outlook), `og:image` (absolute, on the
canonical domain), `og:url`, `twitter:card`, `twitter:image` and a linked
favicon are all present. **Open item, not a failure:** the card image
`https://www.robbinsanalytics.com/assets/thumb-early-warning.png` is
produced by the site repository's `tools/build_thumbs.py` in Phase 6 and does
not exist until the site publishes; until then the tag points at a URL that
returns 404.

## 2 · Checklist A, per chart

| Check | C1 outlook | C2 locked test | C3 coverage | C4 review timeline | C5 lag-matched |
|---|---|---|---|---|---|
| 0.1 decision named | page, six answers | same | same | same | same |
| 0.2 quadrant | explanatory | explanatory | explanatory | explanatory | explanatory |
| 0.3 class | detailed | detailed | detailed | detailed | detailed |
| 1.1 relationship, matches title | change over time, plus a distribution for the next month | change over time (two models against actuals) | ranking, against two reference lines | timeline (events over time, one lane per code) | change over time, three windows |
| 1.2 encoding | position, common scale | position | position | position (time) and shape (mark type) | position |
| 1.3 banked to 45° | **yes**, `cascadiaBankedHeight` | **yes** | n/a (bars) | n/a (marks) | **yes** |
| 1.4 causal disclaimer | n/a | n/a | n/a | **PASS**: "Association only: the timeline is context, not validation" in the subtitle; title uses "began in the span" | n/a |
| 2.1 baseline | zero (count) | zero (count) | zero to 100 (share) | n/a (categorical lanes) | zero (count) |
| K1 extent contains series | axis max derived by `niceAxis` over actuals, upper ranges and the twenty dots | derived over actuals, both models and the upper range | 100 is the quantity's own ceiling, not a fitted bound; bars are shares of 24 months | n/a | derived over the 12-month series, the largest |
| 2.2 single value axis | yes | yes | yes | yes | yes |
| 2.3.1 fixed slots | Evergreen actual, Glacier model in use, Glacier dots | Evergreen actual, Glacier model in use, Rain other model, Madrona miss | Evergreen enabled, Madrona disabled | Madrona flags, episodes and Class I marks | Evergreen within 3, Rain within 6 and 12 |
| 2.3.2 sentiment not by colour alone | n/a | n/a | "rule off" in every disabled bar's label | mark shape plus the key text | n/a |
| 2.3.3 / 2.3.4 mark size | 2 and 2.5 px strokes, 6 px dots in Glacier (trio) | 2 to 2.5 px strokes, trio plus Rain (labelled) | 40 px bars | 9 px squares, 11 px diamonds | 2 to 2.5 px strokes, trio |
| 2.3.5 ≤4 categories | 3 | 3 | 2 | 3 mark types | 3 |
| 2.3.6 contrast | Glacier and Evergreen ≥3:1; band at 0.18 opacity is a region, not a line | Rain dotted line **PASS-BY-EXCEPTION**: directly labelled at ≥4.5:1 at every width (F-14) | ≥3:1 | ≥3:1 | Rain lines **PASS-BY-EXCEPTION**: labelled at every width (F-14) |
| 2.4 gridlines | none | none | none | none | none |
| 2.5 decoration | none | none | none | none | none |
| 2.6 part-to-whole | n/a | n/a | n/a | n/a | n/a |
| 2.7 sort | time | time | descending by coverage | lanes by flagged months, most first, stated in the subtitle (F-15) | time |
| 2.8 horizontal text | yes | yes | yes (F-9) | yes | yes |
| 2.9 rounded | "1K" ticks, whole counts | same | whole percent | dates | "1.5K" ticks |
| 3.1 finding title, top | computed | computed | computed | computed | computed |
| 3.2 title readable from the plot | point and 80% range: the dot column and its marker line; **PASS-BY-EXCEPTION** for "672", a computed aggregate carried by the table's outlook row, basis "80% range ... from 36 past errors" in the summary | **PASS-BY-EXCEPTION**: "246 against 265" are mean absolute errors over the 24 plotted months, carried per month by the table, basis "a month on average" in the title | bars 33% to 100% visible; three Madrona bars below the 70% line | one shaded episode bar visible; 24 diamonds countable; **PASS-BY-EXCEPTION** for "224 evaluated months" = 7 lanes × 32 months on the axis, and the rate, carried by the table | both months marked on the like-for-like line with their values (F-18) |
| 3.3 focus, three parts | actual saturated, annotation at the dots in Glacier ink | comparison chart (3 series, title about the comparison): fixed slots; annotation in Madrona at the Madrona leader | enabled vs disabled; reference labels in their line's ink | Madrona marks; annotation in Madrona at the episode | within 3 saturated, context lines Rain and labelled; annotation Evergreen |
| 3.4 annotation | one, 13 words, Glacier, above the top dot | one, 10 words, leader line to the miss | one note at the narrow width (13 words); at wide widths the two reference labels carry it | one, 14 words, in reserved headroom, names the lane (F-16) | one, 8 words, plus two subordinate value labels |
| K3 no annotation over a mark | above the top dot, clear of the band's upper edge at 656 and 1040 | above the band's upper edge, clear of all three lines | labels above the plot; value labels carry a paper background so the lines break behind them | reserved headroom above the first lane; the reference label sits under the axis labels | top-right corner over the shaded region, no line reaches it; value labels 16 px below their points |
| 3.5 arrangement | next month adjacent to the series end | models overlaid on actuals | ranked | one lane per code | three windows overlaid |
| 3.6 direct labels | end labels at every width (abbreviated at 320: "exp.", "rec.") | end labels at every width ("mean", "rec.", "cand." at 320) | value labels on bars | lane labels; one flat key line for the three mark types, which cannot carry a label each | end labels at every width ("12 mo", "6 mo", "3 mo" at 320) |
| 4.1 holes | points begin Jan 2024 where the evaluated months begin; nothing zero-filled | none | none | an empty lane is zero flags, which is true | incomplete months shown and shaded, not dropped; "still filling" in the subtitle |
| 4.2 provenance strip | 3 segments, `cascadiaProvenance` | 3 | 3 | 3 | 3 |
| K5 rendered segment count | 3 at every width | 3 | 3 | 3 | 3 |
| 4.3 travels alone | flags: "counts, not rates; one firm-list exclusion applied; next month is an elapsed-period estimate" | flags: "counts, not rates; locked test ..., run once" | flags: "not a safety measure; ..." | subtitle: association only; flags: "counts and dates, not rates or risk" | flags: "counts, not rates; ... diagnostic, not a nowcast" |
| 4.5 uncertainty | quantile dotplot (20 outcomes) plus the 80% band | the 80% band | n/a (coverage is exact) | n/a | n/a (counts are exact) |
| 5.1 three layers | summary, table, **L3 navigator** | summary, table, navigator | summary, table; L3 not required, shape in the summary ("sorted from highest to lowest") | summary, table, navigator | summary, table, navigator |
| 5.2 L1 to L3 | type, range, extrema, latest | type, ranges, errors, largest miss | type, ranked list | type, counts per lane, dates | type, ranges, totals |
| K2 every figure from a query | `forecast.csv` outlook row, `forecast_scored.csv` errors, `monthly_report_count.csv` | `forecast_scored.csv`, `forecast_score.csv` | `forecast_score.csv`, `review_workload.csv` | `forecast_scored.csv`, `review_queue.csv`, `review_workload.csv`, `recall_context.csv` | `monthly_lag_matched.csv`, `lag_summary.csv` |
| 5.3 WCAG 2.2 AA | reflow at 320 verified by the render script (no horizontal scroll); 12 px minimum inside the canvas; strip at the theme's 11 px; focus ring from Felix; keyboard button ≥24 px | same | same | same | same |
| 5.4 monochrome | solid vs dashed, labels | solid, dashed, dotted, labels | "rule off" in the label | three shapes | solid vs dashed, weight, labels |
| 5.5 responsive | form constant; abbreviations declared in `ABBR`; no tooltip at or below 768 px (F-19) | same | value labels shorten to the percent; reference labels become the note | lane labels shorten to the code; annotation and reference line become the note and the subtitle | same as C1 |
| K4 tick interval derived | `interval: 'auto'`, `hideOverlap`; first and last labels pulled inside the plot at 320 only (F-5) | same | 20 or 50 by width | same as C1 | same as C1 |
| 5.6 reduced motion | theme: `animation: !RM` | same | same | same | same |
| 5.7 dark mode | `color-scheme: light` declared | same | same | same | same |
| 7.1 adversarial read | panel below | | | | |
| 7.2 AI output | the charts were model-built; the full checklist was run | | | | |
| K6 widths | 320, 655, 656, 1040, recorded above | | | | |
| 7.4 panel as specified | below | | | | |

**K5 was verified from the render, not the config**: `src/render_charts.py`
counts the separator in the rendered strip at every width of the ladder and
printed `[3, 3, 3, 3, 3]` at 320, 655, 656 and 1040.

**The tooltip decision, recorded so it is not re-derived.** Tooltips exist
above a 768 px viewport and are absent at or below it, because CHART-REVIEW
5.5 fails a hover-following tooltip there and the drop order makes it the
first thing to go; the table and the keyboard navigator carry the values.
This does not move the artifact to Checklist B: every finding is fixed in a
computed title and a tooltip moves none of them. The same decision is on the
record in `cascadia-matter-ledger-analytics`.

### Per-chart verdicts

```
CASCADIA CHART REVIEW v2.8 - C1 the outlook (docs/index.html #c1) - 2026-10-06
Class: detailed        Quadrant: explanatory
Relationship: change over time, with a distribution for the next month
States reached: default only (no controls); tooltips are not a state
Widths reached (K6): 320, 655, 656, 1040 (crossing at 656, host 560)
Once per publish (K7, K8): PASS - 2026-10-06
Reading panel (7.4): section 0, 2026-10-06, simulated
INVARIANTS: all PASS; 3.2 PASS-BY-EXCEPTION (computed aggregate, table + basis)
PREFERENCES: none failed
N/A: 1.4, 2.6
INVARIANT FAILURES: 0    PREFERENCE SCORE: 0
VERDICT: SHIP (after the section 0 disposition)

CASCADIA CHART REVIEW v2.8 - C2 the locked test (#c2) - 2026-10-06
Relationship: change over time (two models against actuals)
INVARIANTS: all PASS; 2.3.6 PASS-BY-EXCEPTION (Rain labelled at every width);
            3.2 PASS-BY-EXCEPTION (mean absolute errors, table + basis)
PREFERENCES: none failed      N/A: 1.4, 2.6
INVARIANT FAILURES: 0    PREFERENCE SCORE: 0

CASCADIA CHART REVIEW v2.8 - C3 coverage by code (#c3) - 2026-10-06
Relationship: ranking against two reference lines
INVARIANTS: all PASS      PREFERENCES: none failed
N/A: 1.3, 1.4, 2.6, 4.5, 5.1 L3 (not required; shape clause in the summary)
INVARIANT FAILURES: 0    PREFERENCE SCORE: 0

CASCADIA CHART REVIEW v2.8 - C4 the review timeline (#c4) - 2026-10-06
Relationship: timeline (events over time by code)
INVARIANTS: all PASS; 3.2 PASS-BY-EXCEPTION (224 evaluated months = lanes × months)
PREFERENCES: none failed      N/A: 1.3, 2.1, 2.6, 4.5, K1
INVARIANT FAILURES: 0    PREFERENCE SCORE: 0

CASCADIA CHART REVIEW v2.8 - C5 lag-matched series (#c5) - 2026-10-06
Relationship: change over time, three windows
INVARIANTS: all PASS; 2.3.6 PASS-BY-EXCEPTION (Rain labelled at every width)
PREFERENCES: none failed      N/A: 1.4, 2.6, 4.5
INVARIANT FAILURES: 0    PREFERENCE SCORE: 0
```

**VERDICT, all five charts: SHIP**, with zero INVARIANT failures and a
preference score of zero on each, after the panel's 27 fixes were applied
and the ladder re-rendered (section 5). The three accepted findings carry
their reasons in the disposition; a preference score above zero would have
needed a written justification here, and none was incurred.

## 3 · Findings raised by the author's own review, and their disposition

Every one of these was found by **looking at a render**. None was visible in
the configuration. They were fixed before the panel was spawned and are
recorded here so that what the panel finds can be measured against what the
author had already caught.

| # | Where | Finding | Disposition |
|---|---|---|---|
| F-1 | page | At 320 px the document was 400 px wide (Rule 5.3, WCAG 1.4.10): the compact header was two pills beside a non-wrapping wordmark, which is not what Felix prescribes. | **Fixed**: the header follows Felix 6.2 at narrow widths, a hamburger button and a mobile menu panel, with inline SVG for the icon-font glyphs as the page already does for arrows. Verified by clicking it at 320 px. |
| F-2 | page | **`.container-x` was missing from the compiled stylesheet**: Felix section 3.1 (the container rule) had not been carried into `felix.src.css`, so the page had no side gutters and no maximum width at any viewport. | **Fixed**: section 3.1 added verbatim. The K6 crossing moved from viewport 600 to 656 as a result, and the earlier 599/600 renders were discarded. |
| F-3 | C1, C2 | "with the the ETS candidate's" in subtitles and summaries: the model label carried its own article. | **Fixed** in the builder; zero doubled articles in the page. |
| F-4 | C1, C2, C5 | End-of-line labels overprinted one another where the series converge at the right edge ("expected" over "received"; three labels in one spot on C2 and C5). | **Fixed**: after the first draw the labels' anchors are measured and pushed apart to a 15 px gap, the group kept centred; the lines do not move. |
| F-5 | all time charts | At 320 px the last tick label was clipped ("Sep '2"); at 656 C4's last label clipped at the right edge. | **Fixed**: first and last labels pulled inside the plot at the narrow width only (applying it at wide widths made neighbouring ticks crowd, so it is scoped); C4 reserves a wider right margin at wide widths. |
| F-6 | C1 | **K3**: the annotation was anchored at the 80% upper bound, under the top dots, and printed over the band and the dashed line. | **Fixed**: anchored above the highest dot, narrowed to 170 px so it clears the band's upper edge. |
| F-7 | C1 | The "expected" end label printed across the dotplot column. | **Fixed**: the label distance is one axis category plus 10 px, measured from the chart. |
| F-8 | C2 | "candidate (in use)" was clipped by a guessed 90 px gutter. | **Fixed**: the gutter is measured from the longest label. |
| F-9 | C3 | The two vertical reference labels crossed the value labels of the disabled codes; the dashed lines ran through the text. | **Fixed**: reference labels sit above the plot, one reading leftward from the 70% line and one rightward from the 80% line; value labels carry a paper background so the lines break behind them. |
| F-10 | C3 | At 320 px "58% off" read as a discount. | **Fixed**: "58% rule off"; the narrow note now names both dashed lines. |
| F-11 | C4 | The annotation printed over the x-axis labels. | **Fixed**, first by moving it into the emptiest lane and then by F-16. |
| F-12 | C1 | "672 dots: the 20-quantile spread ..." read as a count of dots; the band was named nowhere. | **Fixed**: "point 672; 20 dots show the quantile spread of 36 past one-month errors"; the subtitle and summary name the band. |
| F-13 | page | The Rule 0.1 paragraph gave five of the six answers; literacy was missing. | **Fixed**: "a reader who works in spreadsheets and reads a trend line, not a statistician". |
| F-14 | C1, C2, C5 | At 320 px every end label was dropped, which left the Rain series unlabelled (3.3, 3.6, 5.5; the 2.3.6 exception is legal only while the label is present). | **Fixed**: a declared abbreviation map (`ABBR` in `page.js`) and a gutter measured from the abbreviated text; no label is dropped at any width. |
| F-15 | C4 | Lane order was undeclared (2.7). | **Fixed**: lanes ordered by flagged months, most first, and the subtitle says so. |
| F-16 | C4 | The annotation explained the 2024-08-29 reference line, which is a disclosure's job (3.4), and nothing annotated the episode the title counts. | **Fixed**: the annotation names the one episode (lane, months, arrived against expected) in headroom reserved above the first lane (K3's remedy), aligned to the episode's last month; the reference line keeps a subordinate label under the axis and the subtitle says what it is. |
| F-17 | all | No canvas said that counts are not rates (4.3): lifted into a slide, a chart lost the page's central caveat. | **Fixed**: every strip's flags segment opens with "counts, not rates" or its equivalent. |
| F-18 | C5 | The two months the title compares were not marked on the plot (3.2 rested wholly on the table). | **Fixed**: both months are marked on the like-for-like line with their values; at 320 px the month is dropped from the label (declared). The labels sit 16 px below their points so no line crosses them. |
| F-19 | all | Tooltips followed the pointer at any width (5.5 fails that at or below 768 px). | **Fixed**: no tooltip at or below 768 px. |

## 4 · Renders handed to the panel

**Ten files: five charts at two widths.** Full-page renders and the K6
crossing renders exist beside them and were used by the author, not by the
panel.

| Viewport | Chart element | Why | Files |
|---|---|---|---|
| **1040 px** | **1000 CSS px** | design width | `docs/renders/c{1..5}-1040.png` |
| **320 px** | **280 CSS px** | Rule 5.3 / WCAG 1.4.10 reflow floor | `docs/renders/c{1..5}-320.png` |
| 655 and 656 px | 559 and 560 CSS px | K6, either side of the host crossing; author only | `docs/renders/c{1..5}-655.png`, `-656.png` |

The filename is the viewport width, not the chart's width, and the seats were
told the second set was "as it appears on a phone". Rendered at
`deviceScaleFactor: 2`, so image pixels are twice the CSS values above.

**The un-panelled specimen is frozen** at
`governance/panel-specimen/2026-10-06-v1/` (the twenty chart renders and the
ladder record), with `docs/index.html` at SHA-256 `4a6be0d7f4963856...` at
the moment the seats were spawned, so the charts as the panel saw them still
exist for comparison with what shipped.

## 5 · After the panel: the fixes, re-rendered and re-gated

The 27 fixes in section 0 were applied in one round (text in
`src/build_page.py`, geometry in `docs/assets/page.js`, one sentence in
`docs/template.html`), the page rebuilt, and `src/render_charts.py` re-run
at the full ladder: **320, 655, 656 and 1040 px, exit 0, no horizontal
overflow, every chart drawn, strip segments `[3, 3, 3, 3, 3]` at every
width.** The author then read every render again and found three residual
defects of the fixes themselves, each fixed and re-rendered before this
record was closed: chart 1's new band label crossed the May 2024 spike
(K3; it now reads leftward over the empty months before the band), chart
3's reference labels vanished when their lines were made transparent by
opacity (a markLine's label shares its line's opacity; the stroke is now
transparent instead) and its longest value label clipped (the right margin
is measured from the longest label), and chart 5's relocated annotation
collided with the compared-month labels (K3; it returned to the top of the
zone it names, finding 21 accepted).

`src/validate.py` was re-run over the rebuilt page: 14 of 14 checks PASS,
names gate and em-dash gate zero. The panel specimen at
`governance/panel-specimen/2026-10-06-v1/` is the state the seats read;
`docs/renders/` is the state that ships.

**Open items carried out of this review.** The card image URL (K8) exists
only once the site repository builds it. Chart 4 at 280 CSS px cannot show
32 months by 7 lanes with every mark apart (finding 18, accepted). The
abbreviations at the narrow width (finding 41, accepted) are declared and
not loved; a future revision could trade the dot column's width for full
words.
