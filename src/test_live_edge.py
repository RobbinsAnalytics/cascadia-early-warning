"""Drive pull_live_edge.run() offline, in a throwaway directory.

No network: the client is a fake that serves the frozen count files with a
chosen meta.last_updated and, where the test says so, extra buckets for a
month beyond the freeze. No repo file is touched: LIVE and GOV are pointed at
a temp dir and the budget check is bypassed. Exit non-zero on any failure.

    .venv/Scripts/python.exe src/test_live_edge.py
"""
from __future__ import annotations

import copy
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pull_live_edge as ple  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent
FROZEN = {c: json.loads((REPO / "data" / "raw" / "counts" / ("%s_date_received.json" % c)).read_text(encoding="utf-8"))
          for c in ple.COHORT}
FROZEN_LU = FROZEN[ple.COHORT[0]]["meta"]["last_updated"]


class FakeClient:
    def __init__(self, last_updated, extra=None, mutate=None, status=200):
        self.lu, self.extra, self.mutate, self.status = last_updated, extra or {}, mutate, status
        self.requests_made = 0
        self.datum = {}

    def get_json(self, url, label=None):
        code = url.split("product_code:")[1].split("&")[0]
        parsed = copy.deepcopy(FROZEN[code])
        parsed["meta"]["last_updated"] = self.lu
        for bucket in self.extra.get(code, []):
            parsed["results"].append(bucket)
        if self.mutate:
            self.mutate(code, parsed)
        self.requests_made += 1
        self.datum["event"] = self.lu
        body = json.dumps(parsed).encode("utf-8")
        return body, parsed, {"status": self.status}


EMPTY_DISPOSITIONS = "# nothing dispositioned\n"
PYX_2026_01 = ('[[revision]]\ncode = "PYX"\nmonth = "2026-01"\nfrozen = 99\nlive_at_disposition = 96\n'
               'dispositioned = "2026-10-13"\nclassification = "source revision"\ndecision = "D24"\n')


def fresh(tmp, dispositions: str | None = EMPTY_DISPOSITIONS):
    """Point the pull at a throwaway tree. The disposition record (D25) is written there too: empty by
    default, the given text otherwise, and absent when None."""
    ple.LIVE = tmp / "live"
    ple.GOV = tmp / "gov"
    ple.budget_ok = lambda n: None
    ple.GOV.mkdir(parents=True, exist_ok=True)
    p = ple.GOV / "source-revisions.toml"
    if dispositions is None:
        if p.exists():
            p.unlink()
    else:
        p.write_text(dispositions, encoding="utf-8")


def pyx_lower(by: int):
    """A fake-source mutation: PYX 2026-01 reads `by` reports lower than frozen (99), taken off 2026-01-27."""
    def mutate(code, parsed):
        if code == "PYX":
            for b in parsed["results"]:
                if b["time"] == "20260127":
                    b["count"] -= by
    return mutate


def run_with(tmp, client, dispositions: str | None = EMPTY_DISPOSITIONS):
    fresh(tmp, dispositions)
    return ple.run(client_factory=lambda: client)


def failed(r):
    return [c["check"] for c in r["checks"] if not c["passed"]]


