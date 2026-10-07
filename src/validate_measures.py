"""validate_measures.py -- PATH 2: re-derive every certified cell independently.

This script does NOT read data/conformed/early_warning.duckdb and imports
nothing from build_model.py, forecast.py, score.py or review.py. It goes back
to the staged pages with DuckDB's JSON reader and SQL, applies the private
token list as SQL regular expressions, re-derives the monthly counts, the
lag-matched counts, the baselines, the candidate's points from the exported
states by its own recurrence, the empirical ranges by SQL quantiles over the
exported errors, the scores and the review episodes, and compares each with
what the engine published, cell by cell.

It also re-derives the figures the page build computes and writes to no
table (the distinct report totals across the codes, the queue with and
without its coverage gate, chart 4's flagged months), and compares them with
each built page's data block.

What it does NOT cover, stated so the page cannot claim more: M-06 (the
recall context), the cohort gate, the exclusion receipt as a table, the
reports without an event date, the promotion decision and the outlook's
twenty dots. It is DuckDB SQL plus its own Python arithmetic, not SQL alone,
and it consumes the engine's published points and states as inputs to the
ranges and scores: a chain of verified links, not an end-to-end rebuild. A
measure that only agrees with itself has not been validated. Written from
governance/metric_register.md,
governance/decision-record.md and config/model.json, never by reading the
engine.

Exit 0 means every published cell reconciles. Exit 1 means at least one does
not, and the failing cells are printed. Publish nothing on exit 1.

    python src/validate_measures.py
"""
from __future__ import annotations

import csv
import json
import math
import pathlib
import re
import sys

import duckdb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = pathlib.Path(__file__).resolve().parent.parent
CONF = REPO / "data" / "conformed"
STAGING = REPO / "data" / "raw" / "staging" / "event"
COUNTS = REPO / "data" / "raw" / "counts"
DOCS = REPO / "docs"
LOCAL = REPO / "governance" / "exclusion-list.local.txt"
CONFIG = REPO / "config" / "model.json"
WINDOW_START, WINDOW_END = "20160101", "20260831"
TRAIN_START, TRAIN_END = "201601", "202312"
TOL = 1e-4


# ---------------------------------------------------------------------------
# golden API (Path 2): SQL and a separately written recurrence
# ---------------------------------------------------------------------------

def _con() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(":memory:")


def golden_baselines(series: dict[str, int], origin: str, horizon: int) -> dict:
    con = _con()
    con.execute("CREATE TABLE s (month VARCHAR, y DOUBLE)")
    con.executemany("INSERT INTO s VALUES (?, ?)", [(m, float(v)) for m, v in series.items()])
    # months as integers so arithmetic is explicit
    con.execute("""CREATE VIEW si AS SELECT month, y,
                   CAST(substr(month,1,4) AS INT)*12 + CAST(substr(month,6,2) AS INT) AS mi FROM s""")
    o = int(origin[:4]) * 12 + int(origin[5:7])
    a = con.execute("""SELECT CASE WHEN count(*) = 3 THEN avg(y) END FROM si
                       WHERE mi BETWEEN ? - 2 AND ?""", [o, o]).fetchone()[0]
    b = con.execute("SELECT y FROM si WHERE mi = ? + ? - 12", [o, horizon]).fetchone()
    return {"baseline_a": None if a is None else float(a), "baseline_b": None if b is None else float(b[0])}


