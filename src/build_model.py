"""build_model.py -- PATH 1: the governed model, from the frozen staging to DuckDB
and the committed conformed tables. Offline; never touches the network.

Reads
    data/raw/extraction_log.json      every window must be complete
    data/raw/manifest.json            every staged page must hash as recorded
    data/raw/staging/event/<CODE>/    the S-01 pages (gitignored, hashed)
    data/raw/counts/<CODE>_*.json     the S-02 series, the independent path
    data/raw/bulk/device-classification-*.zip
    governance/exclusion-list.local.txt   PRIVATE; required; never copied

Writes
    data/conformed/early_warning.duckdb        record grain, gitignored
    data/conformed/monthly_report_count.csv    M-01
    data/conformed/monthly_lag_matched.csv     M-02
    data/conformed/lag_summary.csv             M-02 companion
    data/conformed/quarantine.csv              reports not countable, by reason
    data/conformed/exclusion_receipt.csv       D3 receipt, counts only
    data/conformed/monthly_event_type.csv      report mix, eligible reports
    data/conformed/product_code.csv            the cohort, from classification
    data/conformed/cohort_gate.csv             stage B columns filled
    data/reference/product_code_classification.csv   every code, selected columns
    governance/exclusion_audit.csv             PRIVATE, gitignored
    governance/exclusion-receipt-records.md    public receipt, no names

A report is one mdr_report_key. A page may carry a key twice only if the API
returned it twice, which the extraction log would have flagged as a key
mismatch; here a key seen twice within one code is counted once and the
duplication is recorded in quarantine.csv as a fact about the source.

A FAILED PARTITION IS MISSING DATA, NEVER ZERO: this script refuses to run on
an extraction log with any window not complete.

    python src/build_model.py
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import pathlib
import re
import sys
import zipfile
from collections import Counter, defaultdict

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from acquire import COHORT, COUNTS, EXTRACTION_LOG, MANIFEST, REFERENCE, REPO, STAGING, WINDOW_END, WINDOW_START  # noqa: E402
from cohort_gate import MIN_ELIGIBLE_TRAINING, TRAIN_END, TRAIN_START  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CONF = REPO / "data" / "conformed"
REF = REPO / "data" / "reference"
GOV = REPO / "governance"
DB = CONF / "early_warning.duckdb"
LOCAL = GOV / "exclusion-list.local.txt"
AS_OF = WINDOW_END  # 20260831

FIRM_FIELDS = ("manufacturer_name", "manufacturer_g1_name", "distributor_name",
               "device.manufacturer_d_name")
BRAND_FIELDS = ("device.brand_name",)


# ---------------------------------------------------------------------------
# the private list
# ---------------------------------------------------------------------------

def read_private() -> dict[str, list[str]]:
    if not LOCAL.exists():
        sys.exit("the private exclusion list is absent; the model cannot be built without it "
                 "(the committed conformed tables are the published artifact)")
    sections: dict[str, list[str]] = {}
    cur = None
    for line in LOCAL.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = re.fullmatch(r"\[(\w+)\]", s)
        if m:
            cur = m.group(1)
            sections[cur] = []
        elif cur:
            sections[cur].append(s)
    return sections


class Matcher:
    def __init__(self, sections: dict[str, list[str]]):
        self.firm = re.compile(r"\b(?:%s)" % "|".join(sections["firm_tokens"]), re.I)
        self.not_firm = re.compile(r"\b(?:%s)" % "|".join(sections["not_firm_tokens"]), re.I)
        self.brand = re.compile(r"\b(?:%s)" % "|".join(sections["brand_tokens"]), re.I)

    @staticmethod
    def norm(text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    def firm_hit(self, text: str):
        t = self.norm(text)
        if not t or self.not_firm.search(t):
            return None
        m = self.firm.search(t)
        return m.group(0).lower() if m else None

    def brand_hit(self, text: str):
        t = self.norm(text)
        m = self.brand.search(t) if t else None
        return m.group(0).lower() if m else None


# ---------------------------------------------------------------------------
# staging
# ---------------------------------------------------------------------------

def check_extraction() -> dict:
    log = json.loads(EXTRACTION_LOG.read_text(encoding="utf-8"))
    bad = {k: v for k, v in log["windows"].items()
           if v["status"] != "complete" or v["api_total"] != v["expected"]}
    if bad:
        for k, v in bad.items():
            print("  NOT COMPLETE  %s  %s  expected %s api %s" % (k, v["status"], v["expected"], v["api_total"]))
        sys.exit("%d extraction window(s) are not complete; a failed partition is missing data, never zero" % len(bad))
    return log


def check_hashes(manifest: dict) -> int:
    # A page on disk that the manifest does not know is data with no receipt;
    # it would flow into the counts through iter_pages' glob and be checked by
    # nothing. Refuse it.
    on_disk = {p.relative_to(REPO).as_posix() for p in (STAGING / "event").glob("*/*.json.gz")}
    stray = sorted(on_disk - set(manifest["files"]))
    if stray:
        sys.exit("%d staged page(s) on disk are not in the manifest: %s" % (len(stray), stray[:5]))
    n = 0
    for rel, e in manifest["files"].items():
        if not rel.startswith("data/raw/staging/event/"):
            continue
        p = REPO / rel
        if not p.exists():
            sys.exit("staged page missing: %s" % rel)
        with gzip.open(p, "rb") as gz:
            h = hashlib.sha256(gz.read()).hexdigest()
        if h != e["sha256"]:
            sys.exit("staged page moved since the freeze: %s" % rel)
        n += 1
    return n


def iter_pages(code: str):
    d = STAGING / "event" / code
    for p in sorted(d.glob("*.json.gz")):
        with gzip.open(p, "rb") as gz:
            yield p.name, json.loads(gz.read().decode("utf-8"))


def month_of(yyyymmdd: str | None) -> str | None:
    if yyyymmdd and re.fullmatch(r"\d{8}", yyyymmdd):
        return yyyymmdd[:6]
    return None


def lag_months(event: str, received: str) -> int:
    return (int(received[:4]) * 12 + int(received[4:6])) - (int(event[:4]) * 12 + int(event[4:6]))


# ---------------------------------------------------------------------------
# golden API (Path 1): the lag-matched count on a list of report rows
# ---------------------------------------------------------------------------

def golden_lag_matched(reports: list[dict]) -> dict:
    """reports: dicts with mdr_report_key, date_of_event, date_received (YYYYMMDD
    or blank). Returns event_month -> counts, plus '_missing_event_date'."""
    out: dict = {}
    missing = 0
    for r in reports:
        ev, rc = (r.get("date_of_event") or "").strip(), (r.get("date_received") or "").strip()
        if not re.fullmatch(r"\d{8}", ev):
            missing += 1
            continue
        if not re.fullmatch(r"\d{8}", rc):
            continue
        m = ev[:6]
        row = out.setdefault(m, {"reports_with_event_month": 0, "within_3": 0, "within_6": 0,
                                 "within_12": 0, "negative_lag": 0})
        row["reports_with_event_month"] += 1
        lag = lag_months(ev, rc)
        if lag < 0:
            row["negative_lag"] += 1
            continue
        for k in (3, 6, 12):
            if lag <= k:
                row["within_%d" % k] += 1
    out["_missing_event_date"] = missing
    return {("%s-%s" % (k[:4], k[4:6]) if k[0] != "_" else k): v for k, v in out.items()}


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------

CLASS_COLS = ["product_code", "device_name", "device_class", "medical_specialty",
              "medical_specialty_description", "review_panel", "regulation_number",
              "implant_flag", "life_sustain_support_flag", "summary_malfunction_reporting",
              "submission_type_id"]


def load_classification() -> dict[str, dict]:
    zips = sorted((REPO / "data" / "raw" / "bulk").glob("device-classification-*.zip"))
    if not zips:
        sys.exit("classification bulk missing under data/raw/bulk/")
    with zipfile.ZipFile(zips[0]) as z:
        name = [n for n in z.namelist() if n.endswith(".json")][0]
        data = json.loads(z.read(name).decode("utf-8"))
    out = {}
    for r in data["results"]:
        code = (r.get("product_code") or "").strip().upper()
        if code:
            out[code] = {c: (r.get(c) if r.get(c) is not None else "") for c in CLASS_COLS}
            out[code]["product_code"] = code
    return out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    CONF.mkdir(parents=True, exist_ok=True)
    REF.mkdir(parents=True, exist_ok=True)
    sections = read_private()
    matcher = Matcher(sections)
    log = check_extraction()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    n_pages = check_hashes(manifest)
    print("extraction complete: %d windows, %d staged pages hash as recorded" % (len(log["windows"]), n_pages))

    reports: dict[str, dict] = {}          # key -> attributes (public grain)
    bridge: set[tuple[str, str]] = set()   # (key, code)
    audit: list[tuple[str, str, str, str]] = []   # key, code, field, token (PRIVATE)
    excluded_keys: set[str] = set()
    dup_within_code: Counter = Counter()
    per_code_keys: dict[str, set[str]] = {c: set() for c in COHORT}

    for code in COHORT:
        for name, page in iter_pages(code):
            for r in page.get("results", []):
                key = r.get("mdr_report_key")
                if not key:
                    continue
                if key in per_code_keys[code]:
                    dup_within_code[code] += 1
                per_code_keys[code].add(key)
                devices = r.get("device") or []
                codes_in_report = sorted({(d.get("device_report_product_code") or "").strip().upper()
                                          for d in devices} - {""})
                if code not in codes_in_report:
                    # the query matched on an analysed field; record it rather than trust it
                    codes_in_report.append(code + "?")
                bridge.add((key, code))
                if key not in reports:
                    tor = sorted({t for t in (r.get("type_of_report") or []) if t})
                    reports[key] = {
                        "mdr_report_key": key,
                        "report_number": r.get("report_number") or "",
                        "date_received": r.get("date_received") or "",
                        "date_of_event": r.get("date_of_event") or "",
                        "date_report": r.get("date_report") or "",
                        "event_type": r.get("event_type") or "",
                        "report_source_code": r.get("report_source_code") or "",
                        "type_of_report": "|".join(tor),
                        "summary_report_flag": r.get("summary_report_flag") or "",
                        "noe_summarized": r.get("noe_summarized") or "",
                        "number_devices_in_event": r.get("number_devices_in_event") or "",
                        "n_devices": len(devices),
                        "device_codes": "|".join(codes_in_report),
                        "remedial_action": "|".join(sorted({a for a in (r.get("remedial_action") or []) if a})),
                    }
                    # exclusion, once per report
                    hits = []
                    for f in ("manufacturer_name", "manufacturer_g1_name", "distributor_name"):
                        tok = matcher.firm_hit(r.get(f) or "")
                        if tok:
                            hits.append((f, tok))
                    for d in devices:
                        tok = matcher.firm_hit(d.get("manufacturer_d_name") or "")
                        if tok:
                            hits.append(("device.manufacturer_d_name", tok))
                        tok = matcher.brand_hit(d.get("brand_name") or "")
                        if tok:
                            hits.append(("device.brand_name", tok))
                    if hits:
                        excluded_keys.add(key)
                        for f, tok in sorted(set(hits)):
                            audit.append((key, code, f, tok))
    print("reports: %d distinct keys, %d bridge rows, %d excluded" % (len(reports), len(bridge), len(excluded_keys)))

    # quarantine: a report is countable only with an 8-digit receipt date in window
    quarantine: Counter = Counter()
    countable: set[str] = set()
    for key, a in reports.items():
        d = a["date_received"]
        if not re.fullmatch(r"\d{8}", d):
            quarantine[("missing_or_malformed_date_received")] += 1
        elif d > AS_OF:
            quarantine[("received_after_as_of")] += 1
        elif d < WINDOW_START:
            quarantine[("received_before_window")] += 1
        else:
            countable.add(key)
    for code, n in dup_within_code.items():
        quarantine[("duplicate_key_within_%s_pages" % code)] += n

    # ---- DuckDB ---------------------------------------------------------
    if DB.exists():
        DB.unlink()
    con = duckdb.connect(str(DB))
    con.execute("""CREATE TABLE report (mdr_report_key VARCHAR PRIMARY KEY, report_number VARCHAR,
        date_received VARCHAR, date_of_event VARCHAR, date_report VARCHAR, event_type VARCHAR,
        report_source_code VARCHAR, type_of_report VARCHAR, summary_report_flag VARCHAR,
        noe_summarized VARCHAR, number_devices_in_event VARCHAR, n_devices INTEGER,
        device_codes VARCHAR, remedial_action VARCHAR, receipt_month VARCHAR, event_month VARCHAR,
        lag_months INTEGER, excluded BOOLEAN, countable BOOLEAN)""")
    rows = []
    for key, a in reports.items():
        rm, em = month_of(a["date_received"]), month_of(a["date_of_event"])
        lag = lag_months(a["date_of_event"], a["date_received"]) if (rm and em) else None
        rows.append((key, a["report_number"], a["date_received"], a["date_of_event"], a["date_report"],
                     a["event_type"], a["report_source_code"], a["type_of_report"], a["summary_report_flag"],
                     a["noe_summarized"], a["number_devices_in_event"], a["n_devices"], a["device_codes"],
                     a["remedial_action"], rm, em, lag, key in excluded_keys, key in countable))
    # Bulk loads through pandas frames: executemany on 650,000 rows ran for
    # the better part of an hour on 2026-10-06; a registered frame loads in
    # seconds and the row content is identical.
    import pandas as pd
    report_cols = ["mdr_report_key", "report_number", "date_received", "date_of_event", "date_report",
                   "event_type", "report_source_code", "type_of_report", "summary_report_flag",
                   "noe_summarized", "number_devices_in_event", "n_devices", "device_codes",
                   "remedial_action", "receipt_month", "event_month", "lag_months", "excluded", "countable"]
    df_report = pd.DataFrame(rows, columns=report_cols)
    df_report["lag_months"] = df_report["lag_months"].astype("Int64")
    con.register("df_report", df_report)
    con.execute("INSERT INTO report SELECT * FROM df_report")
    con.unregister("df_report")
    con.execute("CREATE TABLE report_product_code (mdr_report_key VARCHAR, product_code VARCHAR)")
    df_bridge = pd.DataFrame(sorted(bridge), columns=["mdr_report_key", "product_code"])
    con.register("df_bridge", df_bridge)
    con.execute("INSERT INTO report_product_code SELECT * FROM df_bridge")
    con.unregister("df_bridge")
    con.execute("CREATE TABLE exclusion_audit (mdr_report_key VARCHAR, product_code VARCHAR, field VARCHAR, token VARCHAR)")
    df_audit = pd.DataFrame(audit, columns=["mdr_report_key", "product_code", "field", "token"])
    con.register("df_audit", df_audit)
    con.execute("INSERT INTO exclusion_audit SELECT * FROM df_audit")
    con.unregister("df_audit")

    # ---- M-01 monthly_report_count -------------------------------------
    series = {}
    for code in COHORT:
        data = json.loads((COUNTS / ("%s_date_received.json" % code)).read_text(encoding="utf-8"))
        s: Counter = Counter()
        for r in data["results"]:
            if WINDOW_START <= r["time"] <= WINDOW_END:
                s[r["time"][:6]] += r["count"]
        series[code] = s
    m01 = con.execute("""
        SELECT b.product_code, r.receipt_month,
               count(DISTINCT r.mdr_report_key) AS raw_reports,
               count(DISTINCT CASE WHEN r.excluded THEN r.mdr_report_key END) AS excluded_reports,
               count(DISTINCT CASE WHEN NOT r.excluded THEN r.mdr_report_key END) AS eligible_reports
        FROM report r JOIN report_product_code b USING (mdr_report_key)
        WHERE r.countable
        GROUP BY 1, 2 ORDER BY 1, 2""").fetchall()
    months = [("%d%02d" % (y, m)) for y in range(2016, 2027) for m in range(1, 13)
              if WINDOW_START[:6] <= "%d%02d" % (y, m) <= WINDOW_END[:6]]
    got = {(c, m): (raw, ex, el) for c, m, raw, ex, el in m01}
    m01_rows = []
    for code in COHORT:
        for m in months:
            raw, ex, el = got.get((code, m), (0, 0, 0))
            srs = series[code].get(m, 0)
            m01_rows.append({"product_code": code, "month": "%s-%s" % (m[:4], m[4:]),
                             "raw_reports": raw, "series_reports": srs, "variance_raw_vs_series": raw - srs,
                             "excluded_reports": ex, "eligible_reports": el})
    write_csv(CONF / "monthly_report_count.csv", m01_rows)
    var = [r for r in m01_rows if r["variance_raw_vs_series"] != 0]
    print("M-01: %d code-months; %d with variance against the S-02 series" % (len(m01_rows), len(var)))

    # ---- M-02 lag matched (eligible, countable) --------------------------
    lag_rows, summary_rows = [], []
    for code in COHORT:
        recs = con.execute("""
            SELECT r.mdr_report_key, r.date_of_event, r.date_received
            FROM report r JOIN report_product_code b USING (mdr_report_key)
            WHERE b.product_code = ? AND r.countable AND NOT r.excluded""", [code]).fetchall()
        lm = golden_lag_matched([{"mdr_report_key": k, "date_of_event": e, "date_received": d} for k, e, d in recs])
        missing = lm.pop("_missing_event_date")
        for em in sorted(lm):
            if WINDOW_START[:4] + "-01" <= em <= WINDOW_END[:4] + "-" + WINDOW_END[4:6]:
                row = {"product_code": code, "event_month": em}
                row.update(lm[em])
                lag_rows.append(row)
        pre = sum(v["reports_with_event_month"] for k, v in lm.items() if k < WINDOW_START[:4] + "-01")
        summary_rows.append({"product_code": code, "eligible_reports": len(recs),
                             "missing_event_date": missing,
                             "event_month_before_window": pre,
                             "negative_lag": sum(v["negative_lag"] for v in lm.values())})
    write_csv(CONF / "monthly_lag_matched.csv", lag_rows)
    write_csv(CONF / "lag_summary.csv", summary_rows)
    print("M-02: %d code-event-months" % len(lag_rows))

    # ---- quarantine ----------------------------------------------------
    write_csv(CONF / "quarantine.csv", [{"reason": k, "reports": v} for k, v in sorted(quarantine.items())]
              or [{"reason": "none", "reports": 0}])

    # ---- exclusion receipt (public) and audit (private) ------------------
    receipt = con.execute("""
        SELECT product_code, field, count(DISTINCT mdr_report_key) AS reports_matched
        FROM exclusion_audit GROUP BY 1, 2 ORDER BY 1, 2""").fetchall()
    removed = dict(con.execute("""
        SELECT b.product_code, count(DISTINCT r.mdr_report_key)
        FROM report r JOIN report_product_code b USING (mdr_report_key)
        WHERE r.excluded AND r.countable GROUP BY 1""").fetchall())
    totals = dict(con.execute("""
        SELECT b.product_code, count(DISTINCT r.mdr_report_key)
        FROM report r JOIN report_product_code b USING (mdr_report_key)
        WHERE r.countable GROUP BY 1""").fetchall())
    rec_rows = [{"product_code": c, "field": f, "reports_matched": n} for c, f, n in receipt]
    for code in COHORT:
        rec_rows.append({"product_code": code, "field": "ANY (reports removed)", "reports_matched": removed.get(code, 0)})
        rec_rows.append({"product_code": code, "field": "ALL (countable reports)", "reports_matched": totals.get(code, 0)})
    write_csv(CONF / "exclusion_receipt.csv", sorted(rec_rows, key=lambda r: (r["product_code"], r["field"])))
    write_csv(GOV / "exclusion_audit.csv", [{"mdr_report_key": k, "product_code": c, "field": f, "token": t}
                                            for k, c, f, t in audit])
    sha = hashlib.sha256(LOCAL.read_bytes()).hexdigest()
    L = ["# Exclusion receipt, record level", "",
         "*Generated by `src/build_model.py`. Regenerate; do not hand-edit. The private",
         "list's SHA-256 at build time was `%s`.*" % sha, "",
         "Reports whose manufacturer or brand fields matched the private list were",
         "removed whole from every series before anything was counted. Counts per",
         "field can overlap (one report can match on two fields); the ANY row is the",
         "number of reports removed.", "",
         "| Code | Countable reports | Removed | Share |", "|---|---:|---:|---:|"]
    for code in COHORT:
        t, rmv = totals.get(code, 0), removed.get(code, 0)
        L.append("| %s | %s | %s | %.2f%% |" % (code, format(t, ","), format(rmv, ","), 100.0 * rmv / t if t else 0))
    L += ["", "| Code | Field | Reports matched |", "|---|---|---:|"]
    for c, f, n in receipt:
        L.append("| %s | `%s` | %s |" % (c, f, format(n, ",")))
    (GOV / "exclusion-receipt-records.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")

    # ---- monthly event type mix (eligible) -------------------------------
    mix = con.execute("""
        SELECT b.product_code, r.receipt_month, coalesce(nullif(r.event_type, ''), 'blank') AS event_type,
               count(DISTINCT r.mdr_report_key) AS eligible_reports
        FROM report r JOIN report_product_code b USING (mdr_report_key)
        WHERE r.countable AND NOT r.excluded GROUP BY 1, 2, 3 ORDER BY 1, 2, 3""").fetchall()
    write_csv(CONF / "monthly_event_type.csv",
              [{"product_code": c, "month": "%s-%s" % (m[:4], m[4:]), "event_type": t, "eligible_reports": n}
               for c, m, t, n in mix])

    # ---- reports whose remedial action includes a recall (pre-registration 6)
    rem = con.execute("""
        SELECT b.product_code, r.receipt_month, count(DISTINCT r.mdr_report_key)
        FROM report r JOIN report_product_code b USING (mdr_report_key)
        WHERE r.countable AND NOT r.excluded AND lower(r.remedial_action) LIKE '%recall%'
        GROUP BY 1, 2 ORDER BY 1, 2""").fetchall()
    write_csv(CONF / "monthly_remedial_recall.csv",
              [{"product_code": c, "month": "%s-%s" % (m[:4], m[4:]), "eligible_reports_with_recall_action": n}
               for c, m, n in rem] or [{"product_code": "", "month": "", "eligible_reports_with_recall_action": 0}])

    # ---- product codes -------------------------------------------------
    cls = load_classification()
    write_csv(REF / "product_code_classification.csv", [cls[c] for c in sorted(cls)])
    excluded_set = {r["product_code"] for r in read_csv(REF / "excluded_product_codes.csv")}
    pc_rows = []
    for code in COHORT + REFERENCE:
        row = dict(cls.get(code, {c: "" for c in CLASS_COLS}))
        row["product_code"] = code
        row["in_cohort"] = "true" if code in COHORT else "false"
        row["reference_only"] = "true" if code in REFERENCE else "false"
        row["in_excluded_set"] = "true" if code in excluded_set else "false"
        pc_rows.append(row)

    # ---- cohort gate stage B --------------------------------------------
    gate = read_csv(CONF / "cohort_gate.csv")
    elig_train = dict(con.execute("""
        SELECT b.product_code, count(DISTINCT r.mdr_report_key)
        FROM report r JOIN report_product_code b USING (mdr_report_key)
        WHERE r.countable AND NOT r.excluded AND r.receipt_month BETWEEN ? AND ?
        GROUP BY 1""", [TRAIN_START, TRAIN_END]).fetchall())
    for g in gate:
        n = elig_train.get(g["product_code"], 0)
        g["eligible_training_reports"] = n
        g["stage_b_pass"] = "true" if n >= MIN_ELIGIBLE_TRAINING else "false"
        g["forecast"] = "true" if (g["stage_a_pass"] == "true" and g["stage_b_pass"] == "true") else "false"
        print("  gate %s: eligible training %6d  stage B %s  forecast %s"
              % (g["product_code"], n, "PASS" if g["stage_b_pass"] == "true" else "FAIL", g["forecast"]))
    write_csv(CONF / "cohort_gate.csv", gate)
    forecast_codes = {g["product_code"] for g in gate if g["forecast"] == "true"}
    for row in pc_rows:
        row["forecast"] = "true" if row["product_code"] in forecast_codes else "false"
    write_csv(CONF / "product_code.csv", pc_rows)
    print("cohort: %d of %d codes forecast" % (len(forecast_codes), len(COHORT)))

    con.close()
    print("wrote %s and the conformed tables" % DB.relative_to(REPO).as_posix())
    return 0


def write_csv(path: pathlib.Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def read_csv(path: pathlib.Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


if __name__ == "__main__":
    sys.exit(main())
