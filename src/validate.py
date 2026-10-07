"""validate.py -- the domain gate. Exits non-zero on any failure (PRINCIPLES rule 8).

Checks the things the register and the decision record say must be true of
the frozen inputs and the published tables. It does NOT compare Path 1 with
Path 2 (that is src/validate_measures.py) and it does NOT check the committed
freeze (that is src/validate_freeze.py). Run all three, plus src/test_golden.py.

    python src/validate.py                  the checks
    python src/validate.py --prove-failable the checks, then each one fed
                                            deliberately wrong data that it
                                            must reject; the report carries a
                                            "Proof the checks can fail" section

Writes governance/validation_report.md on every run. The names gate never
prints a token: a hit names the file and nothing else.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from contextlib import contextmanager
from datetime import date

import duckdb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = pathlib.Path(__file__).resolve().parent.parent
RAW = REPO / "data" / "raw"
CONF = REPO / "data" / "conformed"
GOV = REPO / "governance"
DOCS = REPO / "docs"
MANIFEST = RAW / "manifest.json"
EXTRACTION_LOG = RAW / "extraction_log.json"
M01 = CONF / "monthly_report_count.csv"
DB = CONF / "early_warning.duckdb"
AUDIT = GOV / "exclusion_audit.csv"
RECEIPT = CONF / "exclusion_receipt.csv"
FORECAST = CONF / "forecast.csv"
SCORED = CONF / "forecast_scored.csv"
QUEUE = CONF / "review_queue.csv"
RECALL_CTX = CONF / "recall_context.csv"
CONFIG = REPO / "config" / "model.json"
LOCAL = GOV / "exclusion-list.local.txt"
REPORT = GOV / "validation_report.md"
AS_OF = "20260831"
WINDOW_START = "20160101"
VERBATIM = {".claude/hooks/no_blanket_add_or_force_push.py", ".claude/hooks/hook_test_matrix.py",
            ".githooks/pre-commit", ".githooks/secret_scan.py", ".githooks/no_whitespace_commits.py",
            "src/validate_freeze.py", ".gitattributes",
            # vendored verbatim with a provenance first line; not authored here
            "docs/assets/cascadia-echarts-theme.js", "docs/assets/echarts.min.js",
            # copied byte for byte from cascadia-matter-ledger-analytics (D18); not authored here
            ".claude/hooks/no_publish_from_scheduled_runs.py"}
TEXT_EXT = {".md", ".py", ".ps1", ".json", ".csv", ".html", ".js", ".css", ".toml", ".txt", ".qmd", ".yml", ".yaml", ".svg"}


def read_csv(path: pathlib.Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def private_sections() -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    cur = None
    if not LOCAL.exists():
        return sections
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


def tracked_files() -> list[str]:
    r = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True)
    return [p for p in r.stdout.splitlines() if p.strip()]


# ---------------------------------------------------------------------------
# the checks: each appends (name, ok, detail, failures)
# ---------------------------------------------------------------------------

def check_hashes(results):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    bad, n, absent = [], 0, 0
    on_disk = {p.relative_to(REPO).as_posix() for p in (RAW / "staging" / "event").glob("*/*.json.gz")}
    for rel in sorted(on_disk - set(manifest["files"])):
        bad.append("staged page on disk with no manifest entry: %s" % rel)
    for rel, e in manifest["files"].items():
        p = REPO / rel
        if not p.exists():
            if rel.startswith("data/raw/staging/event/"):
                bad.append("staged page absent: %s" % rel)
            else:
                absent += 1
            continue
        if e.get("stored") == "gzip":
            with gzip.open(p, "rb") as gz:
                h = hashlib.sha256(gz.read()).hexdigest()
        else:
            h = hashlib.sha256(p.read_bytes()).hexdigest()
        n += 1
        if h != e["sha256"]:
            bad.append("moved since the freeze: %s" % rel)
    results.append(("freeze hashes: every manifest entry on disk recomputes, and no staged page is unmanifested", not bad,
                    "%d files hashed, %d absent (non-staging), %d staged pages on disk, %d bad" % (n, absent, len(on_disk), len(bad)), bad))


def check_extraction_log(results):
    log = json.loads(EXTRACTION_LOG.read_text(encoding="utf-8"))
    bad = ["%s: %s (expected %s, api %s)" % (k, v["status"], v["expected"], v["api_total"])
           for k, v in log["windows"].items() if v["status"] != "complete" or v["api_total"] != v["expected"]]
    results.append(("extraction log: every window complete and equal to its expected total", not bad,
                    "%d windows" % len(log["windows"]), bad))


def check_m01(results):
    rows = read_csv(M01)
    bad = []
    con = duckdb.connect(str(DB), read_only=True)
    db = {(c, m): (raw, ex) for c, m, raw, ex in con.execute("""
        SELECT b.product_code, substr(r.receipt_month,1,4) || '-' || substr(r.receipt_month,5,2),
               count(DISTINCT r.mdr_report_key), count(DISTINCT CASE WHEN r.excluded THEN r.mdr_report_key END)
        FROM report r JOIN report_product_code b USING (mdr_report_key) WHERE r.countable GROUP BY 1, 2""").fetchall()}
    con.close()
    for r in rows:
        raw, srs, ex, el = (int(r[k]) for k in ("raw_reports", "series_reports", "excluded_reports", "eligible_reports"))
        if raw != srs:
            bad.append("%s %s: raw %d vs independent series %d" % (r["product_code"], r["month"], raw, srs))
        if el != raw - ex:
            bad.append("%s %s: eligible %d is not raw %d minus excluded %d" % (r["product_code"], r["month"], el, raw, ex))
        if db.get((r["product_code"], r["month"]), (0, 0)) != (raw, ex):
            bad.append("%s %s: published raw/excluded %d/%d, record table says %s" % (r["product_code"], r["month"], raw, ex, db.get((r["product_code"], r["month"]))))
    results.append(("raw report count per code-month equals the independent S-02 count series, "
                    "eligible equals raw minus excluded, and the record table agrees", not bad,
                    "%d code-months" % len(rows), bad[:20]))


def check_dates(results):
    con = duckdb.connect(str(DB), read_only=True)
    n_bad_fmt = con.execute("SELECT count(*) FROM report WHERE countable AND NOT regexp_matches(date_received, '^[0-9]{8}$')").fetchone()[0]
    n_future = con.execute("SELECT count(*) FROM report WHERE countable AND date_received > ?", [AS_OF]).fetchone()[0]
    n_early = con.execute("SELECT count(*) FROM report WHERE countable AND date_received < ?", [WINDOW_START]).fetchone()[0]
    total = con.execute("SELECT count(*) FROM report").fetchone()[0]
    countable = con.execute("SELECT count(*) FROM report WHERE countable").fetchone()[0]
    con.close()
    q = read_csv(CONF / "quarantine.csv")
    quarantined = sum(int(r["reports"]) for r in q if not r["reason"].startswith("duplicate_key") and r["reason"] != "none")
    bad = []
    if n_bad_fmt:
        bad.append("%d countable reports without an 8-digit receipt date" % n_bad_fmt)
    if n_future:
        bad.append("%d countable reports received after the as-of date %s" % (n_future, AS_OF))
    if n_early:
        bad.append("%d countable reports received before the window" % n_early)
    if total - countable != quarantined:
        bad.append("%d reports not countable but quarantine accounts for %d" % (total - countable, quarantined))
    results.append(("countable reports carry an 8-digit receipt date inside the window, none after the as-of date, "
                    "and quarantine accounts for the rest", not bad,
                    "%d reports, %d countable, %d quarantined" % (total, countable, quarantined), bad))


def check_uniqueness(results):
    con = duckdb.connect(str(DB), read_only=True)
    dup_keys = con.execute("SELECT count(*) - count(DISTINCT mdr_report_key) FROM report").fetchone()[0]
    dup_bridge = con.execute("SELECT count(*) - count(DISTINCT (mdr_report_key, product_code)) FROM report_product_code").fetchone()[0]
    orphan = con.execute("SELECT count(*) FROM report_product_code b LEFT JOIN report r USING (mdr_report_key) WHERE r.mdr_report_key IS NULL").fetchone()[0]
    con.close()
    bad = []
    if dup_keys:
        bad.append("%d duplicate report keys" % dup_keys)
    if dup_bridge:
        bad.append("%d duplicate (key, code) bridge rows" % dup_bridge)
    if orphan:
        bad.append("%d bridge rows without a report" % orphan)
    results.append(("report keys are unique and the code bridge has no duplicate pair", not bad,
                    "keys unique, bridge pairs unique, no orphans" if not bad else "see failures", bad))


def check_exclusion(results):
    sections = private_sections()
    bad = []
    if not sections:
        results.append(("exclusion receipt agrees with the private audit, and every audit token is in the list", False,
                        "private list absent: the check cannot run and fails closed", ["private list absent"]))
        return
    tokens = re.compile(r"\b(?:%s)" % "|".join(sections["firm_tokens"] + sections["brand_tokens"]), re.I)
    audit = read_csv(AUDIT) if AUDIT.exists() else []
    receipt = read_csv(RECEIPT)
    per_field: dict[tuple[str, str], set[str]] = {}
    removed: dict[str, set[str]] = {}
    for a in audit:
        per_field.setdefault((a["product_code"], a["field"]), set()).add(a["mdr_report_key"])
        removed.setdefault(a["product_code"], set()).add(a["mdr_report_key"])
        if not tokens.fullmatch(a["token"]) and not tokens.match(a["token"]):
            bad.append("an audit token is not in the private list (report %s)" % a["mdr_report_key"])
    con = duckdb.connect(str(DB), read_only=True)
    excluded_countable = {c: n for c, n in con.execute("""
        SELECT b.product_code, count(DISTINCT r.mdr_report_key) FROM report r JOIN report_product_code b USING (mdr_report_key)
        WHERE r.excluded AND r.countable GROUP BY 1""").fetchall()}
    audit_keys_db = con.execute("SELECT count(DISTINCT mdr_report_key) FROM exclusion_audit").fetchone()[0]
    con.close()
    for r in receipt:
        if r["field"].startswith("ANY"):
            if int(r["reports_matched"]) != excluded_countable.get(r["product_code"], 0):
                bad.append("%s ANY: receipt %s, record table %d" % (r["product_code"], r["reports_matched"], excluded_countable.get(r["product_code"], 0)))
        elif r["field"].startswith("ALL"):
            continue
        elif int(r["reports_matched"]) != len(per_field.get((r["product_code"], r["field"]), set())):
            bad.append("%s %s: receipt %s, audit %d" % (r["product_code"], r["field"], r["reports_matched"], len(per_field.get((r["product_code"], r["field"]), set()))))
    if len({a["mdr_report_key"] for a in audit}) != audit_keys_db:
        bad.append("audit file has %d distinct keys, record table %d" % (len({a["mdr_report_key"] for a in audit}), audit_keys_db))
    results.append(("exclusion receipt agrees with the private audit, and every audit token is in the list", not bad,
                    "%d audit rows, %d receipt rows" % (len(audit), len(receipt)), bad[:20]))


def git_commits_touching(path: str) -> list[str]:
    r = subprocess.run(["git", "log", "--reverse", "--format=%H", "--", path], cwd=REPO, capture_output=True, text=True)
    return [s for s in r.stdout.splitlines() if s]


def git_show(sha: str, path: str) -> str:
    r = subprocess.run(["git", "show", "%s:%s" % (sha, path)], cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    return r.stdout if r.returncode == 0 else ""


def git_is_ancestor(a: str, b: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", a, b], cwd=REPO).returncode == 0


def check_chronology(results):
    bad = []
    if not FORECAST.exists():
        results.append(("chronology: origin precedes target, locked origins at or after 2023-12, "
                        "promotion committed before locked rows", True, "no forecast rows yet", []))
        return
    rows = read_csv(FORECAST)
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    for r in rows:
        if not r["origin"] < r["target"]:
            bad.append("%s %s origin %s does not precede target %s" % (r["product_code"], r["model"], r["origin"], r["target"]))
        if r["period"] == "locked" and r["origin"] < "2023-12":
            bad.append("locked row with origin %s" % r["origin"])
        if r["period"] == "development" and not ("2022-01" <= r["target"] <= "2023-12"):
            bad.append("development row with target %s" % r["target"])
    locked = [r for r in rows if r["period"] == "locked"]
    if locked:
        if not cfg.get("promoted"):
            bad.append("locked rows exist but config/model.json carries no promotion decision")
        promo_commits = [s for s in git_commits_touching("config/model.json") if '"promoted": {' in git_show(s, "config/model.json")]
        if not promo_commits:
            bad.append("no commit of config/model.json carries the promotion decision")
        else:
            first_locked = None
            for s in git_commits_touching("data/conformed/forecast.csv"):
                if ",locked," in git_show(s, "data/conformed/forecast.csv"):
                    first_locked = s
                    break
            if first_locked and not git_is_ancestor(promo_commits[0], first_locked):
                bad.append("the first commit with locked rows (%s) does not descend from the promotion commit (%s)" % (first_locked[:7], promo_commits[0][:7]))
            if first_locked == promo_commits[0]:
                bad.append("promotion and locked rows landed in the same commit")
    results.append(("chronology: origin precedes target, locked origins at or after 2023-12, "
                    "promotion committed before locked rows", not bad,
                    "%d rows, %d locked" % (len(rows), len(locked)), bad[:20]))


def check_locked_once(results):
    hashes = set()
    for s in git_commits_touching("data/conformed/forecast.csv"):
        txt = git_show(s, "data/conformed/forecast.csv")
        locked = "\n".join(l for l in txt.splitlines() if ",locked," in l)
        if locked:
            hashes.add(hashlib.sha256(locked.encode("utf-8")).hexdigest())
    if FORECAST.exists():
        txt = FORECAST.read_text(encoding="utf-8")
        locked = "\n".join(l for l in txt.splitlines() if ",locked," in l)
        if locked:
            hashes.add(hashlib.sha256(locked.encode("utf-8")).hexdigest())
    ok = len(hashes) <= 1
    results.append(("the locked test ran once: the locked rows have one content hash across history and the working tree",
                    ok, "%d distinct locked-row hashes" % len(hashes),
                    [] if ok else ["locked rows differ between commits or the working tree"]))


def scan_files(extra_dirs: list[pathlib.Path]) -> list[tuple[str, pathlib.Path]]:
    out = []
    for rel in tracked_files():
        p = REPO / rel
        if p.suffix.lower() in TEXT_EXT and p.exists():
            out.append((rel, p))
    for d in extra_dirs:
        if d.exists():
            for p in d.rglob("*"):
                if p.is_file() and p.suffix.lower() in TEXT_EXT:
                    rel = p.relative_to(REPO).as_posix() if REPO in p.parents else p.as_posix()
                    if (rel, p) not in out:
                        out.append((rel, p))
    return out


def check_names(results):
    sections = private_sections()
    if not sections:
        results.append(("names gate: no private token in docs/ or any tracked file", False,
                        "private list absent: fails closed", ["private list absent"]))
        return
    pats = sections["firm_tokens"] + sections.get("names_gate_extra", [])
    rx = re.compile(r"\b(?:%s)" % "|".join(pats), re.I)
    hits = []
    files = scan_files([DOCS])
    for rel, p in files:
        if rel.endswith("exclusion-list.local.txt"):
            continue
        # The verbatim estate files are canonical copies this repo may not
        # edit, and one of them uses an everyday word from the extra list in
        # its docstring in a sense that refers to nothing. Everything authored
        # here, and everything rendered, is scanned.
        if rel in VERBATIM:
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if rx.search(txt):
            hits.append("%s: carries a private token" % rel)
    results.append(("names gate: no private token in docs/ or any tracked file (verbatim kit files exempt)", not hits,
                    "%d files scanned" % len(files), hits[:20]))


def check_emdash(results):
    hits = []
    files = scan_files([DOCS])
    for rel, p in files:
        if rel in VERBATIM:
            continue
        txt = p.read_text(encoding="utf-8", errors="replace")
        # The code point, as an escape: a literal em dash in this file was once
        # rewritten by a blanket scrub into a hyphen, and the gate then counted
        # hyphens. An escape cannot be scrubbed.
        n = txt.count(chr(0x2014))
        if n:
            hits.append("%s: %d em dash(es)" % (rel, n))
    results.append(("em-dash gate: no em dash in docs/ or any authored file", not hits,
                    "%d files scanned, verbatim kit files exempt" % len(files), hits[:20]))


def check_asof(results):
    freeze = tomllib.loads((GOV / "freeze.toml").read_text(encoding="utf-8"))["freeze"]
    newest = ""
    for p in (RAW / "counts").glob("*_date_received.json"):
        data = json.loads(p.read_text(encoding="utf-8"))
        newest = max([newest] + [b["time"] for b in data["results"]])
    want = freeze["as_of_date"].replace("-", "")
    ok = newest == want == AS_OF
    results.append(("as-of agrees: freeze.toml, the count series' newest receipt day, and this gate", ok,
                    "freeze %s, newest receipt %s, gate %s" % (freeze["as_of_date"], newest, AS_OF),
                    [] if ok else ["as-of disagreement"]))


def check_cohort(results):
    gate = read_csv(CONF / "cohort_gate.csv")
    passed = {g["product_code"] for g in gate if g["forecast"] == "true"}
    bad = [g["product_code"] for g in gate if g["forecast"] == "true" and not (g["stage_a_pass"] == "true" and g["stage_b_pass"] == "true")]
    if FORECAST.exists():
        extra = {r["product_code"] for r in read_csv(FORECAST)} - passed
        bad += ["forecast rows for %s, which did not pass the gate" % c for c in sorted(extra)]
    results.append(("cohort gate: forecast rows exist only for codes that passed both stages", not bad,
                    "%d of %d codes forecast" % (len(passed), len(gate)), bad))


def check_review(results):
    if not QUEUE.exists() or not SCORED.exists():
        results.append(("review queue: every episode satisfies the rule on the scored rows", True, "no queue yet", []))
        return
    queue = [q for q in read_csv(QUEUE) if q["product_code"]]
    scored = read_csv(SCORED)
    bad = []
    for q in queue:
        rows = [r for r in scored if r["product_code"] == q["product_code"] and r["model"] == q["model_in_use"]
                and r["horizon"] == "1" and q["episode_start"] <= r["target"] <= q["episode_end"]]
        if len(rows) != int(q["months_in_episode"]):
            bad.append("%s %s: %d scored months in the episode span, %s claimed" % (q["product_code"], q["episode_start"], len(rows), q["months_in_episode"]))
        for r in rows:
            if not (float(r["actual"]) > float(r["upper80"]) and float(r["actual"]) - float(r["point"]) >= 5):
                bad.append("%s %s: month %s does not satisfy the rule" % (q["product_code"], q["episode_start"], r["target"]))
    results.append(("review queue: every episode satisfies the rule on the scored rows", not bad,
                    "%d episodes checked" % len(queue), bad[:20]))


def check_known_events(results):
    """Pre-registration section 4: the derived recall event set must recover the
    fourteen verified Class I events by event number, code and initiation date."""
    known = read_csv(REPO / "data" / "reference" / "known_events.csv")
    ctx = RECALL_CTX
    if not ctx.exists():
        results.append(("known-answer recovery: every verified Class I event is in the derived recall set with its date",
                        True, "no recall context yet", []))
        return
    rows = {r["res_event_number"]: r for r in read_csv(ctx)}
    bad = []
    for k in known:
        r = rows.get(k["res_event_number"])
        if r is None:
            bad.append("event %s (%s, %s) missing" % (k["res_event_number"], k["product_code"], k["event_date_initiated"]))
            continue
        if k["product_code"] not in r["product_codes"].split("|"):
            bad.append("event %s lacks code %s (has %s)" % (k["res_event_number"], k["product_code"], r["product_codes"]))
        if r["event_date_initiated"] != k["event_date_initiated"]:
            bad.append("event %s initiated %s, derived %s" % (k["res_event_number"], k["event_date_initiated"], r["event_date_initiated"]))
        if "Class I" not in r["classification"].split("|"):
            bad.append("event %s is not Class I in the derived set (%s)" % (k["res_event_number"], r["classification"] or "no class"))
    results.append(("known-answer recovery: every verified Class I event is in the derived recall set with its date",
                    not bad, "%d known rows checked against %d derived events" % (len(known), len(rows)), bad))


CHECKS = [check_hashes, check_extraction_log, check_m01, check_dates, check_uniqueness, check_exclusion,
          check_chronology, check_locked_once, check_names, check_emdash, check_asof, check_cohort, check_review,
          check_known_events]


# ---------------------------------------------------------------------------
# proving the checks can fail
# ---------------------------------------------------------------------------
#
# Every check above passes. That on its own is worth very little: a check that
# cannot fail passes for the same reason a deleted check passes, and the report
# reads identically either way. So each check is fed deliberately wrong data
# and must reject it. THE FROZEN DATA IS NEVER TOUCHED: the corruption is
# applied to a temporary copy, the module's path constant is repointed at the
# copy for one check, and the constant is restored and asserted afterwards.

@contextmanager
def _repoint(target: str, path: pathlib.Path):
    g = globals()
    original = g[target]
    g[target] = path
    try:
        yield
    finally:
        g[target] = original
        assert g[target] == original, "path constant not restored"


@contextmanager
def _csv_copy(target: str, mutate):
    original = globals()[target]
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="cascadia-prove-failable-"))
    try:
        rows = read_csv(original)
        mutate(rows)
        copy = tmp / original.name
        with open(copy, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        with _repoint(target, copy):
            yield
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@contextmanager
def _db_copy(sql: list[str]):
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="cascadia-prove-failable-"))
    try:
        copy = tmp / DB.name
        shutil.copyfile(DB, copy)
        con = duckdb.connect(str(copy))
        for s in sql:
            con.execute(s)
        con.close()
        with _repoint("DB", copy):
            yield
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@contextmanager
def _json_copy(target: str, mutate):
    original = globals()[target]
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="cascadia-prove-failable-"))
    try:
        data = json.loads(original.read_text(encoding="utf-8"))
        mutate(data)
        copy = tmp / original.name
        copy.write_text(json.dumps(data), encoding="utf-8")
        with _repoint(target, copy):
            yield
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@contextmanager
def _docs_copy(filename: str, text: str):
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="cascadia-prove-failable-"))
    try:
        d = tmp / "docs"
        d.mkdir()
        (d / filename).write_text(text, encoding="utf-8")
        with _repoint("DOCS", d):
            yield
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _first_eligible_token() -> str:
    s = private_sections()
    t = s["firm_tokens"][0]
    return re.sub(r"\\s[+*]", " ", t).replace("\\b", "").split("(")[0]


def _scenarios():
    yield (check_extraction_log, "a window marked failed: a missing partition must read as missing, never zero",
           lambda: _json_copy("EXTRACTION_LOG", lambda d: d["windows"].__setitem__(next(iter(d["windows"])), dict(next(iter(d["windows"].values())), status="failed: 500"))))
    yield (check_m01, "one eligible count perturbed by one",
           lambda: _csv_copy("M01", lambda rows: rows[20].__setitem__("eligible_reports", str(int(rows[20]["eligible_reports"]) + 1))))
    yield (check_m01, "a report dropped from one of the two codes it belongs to: the bridge loses a row",
           lambda: _db_copy(["DELETE FROM report_product_code WHERE (mdr_report_key, product_code) IN "
                             "(SELECT mdr_report_key, product_code FROM report_product_code b JOIN report r USING (mdr_report_key) "
                             "WHERE r.countable AND NOT r.excluded QUALIFY row_number() OVER (PARTITION BY mdr_report_key ORDER BY product_code) = 2 LIMIT 1)"]))
    yield (check_uniqueness, "a duplicate nested device: the same (report, code) pair appears twice in the bridge",
           lambda: _db_copy(["INSERT INTO report_product_code SELECT * FROM report_product_code LIMIT 1"]))
    yield (check_uniqueness, "a duplicate report key in the record table",
           lambda: _db_copy(["CREATE TABLE r2 AS SELECT * FROM report", "INSERT INTO r2 SELECT * FROM report LIMIT 1",
                             "DROP TABLE report", "ALTER TABLE r2 RENAME TO report"]))
    yield (check_dates, "a countable report with its receipt date blanked",
           lambda: _db_copy(["UPDATE report SET date_received = '' WHERE mdr_report_key = (SELECT mdr_report_key FROM report WHERE countable LIMIT 1)"]))
    yield (check_dates, "a countable report received after the as-of date: a future observation",
           lambda: _db_copy(["UPDATE report SET date_received = '20260915' WHERE mdr_report_key = (SELECT mdr_report_key FROM report WHERE countable LIMIT 1)"]))
    yield (check_exclusion, "an audit row's token replaced by a string that is not in the private list: an alias the list does not own",
           lambda: _csv_copy("AUDIT", lambda rows: rows[0].__setitem__("token", "zzz-not-a-list-token")))
    yield (check_exclusion, "an audit row re-pointed at a different report key: the receipt's ANY count no longer agrees with the record table",
           lambda: _csv_copy("AUDIT", lambda rows: rows.append(dict(rows[0], mdr_report_key="0000000"))))
    yield (check_chronology, "a forecast row whose target equals its origin",
           lambda: _csv_copy("FORECAST", lambda rows: rows[0].__setitem__("target", rows[0]["origin"])))
    yield (check_names, "a private token written into a page under docs/",
           lambda: _docs_copy("probe.html", "<p>%s</p>" % _first_eligible_token()))
    yield (check_emdash, "an em dash written into a page under docs/",
           lambda: _docs_copy("probe.html", "<p>a " + chr(0x2014) + " b</p>"))
    yield (check_known_events, "a verified Class I event removed from the derived recall set",
           lambda: _csv_copy("RECALL_CTX", lambda rows: [rows.remove(r) for r in list(rows) if r["res_event_number"] == "91955"]))
    yield (check_review, "an episode claimed for a month that does not satisfy the rule",
           lambda: _csv_copy("QUEUE", lambda rows: rows.append(dict(rows[0], episode_start="2024-01", episode_end="2024-02", months_in_episode="2"))
                             if rows and rows[0]["product_code"] else rows.append({"product_code": "DSQ", "model_in_use": "baseline_a", "episode_start": "2024-01", "episode_end": "2024-02", "months_in_episode": "2", "max_excess_over_point": "0", "status": "x"})))


def prove_failable():
    proofs = []
    for check, scenario, ctx in _scenarios():
        probe = []
        label = scenario
        try:
            if check in (check_m01, check_dates, check_uniqueness, check_exclusion) and not DB.exists():
                proofs.append((check.__name__, scenario, None, "skipped: no record table yet"))
                continue
            if check in (check_chronology,) and not FORECAST.exists():
                proofs.append((check.__name__, scenario, None, "skipped: no forecast rows yet"))
                continue
            if check in (check_review,) and not (QUEUE.exists() and SCORED.exists()):
                proofs.append((check.__name__, scenario, None, "skipped: no queue yet"))
                continue
            if check in (check_known_events,) and not RECALL_CTX.exists():
                proofs.append((check.__name__, scenario, None, "skipped: no recall context yet"))
                continue
            with ctx():
                check(probe)
            name, passed = probe[0][0], probe[0][1]
            tripped = not passed
        except Exception as exc:  # noqa: BLE001
            name, tripped = check.__name__, True
            label += "  [raised %s]" % type(exc).__name__
        proofs.append((name, label, tripped, ""))
    return proofs


# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    results = []
    for check in CHECKS:
        try:
            check(results)
        except Exception as exc:  # noqa: BLE001
            results.append((check.__name__, False, "raised %s: %s" % (type(exc).__name__, exc), [str(exc)]))
    proofs = prove_failable() if "--prove-failable" in argv else []
    all_pass = all(ok for _, ok, _, _ in results)
    all_tripped = all(t for _, _, t, _ in proofs if t is not None)
    ok = all_pass and (all_tripped if proofs else True)

    md = ["# Validation report: Cascadia Early Warning", "",
          "*Auto-generated by `src/validate.py` on %s. Receipts frozen through 2026-08-31, "
          "retrieved 2026-10-06 (openFDA, staged and hashed; see `governance/source-register.md`).*" % date.today().isoformat(),
          "", "**Overall: %s**" % ("ALL CHECKS PASS" if ok else "FAILURES DETECTED"), "",
          "## Automated checks", "", "| # | Check | Result | Coverage |", "|---|---|---|---|"]
    for i, (name, okk, detail, _) in enumerate(results, 1):
        md.append("| %d | %s | %s | %s |" % (i, name, "PASS" if okk else "FAIL", detail))
    for name, okk, _, failures in results:
        if failures:
            md += ["", "### Failures: %s" % name, ""] + ["- %s" % f for f in failures]
    if proofs:
        n_t = sum(1 for _, _, t, _ in proofs if t)
        n_r = sum(1 for _, _, t, _ in proofs if t is not None)
        md += ["", "## Proof the checks can fail", "",
               "*Each check above is re-run against a deliberately corrupted copy of its input and must reject it. "
               "A check that passes corrupted input is not testing anything, and reads identically in this report to "
               "one that works. The frozen data is never modified: the corruption is applied to a temporary copy and "
               "the path is restored after every scenario.*", "",
               "**%d of %d scenarios tripped.**" % (n_t, n_r), "",
               "| Check | Corruption fed to it | Tripped? |", "|---|---|---|"]
        for name, scenario, t, note in proofs:
            md.append("| %s | %s | %s |" % (name, scenario, "tripped" if t else ("**NO**" if t is not None else note)))
    md += ["", "---", "*Report counts are not incident rates or measures of device safety. This independent public-data "
           "demonstration provides no medical, legal or regulatory advice.*", ""]
    REPORT.write_text("\n".join(md), encoding="utf-8", newline="\n")

    print("validate.py: domain gate")
    for name, okk, detail, _ in results:
        print("  %s  %s" % ("PASS" if okk else "FAIL", name))
        print("        %s" % detail)
    for name, okk, _, failures in results:
        for f in failures[:8]:
            print("        - %s" % f)
    if proofs:
        print("\nProving each check CAN fail:")
        for name, scenario, t, note in proofs:
            print("  [%s] %s" % ("TRIPPED" if t else ("DID NOT TRIP" if t is not None else "SKIPPED"), name))
            print("          %s%s" % (scenario, (" " + note) if note else ""))
    print("\nwrote %s" % REPORT.relative_to(REPO).as_posix())
    print("\nPUBLISH GATE: " + ("PASSED" if ok else "FAILED: publish nothing, commit nothing under data/conformed/ or docs/."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