def main() -> int:
    problems = []

    def expect(cond, msg):
        print(("  ok   " if cond else "  FAIL ") + msg)
        if not cond:
            problems.append(msg)

    # 1. the source unchanged since the freeze: the first run sees it (ok, nothing appended), the second skips
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        r1 = run_with(tmp, FakeClient(FROZEN_LU))
        expect(r1["status"] == "ok" and r1["passed"], "first run at the frozen datum: ok, passed (%s, %s)" % (r1["status"], failed(r1)))
        expect(r1["months_appended"] == {} and r1["forecasts_issued"] == 0, "nothing appended or issued when nothing is loaded past the freeze")
        expect(r1["frozen_variance"]["months_reading_higher"] == 0 and r1["frozen_variance"]["months_reading_lower"] == 0,
               "frozen months re-read from identical bodies show zero variance")
        r2 = run_with(tmp, FakeClient(FROZEN_LU))
        expect(r2["status"].startswith("skipped: source unchanged"), "second run at the same datum skips (%s)" % r2["status"])
        hist = (tmp / "gov" / "run_history.jsonl").read_text(encoding="utf-8").splitlines()
        expect(len(hist) == 2, "two history lines appended")

    # 2. last_updated earlier than the frozen datum: a failed check, status failed
    with tempfile.TemporaryDirectory() as d:
        r = run_with(pathlib.Path(d), FakeClient("2026-09-01"))
        expect(r["status"] == "failed" and any("not before the frozen datum" in c for c in failed(r)),
               "a backwards last_updated fails (%s)" % failed(r))

    # 3. a malformed bucket: a failed check
    with tempfile.TemporaryDirectory() as d:
        def mutate(code, parsed):
            if code == "DSQ":
                parsed["results"].append({"time": "2026-9-1", "count": "x"})
        r = run_with(pathlib.Path(d), FakeClient(FROZEN_LU, mutate=mutate))
        expect(r["status"] == "failed" and any(c.startswith("response schema, DSQ") for c in failed(r)),
               "a malformed bucket fails the schema check (%s)" % failed(r))

    # 4. a frozen month rewritten downward by more than 1%: a failed check
    with tempfile.TemporaryDirectory() as d:
        def mutate(code, parsed):
            if code == "LWS":
                parsed["results"] = [b for b in parsed["results"] if not b["time"].startswith("202403")]
        r = run_with(pathlib.Path(d), FakeClient("2026-10-03", mutate=mutate))
        expect(r["status"] == "failed" and any("rewritten downward" in c for c in failed(r)),
               "a frozen month emptied in a later vintage fails (%s)" % failed(r))
        expect(r["frozen_variance"]["material_downward"][0]["code"] == "LWS", "and the record names the code")

    # 5. September 2026 loaded: appended for every code, the frozen outlook scored, forecasts re-issued
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        extra = {c: [{"time": "20260901", "count": 300}, {"time": "20260915", "count": 350}] for c in ple.COHORT}
        extra["PYX"] = [{"time": "20260910", "count": 4}]
        r = run_with(tmp, FakeClient("2026-10-15", extra=extra))
        expect(r["status"] == "ok" and r["passed"], "September loaded: ok (%s %s)" % (r["status"], failed(r) or r["error"]))
        expect(all(r["months_appended"].get(c) == ["2026-09"] for c in ple.COHORT), "2026-09 appended for all seven codes")
        series = ple.read_csv(tmp / "live" / "live_series.csv")
        dsq = [x for x in series if x["product_code"] == "DSQ" and x["month"] == "2026-09"]
        expect(dsq and int(dsq[0]["reports_as_seen"]) == 650, "DSQ 2026-09 reads 650 as seen (%s)" % (dsq[0]["reports_as_seen"] if dsq else None))
        scores = ple.read_csv(tmp / "live" / "live_scores.csv")
        h1 = [x for x in scores if x["target"] == "2026-09" and x["horizon"] == "1"]
        expect(len(h1) == 21, "the frozen outlook's 21 horizon-one rows (7 codes x 3 models) scored (%d)" % len(h1))
        fc = ple.read_csv(tmp / "live" / "live_forecast.csv")
        expect(len(fc) == 42 and all(x["origin"] == "2026-09" for x in fc), "42 forecasts re-issued from origin 2026-09 (%d)" % len(fc))
        cand = [x for x in fc if x["model"] == "candidate" and x["horizon"] == "1"]
        expect(all(x["point"] != "" for x in cand), "every candidate fit succeeded")
        expect(all(x["calibration_n"] == "36" for x in fc if x["model"] in ("baseline_a", "candidate") and x["horizon"] == "1"),
               "horizon-one ranges rest on 36 errors")
        vint = list((tmp / "live" / "counts").iterdir())
        expect(len(vint) == 1 and len(list(vint[0].glob("*_date_received.json"))) == 7, "one vintage with seven bodies saved")
        # a second run at a later datum with the same month: no re-score, no re-issue at the same origin
        r3 = run_with(tmp, FakeClient("2026-10-22", extra=extra))
        expect(r3["status"] == "ok" and r3["forecasts_scored"] == 0 and r3["forecasts_issued"] == 0,
               "a later vintage of the same month scores and issues nothing new (%s, %d, %d)" % (r3["status"], r3["forecasts_scored"], r3["forecasts_issued"]))
        series = ple.read_csv(tmp / "live" / "live_series.csv")
        expect(len([x for x in series if x["month"] == "2026-09"]) == 14, "both vintages' readings of 2026-09 are kept")

    # 7. the disposition record (D25): a dispositioned source revision is known and passes; anything else fails
    frozen_pyx_jan = sum(int(b["count"]) for b in FROZEN["PYX"]["results"] if b["time"].startswith("202601"))
    expect(frozen_pyx_jan == 99, "the fixture's PYX 2026-01 is the frozen 99 the entry names (%d)" % frozen_pyx_jan)
    with tempfile.TemporaryDirectory() as d:  # known: listed at 96, reads 96
        r = run_with(pathlib.Path(d), FakeClient("2026-10-07", mutate=pyx_lower(3)), PYX_2026_01)
        fv = r["frozen_variance"]
        expect(r["status"] == "ok" and r["passed"] and not failed(r), "a listed revision at its dispositioned count passes (%s, %s)" % (r["status"], failed(r)))
        expect(len(fv["known_revisions"]) == 1 and fv["known_revisions"][0]["month"] == "2026-01" and fv["known_revisions"][0]["live"] == 96
               and fv["known_revisions"][0]["decision"] == "D24", "and the record carries it as known, with its decision")
        expect(fv["material_downward"] == [] and fv["months_reading_lower"] == 1, "nothing material; the month still counts as reading lower")
        expect(any(c["check"].startswith("source revisions dispositioned") and c["value"] == 1 for c in r["checks"]), "the record's entry count is a check value")
    with tempfile.TemporaryDirectory() as d:  # known, shallower: listed at 96, reads 97 (still over 1%)
        r = run_with(pathlib.Path(d), FakeClient("2026-10-07", mutate=pyx_lower(2)), PYX_2026_01)
        expect(r["passed"] and len(r["frozen_variance"]["known_revisions"]) == 1, "a listed revision reading shallower than its entry is still known (%s)" % failed(r))
    with tempfile.TemporaryDirectory() as d:  # unlisted: empty record, reads 96
        r = run_with(pathlib.Path(d), FakeClient("2026-10-07", mutate=pyx_lower(3)))
        expect(r["status"] == "failed" and any("rewritten downward" in c for c in failed(r)), "the same decrease with an empty record fails (%s)" % failed(r))
        expect(r["frozen_variance"]["known_revisions"] == [] and r["frozen_variance"]["material_downward"][0]["month"] == "2026-01",
               "and is material, not known")
    with tempfile.TemporaryDirectory() as d:  # deepened: listed at 96, reads 95
        r = run_with(pathlib.Path(d), FakeClient("2026-10-07", mutate=pyx_lower(4)), PYX_2026_01)
        m = r["frozen_variance"]["material_downward"]
        expect(r["status"] == "failed" and any("rewritten downward" in c for c in failed(r)), "a listed revision that has deepened fails (%s)" % failed(r))
        expect(len(m) == 1 and m[0]["live"] == 95 and "deeper than its entry" in m[0].get("note", ""), "and the record says it is deeper than its entry")
    with tempfile.TemporaryDirectory() as d:  # frozen mismatch: the entry's frozen count is not the table's
        r = run_with(pathlib.Path(d), FakeClient("2026-10-07", mutate=pyx_lower(3)), PYX_2026_01.replace("frozen = 99", "frozen = 98"))
        expect(r["status"] == "failed" and "the table says 99" in r["frozen_variance"]["material_downward"][0].get("note", ""),
               "an entry whose frozen count is not the table's does not match, and fails (%s)" % failed(r))
    with tempfile.TemporaryDirectory() as d:  # empty record, no decrease: not an error
        r = run_with(pathlib.Path(d), FakeClient("2026-10-07"))
        expect(r["status"] == "ok" and r["passed"] and r["error"] is None, "an empty disposition record is not an error (%s, %s)" % (r["status"], r["error"]))
    with tempfile.TemporaryDirectory() as d:  # malformed: missing keys
        r = run_with(pathlib.Path(d), FakeClient("2026-10-07"), '[[revision]]\ncode = "PYX"\nmonth = "2026-01"\n')
        expect(r["status"] == "failed" and r["error"] and "source-revisions.toml entry 1" in r["error"] and r["requests_made"] == 0,
               "a malformed entry fails as an error before any request (%s)" % r["error"])
    with tempfile.TemporaryDirectory() as d:  # malformed: live not below frozen
        r = run_with(pathlib.Path(d), FakeClient("2026-10-07"), PYX_2026_01.replace("live_at_disposition = 96", "live_at_disposition = 99"))
        expect(r["status"] == "failed" and r["error"] and "0 <= live < frozen" in r["error"], "a live count not below frozen is malformed (%s)" % r["error"])
    with tempfile.TemporaryDirectory() as d:  # malformed: a month twice
        r = run_with(pathlib.Path(d), FakeClient("2026-10-07"), PYX_2026_01 + "\n" + PYX_2026_01)
        expect(r["status"] == "failed" and r["error"] and "listed twice" in r["error"], "a duplicate entry is malformed (%s)" % r["error"])
    with tempfile.TemporaryDirectory() as d:  # missing file
        r = run_with(pathlib.Path(d), FakeClient("2026-10-07"), None)
        expect(r["status"] == "failed" and r["error"] and "missing" in r["error"] and r["requests_made"] == 0,
               "a missing disposition record fails as an error before any request (%s)" % r["error"])
    real = ple.load_dispositions(REPO / "governance" / "source-revisions.toml")
    expect(set(real) >= {("PYX", "2026-01"), ("PYX", "2026-05")}, "the committed record loads and carries the two D24 months")

    # 6. the pure pieces
    expect(ple.seen_months("2026-09-29") == [], "last_updated 2026-09-29 sees no month past the freeze")
    expect(ple.seen_months("2026-10-01") == ["2026-09"], "last_updated 2026-10-01 sees September")
    expect(ple.seen_months("2026-12-01") == ["2026-09", "2026-10", "2026-11"], "last_updated 2026-12-01 sees three months")
    expect(ple.month_end("2026-02") == "2026-02-28", "month_end handles February")

    print("\nLIVE EDGE TESTS: %s" % ("PASSED" if not problems else "FAILED (%d)" % len(problems)))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
