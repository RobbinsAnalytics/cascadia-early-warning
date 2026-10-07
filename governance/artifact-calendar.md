# Artifact calendar - events that changed reporting behavior, not device performance

*Phase 1 artifact (S-07). Owner: Aaron Robbins. Established 2026-10-06. Every
row is a change in how reports reach the source, so that a step or a spike in
a count series can be read against it before it is read as anything else. The
page annotates the series with these dates. No row concerns any firm or
device; the series this module forecasts are counts of reports by product
code, and this calendar is about the reporting system.*

| Date | Event | How it shows in the receipt-date series | Status | Source |
|---|---|---|---|---|
| 2006 | `date_of_event` added to the MDR record | Records received before 2006 carry no event date; the lag diagnostic (M-02) starts at 2006 or later | Verified in the field reference | https://open.fda.gov/fields/deviceevent.yaml |
| 2011 to 2018 | Litigation-driven reporting wave: reports whose reporter occupation is coded ATTORNEY run from under 1,000 a year in 2010 to 27,514 (2012), 35,182 (2013), 31,135 (2014), then fall to 3,564 (2018) and single digits after | Receipt-date spikes concentrated in a few product codes outside this cohort; the collapse after 2018 is a coding change, not a change in behaviour | Counts verified by API query 2026-10-06; cause of the coding collapse not established | api.fda.gov `count=reporter_occupation_code.exact` |
| 2014-02-14 rule; 2015-08-14 effective | Electronic MDR (eMDR) final rule: manufacturers and importers must submit electronically | No visible step in annual totals (2014: 862,116; 2015: 861,801; 2016: 867,447). Listed because it is often cited as one | Verified | https://www.fda.gov/medical-devices/postmarket-requirements-devices/mandatory-reporting-requirements-manufacturers-importers-and-device-user-facilities |
| 1997 to 2019-06 | Alternative Summary Reporting (ASR): 108 exemptions let some manufacturers file summary spreadsheets outside MAUDE. The ASR data were never loaded into MAUDE and are published as separate files | Product codes under an exemption are structurally undercounted in MAUDE while the exemption ran | Verified | https://www.fda.gov/medical-devices/medical-device-reporting-mdr-how-report-medical-device-problems/mdr-data-files |
| mid-2017 | FDA begins revoking ASR exemptions; from 2017 companion reports for the remaining exemptions do enter MAUDE | A step up in individual reports for formerly exempt codes from mid-2017 | Verified (revocations); the per-code timing is not published | Same page; https://kffhealthnews.org/news/fda-to-end-program-that-hid-millions-of-reports-on-faulty-medical-devices/ |
| 2018-08-17 | Voluntary Malfunction Summary Reporting (VMSR) begins for malfunctions manufacturers become aware of on or after this date; eligible codes are Class I and Class II devices that are not permanently implantable, life-supporting or life-sustaining, and at least two years old | For eligible codes one record can stand for many malfunctions from 2018 Q4. **Every code in this cohort is ineligible**, so one record stays one report; the eligibility field is in the classification extract | Verified | https://www.govinfo.gov/content/pkg/FR-2018-08-17/html/2018-17770.htm |
| 2019-05 to 2019-06 | ASR program ends; the last 13 exemptions (dental implants, implantable defibrillators and pacemaker electrodes among them) are revoked | A step up in individual reports for those codes from mid-2019; no all-device "dump" is visible in June 2019 (2019-06 is below 2019-05) | Verified | Same FDA page; https://www.medtechdive.com/news/fda-ends-alternative-reporting-program-pledges-to-make-maude-user-friendly/557465/ |
| 2019-09 | All-device receipt spike: 185,025 reports in the month against 85,000 to 105,000 in the months before; 2019-10 to 2019-12 run 127,000 to 144,000 | A one-month pile-up across many codes. Cause not established (candidates: quarterly summary batches, backfill after the ASR end) | Counts verified; cause not | api.fda.gov `count=date_received` |
| 2020-03 onward | Pandemic reporting guidance (May 2020) | Of 816,470 reports received January to July 2020, 3,500 mention the pandemic; no step in the cohort's codes is attributed to it here | Verified | https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11618056/ |
| 2022 | eMDR system rejects submissions with a blank product code or missing adverse-event problem codes | Field completeness changes, not counts; the share of records without a product code should fall after 2022 | Verified | https://www.fda.gov/medical-devices/emdr-electronic-medical-device-reporting/emdr-system-enhancements |
| 2024-08-29 | VMSR format change: the summary count moves from narrative text to structured fields (`summary_report_flag`, `noe_summarized`, `exemption_number`) for events manufacturers become aware of on or after this date; additional eligible codes | Summary records become identifiable in the structured record from this date only; before it the count lived in narrative text. Does not touch this cohort's ineligible codes | Verified | https://www.govinfo.gov/content/pkg/FR-2024-08-29/pdf/2024-19414.pdf |
| Any month | Manufacturer batch cadence: some reporters file in alternating months or in quarterly batches | A sawtooth in some codes' receipt-date series that is a filing rhythm, not an event rhythm; the lag-matched diagnostic (M-02) is the like-for-like view | Verified in series outside this cohort | api.fda.gov |
| 2026-03 to 2026-07 | FDA announces the replacement of MAUDE by the Adverse Event Monitoring System, with historical device data migrated | Effect on the openFDA endpoint not established; it still reported `last_updated` 2026-09-29 on 2026-10-06 with receipts through 2026-08-31 | Announcements verified; effect not | https://www.emergobyul.com/news/medical-device-manufacturers-first-introduction-fda-adverse-event-monitoring-system |

## What the calendar means for the forecast

- **History starts 2016-01** (D5), after the 2011 to 2015 litigation wave and
  the eMDR cut-over, and the development period starts 2022-01, after the ASR
  end and the 2019-09 pile-up have left the 36-month calibration window of the
  earliest development origin.
- **The cohort is VMSR-ineligible by construction** (D2), so the 2018-08-17
  and 2024-08-29 changes do not alter what one record means for these codes.
  The classification extract's `summary_malfunction_reporting` field is the
  committed evidence, per code.
- **Receipt pile-ups are expected**, which is why the review rule (D9)
  requires two consecutive months above the 80% range rather than one.
- **The series are counts of reports received**, labelled as such; the
  calendar is the first thing a reader is shown before a step is read as a
  change in anything other than reporting.