def golden_ets_point(level: float, trend: float, phi: float, seasonals: list[float], h: int) -> float:
    damp, p = 0.0, 1.0
    for _ in range(h):
        p *= phi
        damp += p
    season_index = (h - 1) - 12 * ((h - 1) // 12)
    return level + trend * damp + seasonals[season_index]


def golden_episodes(rows: list[dict]) -> list[tuple[str, str, int]]:
    con = _con()
    con.execute("CREATE TABLE r (target VARCHAR, actual DOUBLE, point DOUBLE, upper80 DOUBLE)")
    con.executemany("INSERT INTO r VALUES (?,?,?,?)",
                    [(r["target"], float(r["actual"]), float(r["point"]), float(r["upper80"])) for r in rows])
    out = con.execute("""
        WITH f AS (
          SELECT target, (actual > upper80 AND actual - point >= 5) AS flag FROM r),
        g AS (
          SELECT target, flag,
                 sum(CASE WHEN flag THEN 0 ELSE 1 END) OVER (ORDER BY target ROWS UNBOUNDED PRECEDING) AS grp
          FROM f)
        SELECT min(target), max(target), count(*) FROM g WHERE flag GROUP BY grp HAVING count(*) >= 2
        ORDER BY 1""").fetchall()
    return [(a, b, int(n)) for a, b, n in out]


def golden_lag_matched(reports: list[dict]) -> dict:
    con = _con()
    con.execute("CREATE TABLE r (k VARCHAR, ev VARCHAR, rc VARCHAR)")
    con.executemany("INSERT INTO r VALUES (?,?,?)",
                    [(r["mdr_report_key"], (r.get("date_of_event") or "").strip(), (r.get("date_received") or "").strip())
                     for r in reports])
    rows = con.execute("""
        WITH v AS (
          SELECT k, ev, rc,
                 regexp_matches(ev, '^[0-9]{8}$') AS ev_ok, regexp_matches(rc, '^[0-9]{8}$') AS rc_ok
          FROM r),
        l AS (
          SELECT substr(ev,1,4) || '-' || substr(ev,5,2) AS em,
                 (CAST(substr(rc,1,4) AS INT)*12 + CAST(substr(rc,5,2) AS INT))
                 - (CAST(substr(ev,1,4) AS INT)*12 + CAST(substr(ev,5,2) AS INT)) AS lag
          FROM v WHERE ev_ok AND rc_ok)
        SELECT em, count(*),
               sum(CASE WHEN lag BETWEEN 0 AND 3 THEN 1 ELSE 0 END),
               sum(CASE WHEN lag BETWEEN 0 AND 6 THEN 1 ELSE 0 END),
               sum(CASE WHEN lag BETWEEN 0 AND 12 THEN 1 ELSE 0 END),
               sum(CASE WHEN lag < 0 THEN 1 ELSE 0 END)
        FROM l GROUP BY em ORDER BY em""").fetchall()
    missing = con.execute("SELECT count(*) FROM r WHERE NOT regexp_matches(ev, '^[0-9]{8}$')").fetchone()[0]
    out = {em: {"reports_with_event_month": int(n), "within_3": int(w3), "within_6": int(w6),
                "within_12": int(w12), "negative_lag": int(neg)} for em, n, w3, w6, w12, neg in rows}
    out["_missing_event_date"] = int(missing)
    return out


def golden_scores(rows: list[dict]) -> dict:
    con = _con()
    con.execute("CREATE TABLE r (y DOUBLE, m DOUBLE, l50 DOUBLE, u50 DOUBLE, l80 DOUBLE, u80 DOUBLE)")
    con.executemany("INSERT INTO r VALUES (?,?,?,?,?,?)",
                    [(r["actual"], r["point"], r["lower50"], r["upper50"], r["lower80"], r["upper80"]) for r in rows])
    n, mae, c50, c80, w50, w80, w = con.execute("""
        SELECT count(*), avg(abs(y - m)),
               avg(CASE WHEN y BETWEEN l50 AND u50 THEN 1.0 ELSE 0.0 END),
               avg(CASE WHEN y BETWEEN l80 AND u80 THEN 1.0 ELSE 0.0 END),
               avg(u50 - l50), avg(u80 - l80),
               avg((0.5*abs(y - m)
                    + 0.25*((u50 - l50) + CASE WHEN y < l50 THEN 4.0*(l50 - y) ELSE 0 END
                                        + CASE WHEN y > u50 THEN 4.0*(y - u50) ELSE 0 END)
                    + 0.10*((u80 - l80) + CASE WHEN y < l80 THEN 10.0*(l80 - y) ELSE 0 END
                                        + CASE WHEN y > u80 THEN 10.0*(y - u80) ELSE 0 END)) / 2.5)
        FROM r""").fetchone()
    return {"n": int(n), "mae": mae, "coverage50": c50, "coverage80": c80, "width50": w50, "width80": w80, "wis": w}


# ---------------------------------------------------------------------------
# the private list as SQL patterns
# ---------------------------------------------------------------------------

def private_patterns() -> dict[str, str]:
    if not LOCAL.exists():
        sys.exit("the private exclusion list is absent; the exclusion cannot be re-derived")
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
    return {k: r"\b(?:" + "|".join(sections[k]) + ")" for k in ("firm_tokens", "not_firm_tokens", "brand_tokens")}


def read_csv(path: pathlib.Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------------------
# main: re-derive and compare
# ---------------------------------------------------------------------------

def main() -> int:
    failures: list[str] = []
    checked = 0

    def fail(msg: str) -> None:
        failures.append(msg)

    pat = private_patterns()
    con = duckdb.connect(":memory:")
    con.execute("SET preserve_insertion_order = false")

    # -- the staged pages, via DuckDB's JSON reader -----------------------
    files = sorted(STAGING.glob("*/*.json.gz"))
    if not files:
        sys.exit("no staged pages under %s" % STAGING)
    # ONE PAGE AT A TIME. Materializing every page's JSON in one table ran the
    # process out of memory on 2026-10-06 (696 pages, about 3.5 GB of text);
    # each page is read, reduced to the ten fields this path needs, and
    # appended, so nothing larger than one page is ever held.
    con.execute("""
        CREATE TABLE rec (code VARCHAR, k VARCHAR, rc VARCHAR, ev VARCHAR, event_type VARCHAR,
                          mn VARCHAR, mg VARCHAR, dn VARCHAR, dmn VARCHAR[], dbn VARCHAR[])
    """)
    for i, f in enumerate(files, 1):
        code = f.parent.name
        con.execute(r"""
            INSERT INTO rec
            SELECT ? AS code,
                   json_extract_string(r, '$.mdr_report_key') AS k,
                   coalesce(json_extract_string(r, '$.date_received'), '') AS rc,
                   coalesce(json_extract_string(r, '$.date_of_event'), '') AS ev,
                   coalesce(json_extract_string(r, '$.event_type'), '') AS event_type,
                   coalesce(json_extract_string(r, '$.manufacturer_name'), '') AS mn,
                   coalesce(json_extract_string(r, '$.manufacturer_g1_name'), '') AS mg,
                   coalesce(json_extract_string(r, '$.distributor_name'), '') AS dn,
                   coalesce(json_extract_string(r, '$.device[*].manufacturer_d_name'), []) AS dmn,
                   coalesce(json_extract_string(r, '$.device[*].brand_name'), []) AS dbn
            FROM (SELECT unnest(json_extract(results, '$[*]')) AS r
                  FROM read_json(?, columns={'meta': 'JSON', 'results': 'JSON'},
                                 maximum_object_size=268435456))
        """, [code, f.as_posix()])
        if i % 100 == 0:
            print("  %d of %d pages read" % (i, len(files)))
    n_rec = con.execute("SELECT count(*) FROM rec").fetchone()[0]
    print("staged records read: %s from %d pages" % (format(n_rec, ","), len(files)))

    # exclusion in SQL: per field value, not-firm first, then firm; brand on brand
    firm, notf, brand = pat["firm_tokens"], pat["not_firm_tokens"], pat["brand_tokens"]
    con.execute("""
        CREATE MACRO firm_hit(s) AS (regexp_replace(s, '\\s+', ' ', 'g') <> ''
            AND NOT regexp_matches(regexp_replace(s, '\\s+', ' ', 'g'), $notf$, 'i')
            AND regexp_matches(regexp_replace(s, '\\s+', ' ', 'g'), $firm$, 'i'))
    """.replace("$notf$", "'" + notf.replace("'", "''") + "'").replace("$firm$", "'" + firm.replace("'", "''") + "'"))
    con.execute("""
        CREATE MACRO brand_hit(s) AS (regexp_replace(s, '\\s+', ' ', 'g') <> ''
            AND regexp_matches(regexp_replace(s, '\\s+', ' ', 'g'), $brand$, 'i'))
    """.replace("$brand$", "'" + brand.replace("'", "''") + "'"))
    con.execute("""
        CREATE TABLE rep AS
        SELECT k, any_value(rc) AS rc, any_value(ev) AS ev, any_value(event_type) AS event_type,
               bool_or(firm_hit(mn) OR firm_hit(mg) OR firm_hit(dn)
                       OR list_bool_or(list_transform(dmn, x -> firm_hit(coalesce(x, ''))))
                       OR list_bool_or(list_transform(dbn, x -> brand_hit(coalesce(x, ''))))) AS excluded
        FROM rec GROUP BY k
    """)
    con.execute("CREATE TABLE br AS SELECT DISTINCT k, code FROM rec")
    con.execute("""
        CREATE VIEW cnt AS
        SELECT b.code, substr(p.rc,1,4) || '-' || substr(p.rc,5,2) AS month, p.k, p.excluded, p.ev, p.rc
        FROM rep p JOIN br b USING (k)
        WHERE regexp_matches(p.rc, '^[0-9]{8}$') AND p.rc BETWEEN ? AND ?
    """.replace("?", "'" + WINDOW_START + "'", 1).replace("?", "'" + WINDOW_END + "'", 1))

    # -- M-01 ------------------------------------------------------------
    m01 = read_csv(CONF / "monthly_report_count.csv")
    got = {(r[0], r[1]): (int(r[2]), int(r[3]), int(r[4])) for r in con.execute("""
        SELECT code, month, count(DISTINCT k), count(DISTINCT CASE WHEN excluded THEN k END),
               count(DISTINCT CASE WHEN NOT excluded THEN k END)
        FROM cnt GROUP BY 1, 2""").fetchall()}
    for r in m01:
        checked += 1
        raw, ex, el = got.get((r["product_code"], r["month"]), (0, 0, 0))
        if (raw, ex, el) != (int(r["raw_reports"]), int(r["excluded_reports"]), int(r["eligible_reports"])):
            fail("M-01 %s %s: published raw/excluded/eligible %s/%s/%s, re-derived %d/%d/%d"
                 % (r["product_code"], r["month"], r["raw_reports"], r["excluded_reports"], r["eligible_reports"], raw, ex, el))
        # and the S-02 series, read here from the raw count files
    series_ok = 0
    for code in sorted({r["product_code"] for r in m01}):
        data = json.loads((COUNTS / ("%s_date_received.json" % code)).read_text(encoding="utf-8"))
        s: dict[str, int] = {}
        for b in data["results"]:
            if WINDOW_START <= b["time"] <= WINDOW_END:
                m = b["time"][:4] + "-" + b["time"][4:6]
                s[m] = s.get(m, 0) + b["count"]
        for r in m01:
            if r["product_code"] == code:
                checked += 1
                if int(r["series_reports"]) != s.get(r["month"], 0):
                    fail("M-01 %s %s: series_reports %s but the S-02 file says %d" % (code, r["month"], r["series_reports"], s.get(r["month"], 0)))
                elif int(r["raw_reports"]) != s.get(r["month"], 0):
                    fail("M-01 %s %s: raw %s differs from the series %d" % (code, r["month"], r["raw_reports"], s.get(r["month"], 0)))
                else:
                    series_ok += 1
    print("M-01: %d code-months compared; %d tie to the S-02 series" % (len(m01), series_ok))

    # -- M-02 ------------------------------------------------------------
    m02 = read_csv(CONF / "monthly_lag_matched.csv")
    lag = {}
    for r in con.execute("""
        WITH l AS (
          SELECT code, substr(ev,1,4) || '-' || substr(ev,5,2) AS em,
                 (CAST(substr(rc,1,4) AS INT)*12 + CAST(substr(rc,5,2) AS INT))
                 - (CAST(substr(ev,1,4) AS INT)*12 + CAST(substr(ev,5,2) AS INT)) AS lag
          FROM cnt WHERE NOT excluded AND regexp_matches(ev, '^[0-9]{8}$'))
        SELECT code, em, count(*),
               sum(CASE WHEN lag BETWEEN 0 AND 3 THEN 1 ELSE 0 END),
               sum(CASE WHEN lag BETWEEN 0 AND 6 THEN 1 ELSE 0 END),
               sum(CASE WHEN lag BETWEEN 0 AND 12 THEN 1 ELSE 0 END),
               sum(CASE WHEN lag < 0 THEN 1 ELSE 0 END)
        FROM l GROUP BY 1, 2""").fetchall():
        lag[(r[0], r[1])] = tuple(int(x) for x in r[2:])
    for r in m02:
        checked += 1
        want = tuple(int(r[c]) for c in ("reports_with_event_month", "within_3", "within_6", "within_12", "negative_lag"))
        if lag.get((r["product_code"], r["event_month"])) != want:
            fail("M-02 %s %s: published %s, re-derived %s" % (r["product_code"], r["event_month"], want, lag.get((r["product_code"], r["event_month"]))))
    print("M-02: %d code-event-months compared" % len(m02))

    # -- M-03 mechanics ------------------------------------------------------
    if not (CONF / "forecast.csv").exists():
        print("M-03 to M-05: not yet built; only M-01 and M-02 were re-derived")
        return report(checked, failures)
    fc = read_csv(CONF / "forecast.csv")
    states = {(r["product_code"], r["origin"]): r for r in read_csv(CONF / "forecast_states.csv")}
    elig = {(r["product_code"], r["month"]): float(r["eligible_reports"]) for r in m01}
    con.execute("CREATE TABLE e (code VARCHAR, month VARCHAR, y DOUBLE)")
    con.executemany("INSERT INTO e VALUES (?,?,?)", [(c, m, y) for (c, m), y in elig.items()])
    con.execute("""CREATE VIEW ei AS SELECT code, month, y,
                   CAST(substr(month,1,4) AS INT)*12 + CAST(substr(month,6,2) AS INT) AS mi FROM e""")
    ba = {(r[0], r[1]): r[2] for r in con.execute("""
        SELECT code, month, CASE WHEN count(*) OVER w = 3 THEN avg(y) OVER w END
        FROM ei WINDOW w AS (PARTITION BY code ORDER BY mi ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)""").fetchall()}
    n_pts = 0
    for r in fc:
        if r["point"] == "":
            continue
        pt = float(r["point"])
        code, o, t, h = r["product_code"], r["origin"], r["target"], int(r["horizon"])
        if r["model"] == "baseline_a":
            exp = ba.get((code, o))
        elif r["model"] == "baseline_b":
            ti = int(t[:4]) * 12 + int(t[5:7]) - 12
            exp = elig.get((code, "%04d-%02d" % ((ti - 1) // 12, (ti - 1) % 12 + 1)))
        else:
            st = states.get((code, o))
            if not st or st.get("fit_error"):
                fail("M-03 %s %s candidate: a point exists but no exported states" % (code, o))
                continue
            lp = golden_ets_point(float(st["level"]), float(st["trend"]), float(st["damping_trend"]),
                                  [float(st["s%d" % i]) for i in range(1, 13)], h)
            exp = max(0.0, math.expm1(lp))
        checked += 1
        n_pts += 1
        if exp is None or abs(exp - pt) > TOL * max(1.0, abs(pt)):
            fail("M-03 %s %s %s h%d: published point %s, re-derived %s" % (code, r["model"], o, h, r["point"], exp))
    # ranges: quantiles over the 36 latest elapsed errors, in SQL
    con.execute("CREATE TABLE f (code VARCHAR, model VARCHAR, h INT, origin VARCHAR, target VARCHAR, pt DOUBLE)")
    con.executemany("INSERT INTO f VALUES (?,?,?,?,?,?)",
                    [(r["product_code"], r["model"], int(r["horizon"]), r["origin"], r["target"],
                      None if r["point"] == "" else float(r["point"])) for r in fc])
    rng = {}
    for row in con.execute("""
        WITH err AS (
          SELECT f.code, f.model, f.h, f.target, e.y - f.pt AS err
          FROM f JOIN e ON e.code = f.code AND e.month = f.target WHERE f.pt IS NOT NULL),
        pairs AS (
          SELECT r.code, r.model, r.h, r.origin, x.err,
                 row_number() OVER (PARTITION BY r.code, r.model, r.h, r.origin ORDER BY x.target DESC) AS rn
          FROM f r JOIN err x ON x.code = r.code AND x.model = r.model AND x.h = r.h AND x.target <= r.origin)
        SELECT code, model, h, origin, count(*), quantile_cont(err, 0.25), quantile_cont(err, 0.75),
               quantile_cont(err, 0.10), quantile_cont(err, 0.90)
        FROM pairs WHERE rn <= 36 GROUP BY 1,2,3,4""").fetchall():
        rng[(row[0], row[1], int(row[2]), row[3])] = row[4:]
    n_rng = 0
    for r in fc:
        key = (r["product_code"], r["model"], int(r["horizon"]), r["origin"])
        n, q25, q75, q10, q90 = rng.get(key, (0, None, None, None, None))
        checked += 1
        if int(r["calibration_n"]) != n:
            fail("M-03 %s calibration_n published %s, re-derived %d" % (key, r["calibration_n"], n))
            continue
        if r["lower80"] == "":
            if n >= 12 and r["point"] != "":
                fail("M-03 %s: no range published although %d errors were available" % (key, n))
            continue
        pt = float(r["point"])
        exp = {"lower50": max(0.0, pt + q25), "upper50": max(0.0, pt + q75),
               "lower80": max(0.0, pt + q10), "upper80": max(0.0, pt + q90)}
        for c, v in exp.items():
            if abs(v - float(r[c])) > 1e-3 * max(1.0, abs(v)):
                fail("M-03 %s %s: published %s, re-derived %.6f" % (key, c, r[c], v))
                break
        else:
            n_rng += 1
    print("M-03: %d points and %d ranges re-derived" % (n_pts, n_rng))

    # -- M-04 ------------------------------------------------------------
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    if not (CONF / "forecast_score.csv").exists():
        print("M-04 and M-05: not yet built")
        return report(checked, failures)
    sc = read_csv(CONF / "forecast_score.csv")
    scored_rows = []
    for r in fc:
        if r["period"] not in ("development", "locked", "recent") or r["point"] == "" or r["lower80"] == "":
            continue
        y = elig.get((r["product_code"], r["target"]))
        if y is None:
            continue
        scored_rows.append((r["product_code"], r["model"], int(r["horizon"]), r["period"], y, float(r["point"]),
                            float(r["lower50"]), float(r["upper50"]), float(r["lower80"]), float(r["upper80"])))
    con.execute("CREATE TABLE sr (code VARCHAR, model VARCHAR, h INT, period VARCHAR, y DOUBLE, m DOUBLE, l50 DOUBLE, u50 DOUBLE, l80 DOUBLE, u80 DOUBLE)")
    con.executemany("INSERT INTO sr VALUES (?,?,?,?,?,?,?,?,?,?)", scored_rows)
    cells = {}
    for row in con.execute("""
        SELECT code, model, h, period, count(*), avg(abs(y - m)),
               avg(CASE WHEN y BETWEEN l50 AND u50 THEN 1.0 ELSE 0.0 END),
               avg(CASE WHEN y BETWEEN l80 AND u80 THEN 1.0 ELSE 0.0 END),
               avg(u50 - l50), avg(u80 - l80),
               avg((0.5*abs(y - m)
                    + 0.25*((u50 - l50) + CASE WHEN y < l50 THEN 4.0*(l50 - y) ELSE 0 END
                                        + CASE WHEN y > u50 THEN 4.0*(y - u50) ELSE 0 END)
                    + 0.10*((u80 - l80) + CASE WHEN y < l80 THEN 10.0*(l80 - y) ELSE 0 END
                                        + CASE WHEN y > u80 THEN 10.0*(y - u80) ELSE 0 END)) / 2.5)
        FROM sr GROUP BY 1,2,3,4""").fetchall():
        cells[(row[0], row[1], int(row[2]), row[3])] = row[4:]
    for r in sc:
        key = (r["product_code"], r["model"], int(r["horizon"]), r["period"])
        got = cells.get(key)
        checked += 1
        if got is None:
            fail("M-04 %s: published cell has no re-derived counterpart" % (key,))
            continue
        n, mae, c50, c80, w50, w80, w = got
        for name, pub, val in (("n", r["n"], n), ("mae", r["mae"], mae), ("coverage50", r["coverage50"], c50),
                               ("coverage80", r["coverage80"], c80), ("width50", r["width50"], w50),
                               ("width80", r["width80"], w80), ("wis", r["wis"], w)):
            if abs(float(pub) - float(val)) > 1e-4 * max(1.0, abs(float(val))):
                fail("M-04 %s %s: published %s, re-derived %.6f" % (key, name, pub, val))
                break
        base = cells.get((key[0], "baseline_a", key[2], key[3]))
        if base and r["mae_scaled_vs_a"] != "":
            if abs(float(r["mae_scaled_vs_a"]) - mae / base[1]) > 1e-4 * max(1.0, mae / base[1]):
                fail("M-04 %s mae_scaled_vs_a: published %s, re-derived %.6f" % (key, r["mae_scaled_vs_a"], mae / base[1]))
    print("M-04: %d cells compared" % len(sc))

    # -- M-05 ------------------------------------------------------------
    promoted = cfg.get("promoted") or {}
    if not (CONF / "review_queue.csv").exists():
        print("M-05: not yet built")
        return report(checked, failures)
    queue = [r for r in read_csv(CONF / "review_queue.csv") if r["product_code"]]
    work = read_csv(CONF / "review_workload.csv")
    q2 = {}
    for w in work:
        code, use = w["product_code"], w["model_in_use"]
        checked += 1
        if promoted.get(code, {}).get("model_in_use") != use:
            fail("M-05 %s: workload says model %s, config says %s" % (code, use, promoted.get(code, {}).get("model_in_use")))
        cov = [c for c in cells if c == (code, use, 1, "locked")]
        c80 = cells[cov[0]][3] if cov else None
        enabled = c80 is not None and c80 >= 0.70
        if (w["rule_enabled"] == "true") != enabled:
            fail("M-05 %s: rule_enabled published %s, re-derived %s (coverage80 %s)" % (code, w["rule_enabled"], enabled, c80))
        rows = [{"target": t, "actual": y, "point": m, "upper80": u80}
                for (c, mdl, h, per, y, m, l50, u50, l80, u80, t) in
                [(sr[0], sr[1], sr[2], sr[3], sr[4], sr[5], sr[6], sr[7], sr[8], sr[9], fr["target"])
                 for sr, fr in zip(scored_rows, [r for r in fc if r["period"] in ("development", "locked", "recent")
                                                   and r["point"] != "" and r["lower80"] != ""
                                                   and elig.get((r["product_code"], r["target"])) is not None])]
                if c == code and mdl == use and h == 1 and per in ("locked", "recent")]
        ungated = golden_episodes(rows)
        eps = ungated if enabled else []
        pub = [(q["episode_start"], q["episode_end"], int(q["months_in_episode"])) for q in queue if q["product_code"] == code]
        if sorted(eps) != sorted(pub):
            fail("M-05 %s: published episodes %s, re-derived %s" % (code, pub, eps))
        if int(w["evaluated_months"]) != len(rows) or int(w["episodes"]) != len(eps):
            fail("M-05 %s: workload evaluated/episodes %s/%s, re-derived %d/%d" % (code, w["evaluated_months"], w["episodes"], len(rows), len(eps)))
        q2[code] = {"enabled": enabled, "months": len(rows), "ungated": len(ungated), "gated": len(eps), "ungated_eps": sorted(ungated),
                    "flagged": sorted(r["target"] for r in rows if r["actual"] > r["upper80"] and r["actual"] - r["point"] >= 5)}
    print("M-05: %d codes compared, %d published episodes" % (len(work), len(queue)))

    # -- the page's own figures ------------------------------------------------------
    # Some figures are computed by the page build and written to no table: the distinct report
    # totals across the codes (a report can carry two codes, so M-01 summed counts memberships), the
    # queue with and without its coverage gate, and the flagged months chart 4 draws. The page's
    # data block is what publishes them, so that is what they are compared against.
    in_codes = ",".join("'%s'" % c for c in sorted({r["product_code"] for r in m01}))
    d_raw, d_elig, d_mem = con.execute("""
        SELECT count(DISTINCT k), count(DISTINCT CASE WHEN NOT excluded THEN k END), count(*)
        FROM cnt WHERE code IN (%s)""" % in_codes).fetchone()
    d_multi = con.execute("SELECT count(*) FROM (SELECT k FROM cnt WHERE code IN (%s) GROUP BY k HAVING count(*) > 1)" % in_codes).fetchone()[0]
    reports2 = {"distinctRaw": int(d_raw), "distinctEligible": int(d_elig), "memberships": int(d_mem), "multiCodeReports": int(d_multi)}
    print("reports: %d distinct, %d distinct eligible, %d report-code memberships, %d reports in more than one code"
          % (d_raw, d_elig, d_mem, d_multi))
    n_page = 0
    for page in sorted(DOCS.glob("*.html")):
        if "template" in page.name:
            continue
        data = page_data(page)
        if data is None:
            fail("page %s: no cascadia-data block to compare" % page.name)
            continue
        facts = data.get("facts", {})
        checked += 1
        if facts.get("reports") != reports2:
            fail("page %s report totals: published %s, re-derived %s" % (page.name, facts.get("reports"), reports2))
        want = {"gatedEpisodes": sum(v["gated"] for v in q2.values()), "ungatedEpisodes": sum(v["ungated"] for v in q2.values()),
                "enabledMonths": sum(v["months"] for v in q2.values() if v["enabled"]),
                "evaluatedMonths": sum(v["months"] for v in q2.values())}
        got = facts.get("queue")
        checked += 1
        if not got:
            fail("page %s: the data block carries no queue figures" % page.name)
        else:
            for k, v in want.items():
                if got.get(k) != v:
                    fail("page %s queue %s: published %s, re-derived %s" % (page.name, k, got.get(k), v))
            for code, v in q2.items():
                pc = got.get("perCode", {}).get(code, {})
                if (pc.get("ungated"), pc.get("flagged")) != (v["ungated"], len(v["flagged"])):
                    fail("page %s queue %s: published ungated/flagged %s/%s, re-derived %d/%d"
                         % (page.name, code, pc.get("ungated"), pc.get("flagged"), v["ungated"], len(v["flagged"])))
        for lane in (data.get("c4") or {}).get("lanes", []):
            checked += 2
            if sorted(lane["flagged"]) != q2.get(lane["code"], {}).get("flagged"):
                fail("page %s chart 4 %s: draws flagged months %s, re-derived %s" % (page.name, lane["code"], lane["flagged"], q2.get(lane["code"], {}).get("flagged")))
            drawn = sorted((e["start"], e["end"], int(e["months"])) for e in lane.get("ungated", []))
            if drawn != q2.get(lane["code"], {}).get("ungated_eps"):
                fail("page %s chart 4 %s: carries episodes-if-on %s, re-derived %s" % (page.name, lane["code"], drawn, q2.get(lane["code"], {}).get("ungated_eps")))
        n_page += 1
    if not n_page:
        fail("no built page under docs/ to compare")
    print("page: %d page(s) compared (distinct report totals, queue with and without the gate, chart 4's flagged months and episodes)" % n_page)

    return report(checked, failures)


def page_data(path: pathlib.Path):
    m = re.search(r'<script id="cascadia-data" type="application/json">(.*?)</script>', path.read_text(encoding="utf-8"), re.S)
    return json.loads(m.group(1)) if m else None


def report(checked: int, failures: list[str]) -> int:
    print("\n%d cells checked" % checked)
    if failures:
        print("%d MISMATCH(ES):" % len(failures))
        for f in failures[:40]:
            print("  " + f)
        if len(failures) > 40:
            print("  ... and %d more" % (len(failures) - 40))
        print("\nVALIDATE MEASURES: FAILED. Publish nothing.")
        return 1
    print("\nVALIDATE MEASURES: PASSED. Every cell this path re-derives reconciles with what was published.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
