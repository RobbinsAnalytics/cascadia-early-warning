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
import html.parser
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from contextlib import ExitStack, contextmanager
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
PRODUCT_CODE = CONF / "product_code.csv"
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
    results.append(("one locked result: the locked rows have one content hash across committed history and the working tree",
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


# ---------------------------------------------------------------------------
# page checks: what the rendered pages say, read back from the HTML
# ---------------------------------------------------------------------------

_BLOCKS = {"p", "li", "dd", "dt", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "caption", "summary", "blockquote",
           "figcaption", "div", "section", "header", "footer", "main", "aside", "nav", "ul", "ol", "dl", "table", "tr",
           "details", "body", "title", "br"}
_VOID = {"meta", "link", "br", "img", "input", "hr", "source", "area", "base", "col", "embed", "param", "track", "wbr"}


class _PageText(html.parser.HTMLParser):
    """The text a reader meets, as block segments, with three things held apart: the text of
    elements marked data-cohort-fact (generated statements, checked on their own), the chart
    data block (whose strings are drawn into the canvases), and the recall table (whose
    'Class' column is a recall classification, not a device class)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.segments, self.facts, self.meta, self.data_json = [], [], [], [], None
        self._buf, self._fact = [], None

    def _flush(self):
        s = "".join(self._buf).strip()
        if s:
            self.segments.append(s)
        self._buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and a.get("content") and (a.get("name") or a.get("property") or "").endswith(("description", "title")):
            self.meta.append(a["content"])
        if tag in _BLOCKS and self._fact is None:
            self._flush()
        if tag in _VOID:
            return
        self.stack.append((tag, a))
        if "data-cohort-fact" in a and self._fact is None:
            self._fact = {"kind": a["data-cohort-fact"], "attrs": a, "text": [], "depth": len(self.stack)}
            self._buf.append(" \x00 ")

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        while self.stack:
            t, _ = self.stack.pop()
            if self._fact is not None and len(self.stack) < self._fact["depth"]:
                self._fact["text"] = "".join(self._fact["text"]).strip()
                self.facts.append(self._fact)
                self._fact = None
            if t == tag:
                break
        if tag in _BLOCKS and self._fact is None:
            self._flush()

    def handle_data(self, data):
        tags = [t for t, _ in self.stack]
        if "style" in tags:
            return
        if "script" in tags:
            if any(t == "script" and a.get("id") == "cascadia-data" for t, a in self.stack):
                self.data_json = (self.data_json or "") + data
            return
        if any(t == "table" and a.get("id") == "tbl-recall" for t, a in self.stack):
            return
        (self._fact["text"] if self._fact is not None else self._buf).append(data)

    def close(self):
        super().close()
        self._flush()


def page_text(path: pathlib.Path) -> _PageText:
    p = _PageText()
    p.feed(path.read_text(encoding="utf-8"))
    p.close()
    return p


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


_ROMAN = {"1": "I", "2": "II", "3": "III"}
# Case-insensitive, and "Class-II" as well as "Class II": a class claim in any spelling is a claim.
_CLASS_RX = re.compile(r"(?i)\bclass(?:es)?[\s-]+(?:II|III|2|3)\b(?:\s*(?:,|and|&)\s*(?:II|III|2|3)\b)*")
_ELIG_RX = re.compile(r"(?i)\b(?:in)?eligible\b|\bqualif")
_SENTENCE_RX = re.compile(r"(?<=[.;!?])\s+")


def _asserted_eligibility(text: str, codes: list[str]):
    """What a marked eligibility statement SAYS, read from its words: (eligible, ineligible) as sets of
    codes, or None when the sentence is not in a form this check can read (which fails the check). The
    first sentence must place codes on FDA's list ("X is on FDA's list ...") and may add "and Y are
    not"; "every code" / "all N codes" and "no code" / "none of the N codes" are the whole cohort."""
    first = re.split(r"(?<=\.)\s+", text.strip())[0]
    named = lambda s: {c for c in codes if re.search(r"\b%s\b" % c, s)}  # noqa: E731
    head, _, tail = first.partition(", and ")
    if not re.search(r"(?i)\bon FDA's list\b", head):
        return None
    if re.search(r"(?i)^\s*(?:no code|none of)\b", head):
        return set(), set(codes)
    if re.search(r"(?i)\bnot on\b", head):
        return None
    yes = set(codes) if re.search(r"(?i)^\s*(?:every code|all \w+ codes)\b", head) else named(head)
    if tail:
        if not re.search(r"(?i)\bnot\.?\s*$", tail):
            return None
        return yes, named(tail)
    return yes, set(codes) - yes


def check_cohort_facts(results):
    """Every device-class and summary-reporting-eligibility statement on the pages, in their
    meta descriptions and in the chart text drawn into their canvases, agrees with
    product_code.csv. An eligibility statement must sit in an element marked
    data-cohort-fact="summary" whose code lists match the file; a class phrase anywhere must
    be the cohort's own (no per-code class statement is made, and one would have to be added
    here first). Recall classifications are not device classes: the recall table is skipped,
    and "Class I" is not matched. Every built page must carry both generated statements."""
    rows = read_csv(PRODUCT_CODE)
    codes = sorted(r["product_code"] for r in rows if r["forecast"] == "true")
    cls = sorted({r["device_class"] for r in rows if r["forecast"] == "true"})
    roman = [_ROMAN[c] for c in cls]
    want = ("Class " if len(roman) == 1 else "Classes ") + (roman[0] if len(roman) == 1 else ", ".join(roman[:-1]) + " and " + roman[-1])
    elig = {r["product_code"] for r in rows if r["forecast"] == "true" and r["summary_malfunction_reporting"] == "Eligible"}
    inelig = set(codes) - elig
    bad, n_pages, n_facts = [], 0, 0

    def scan(where, text, markable):
        for m in _CLASS_RX.finditer(text):
            if m.group(0) != want:
                bad.append("%s: device class stated as %r; product_code.csv gives %r" % (where, m.group(0), want))
        for s in _SENTENCE_RX.split(text):
            if re.search(r"(?i)\bsummary\b", s) and _ELIG_RX.search(s):
                bad.append("%s: a summary-reporting eligibility statement %s: %r"
                           % (where, "outside a marked data-cohort-fact element" if markable else "in chart text, where it cannot be checked", s[:90]))

    for path in sorted(DOCS.glob("*.html")):
        n_pages += 1
        rel = "docs/" + path.name
        pt = page_text(path)
        for seg in pt.segments:
            scan(rel, seg, True)
        for m in pt.meta:
            scan(rel + " (meta)", m, False)
        if pt.data_json and not pt.data_json.strip().startswith("@@"):
            try:
                for s in _strings(json.loads(pt.data_json)):
                    scan(rel + " (chart text)", s, False)
            except ValueError:
                bad.append("%s: the chart data block does not parse" % rel)
        kinds = {f["kind"] for f in pt.facts}
        for f in pt.facts:
            n_facts += 1
            if f["kind"] == "classes":
                if f["text"] != want:
                    bad.append("%s: marked class statement %r; product_code.csv gives %r" % (rel, f["text"], want))
            elif f["kind"] == "summary":
                e = set(f["attrs"].get("data-eligible", "").split())
                i = set(f["attrs"].get("data-ineligible", "").split())
                if e != elig or i != inelig:
                    bad.append("%s: marked eligibility statement lists eligible %s, ineligible %s; product_code.csv gives %s, %s"
                               % (rel, sorted(e), sorted(i), sorted(elig), sorted(inelig)))
                # The words, not only the attributes: what the sentence says must be what the file says.
                said = _asserted_eligibility(f["text"], codes)
                if said is None:
                    bad.append("%s: marked eligibility statement in a form this check cannot read: %r" % (rel, f["text"][:120]))
                elif said != (elig, inelig):
                    bad.append("%s: marked eligibility statement says eligible %s, ineligible %s; product_code.csv gives %s, %s"
                               % (rel, sorted(said[0]), sorted(said[1]), sorted(elig), sorted(inelig)))
                for m in _CLASS_RX.finditer(f["text"]):
                    if m.group(0) != want:
                        bad.append("%s: device class stated as %r inside a marked statement; product_code.csv gives %r" % (rel, m.group(0), want))
            else:
                bad.append("%s: unknown data-cohort-fact kind %r" % (rel, f["kind"]))
        if "template" not in path.name and not {"classes", "summary"} <= kinds:
            bad.append("%s: a built page without the generated %s statement" % (rel, " and ".join(sorted({"classes", "summary"} - kinds))))
    results.append(("cohort facts: every device-class and summary-eligibility statement on the pages agrees with product_code.csv",
                    not bad and n_pages > 0, "%d pages, %d marked statements; cohort %s, summary-eligible %s"
                    % (n_pages, n_facts, want, ", ".join(sorted(elig)) or "none"), bad[:20] or ([] if n_pages else ["no pages under docs/"])))


WORDS_BEFORE_CHART = 40
WORDS_GATED = ("s1", "s2", "s3")      # must each hold a chart, and lead with it
WORDS_GATED_IF_CHART = ("s4",)        # gated only if it holds a chart
WORDS_EXEMPT = ("s5",)                # method and receipts


class _SectionWords(html.parser.HTMLParser):
    """Visible words between each section's H2 and the start of its first chart card. A word is
    a whitespace-separated token holding a letter or digit, joined across inline elements and
    split at blocks. Not counted: script, style, svg, anything under the hidden attribute,
    aria-hidden or sr-only, and a closed <details> outside its <summary> (the reader sees only
    the summary line). The count stops at the chart card, not at the canvas inside it: the card
    is what the reader meets."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.sections = [], {}
        self._cur, self._counting, self._buf = None, False, []

    def _hidden(self):
        for t, a in self.stack:
            cls = a.get("class") or ""
            if t in ("script", "style", "svg", "template", "noscript") or "hidden" in a \
                    or "sr-only" in cls.split():
                return True
        for i, (t, a) in enumerate(self.stack):
            if t == "details" and "open" not in a and not any(tt == "summary" for tt, _ in self.stack[i + 1:]):
                return True
        return False

    def _flush(self):
        if self._cur and self._counting:
            words = [w for w in "".join(self._buf).split() if re.search(r"[A-Za-z0-9]", w)]
            self.sections[self._cur]["words"] += len(words)
        self._buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in _BLOCKS:
            self._flush()
        if self._cur and self._counting and "chart-card" in (a.get("class") or "").split():
            self._flush()
            self._counting = False
            self.sections[self._cur]["chart"] = True
        if tag in _VOID:
            return
        self.stack.append((tag, a))
        sid = a.get("id") or ""
        if tag == "div" and re.fullmatch(r"s\d+", sid) and self._cur is None:
            self._cur = sid
            self.sections[sid] = {"h2": False, "chart": False, "words": 0, "depth": len(self.stack)}

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        if tag in _BLOCKS:
            self._flush()
        while self.stack:
            t, _ = self.stack.pop()
            if t == tag:
                break
        if self._cur:
            s = self.sections[self._cur]
            if tag == "h2" and not s["h2"]:
                s["h2"], self._counting = True, not s["chart"]
            if len(self.stack) < s["depth"]:
                self._flush()
                self._cur, self._counting = None, False

    def handle_data(self, data):
        if self._cur and self._counting and not self._hidden():
            self._buf.append(data)


def check_words_before_chart(results):
    """Visuals first: on the module page, at most WORDS_BEFORE_CHART visible words between each
    section's H2 and its first chart card. Sections 01 to 03 must each hold a chart; 04 is gated
    if it holds one; 05, the method and receipts, is exempt."""
    page = DOCS / "index.html"
    if not page.exists():
        results.append(("words before the first chart: at most %d visible words between each section's H2 and its chart" % WORDS_BEFORE_CHART,
                        False, "docs/index.html absent", ["docs/index.html absent"]))
        return
    p = _SectionWords()
    p.feed(page.read_text(encoding="utf-8"))
    p.close()
    bad, seen = [], []
    for sid in WORDS_GATED + WORDS_GATED_IF_CHART:
        s = p.sections.get(sid)
        if s is None:
            if sid in WORDS_GATED:
                bad.append("%s: section missing" % sid)
            continue
        if not s["h2"]:
            bad.append("%s: no H2" % sid)
            continue
        if not s["chart"]:
            if sid in WORDS_GATED:
                bad.append("%s: no chart card after its H2" % sid)
            continue
        seen.append("%s %d" % (sid, s["words"]))
        if s["words"] > WORDS_BEFORE_CHART:
            bad.append("%s: %d visible words between the H2 and the first chart card (limit %d)" % (sid, s["words"], WORDS_BEFORE_CHART))
    results.append(("words before the first chart: at most %d visible words between each section's H2 and its first chart card "
                    "on the module page (01 to 03 must hold one, 04 if it does, 05 exempt)" % WORDS_BEFORE_CHART, not bad,
                    "; ".join(seen) or "no gated section measured", bad))


CASE_OPENING_MAX = 120
CANONICAL_ORIGIN = "https://www.robbinsanalytics.com/"


class _CaseOrder(html.parser.HTMLParser):
    """The order in which the case study's parts open, and its furniture: the opening's words, the
    position of the results table, of the first H2 and of the first section, the H1 count, and the
    canonical and social tags."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.n, self.pos, self.h1, self.meta, self.canonical = 0, {}, 0, {}, None
        self._in_opening, self.opening = 0, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.n += 1
        if tag == "h1":
            self.h1 += 1
        if tag == "meta" and (a.get("property") or a.get("name")):
            self.meta[a.get("property") or a.get("name")] = a.get("content", "")
        if tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href")
        if a.get("data-case") == "opening":
            self.pos.setdefault("opening", self.n)
            self._in_opening = 1
        elif self._in_opening and tag not in _VOID:
            self._in_opening += 1
        if tag == "table" and a.get("id") == "case-results":
            self.pos.setdefault("results", self.n)
        if tag == "h2":
            self.pos.setdefault("h2", self.n)
        if re.fullmatch(r"cs\d+", a.get("id") or ""):
            self.pos.setdefault("section", self.n)

    def handle_endtag(self, tag):
        if self._in_opening:
            self._in_opening -= 1

    def handle_data(self, data):
        if self._in_opening:
            self.opening.append(data)


def check_case_study(results):
    """The case study's shape (Build Brief 2.1 steps 16 to 18): the opening is at most
    CASE_OPENING_MAX words and comes first, the results table comes before any other section, and the
    page has exactly one H1, a canonical URL on the canonical domain, and Open Graph and Twitter tags
    whose URL and image agree with it."""
    page = DOCS / "case-study.html"
    label = ("case study: the opening at most %d words, then the results table before any section; one H1; "
             "canonical, Open Graph and Twitter tags" % CASE_OPENING_MAX)
    if not page.exists():
        results.append((label, False, "docs/case-study.html absent", ["docs/case-study.html absent"]))
        return
    p = _CaseOrder()
    p.feed(page.read_text(encoding="utf-8"))
    p.close()
    bad = []
    words = [w for w in "".join(p.opening).split() if re.search(r"[A-Za-z0-9]", w)]
    pos = p.pos
    for k in ("opening", "results", "h2", "section"):
        if k not in pos:
            bad.append("no %s found" % {"opening": "element marked data-case=\"opening\"", "results": "table#case-results",
                                         "h2": "H2", "section": "section with an id cs1, cs2 ..."}[k])
    if len(words) > CASE_OPENING_MAX:
        bad.append("the opening is %d words (limit %d)" % (len(words), CASE_OPENING_MAX))
    if not bad:
        if not pos["opening"] < pos["results"]:
            bad.append("the results table comes before the opening")
        if not pos["results"] < min(pos["h2"], pos["section"]):
            bad.append("a section or H2 comes before the results table")
    if p.h1 != 1:
        bad.append("%d H1 elements; the page must have exactly one" % p.h1)
    c = p.canonical or ""
    if not (c.startswith(CANONICAL_ORIGIN) and c.endswith("/case-study.html")):
        bad.append("canonical URL %r is not the case study on the canonical domain" % c)
    for k in ("og:title", "og:description", "og:image", "og:url", "twitter:card", "twitter:image", "description"):
        if not p.meta.get(k):
            bad.append("missing %s" % k)
    if p.meta.get("og:url") != c:
        bad.append("og:url %r differs from the canonical URL" % p.meta.get("og:url"))
    for k in ("og:image", "twitter:image"):
        if p.meta.get(k) and not p.meta[k].startswith(CANONICAL_ORIGIN):
            bad.append("%s is not an absolute URL on the canonical domain" % k)
    results.append((label, not bad, "opening %d words; order opening %s, results %s, first H2 %s, first section %s; H1 %d"
                    % (len(words), pos.get("opening"), pos.get("results"), pos.get("h2"), pos.get("section"), p.h1), bad))


CHECKS = [check_hashes, check_extraction_log, check_m01, check_dates, check_uniqueness, check_exclusion,
          check_chronology, check_locked_once, check_names, check_emdash, check_asof, check_cohort, check_review,
          check_known_events, check_cohort_facts, check_words_before_chart, check_case_study]


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


@contextmanager
def _docs_tree_copy(mutations: dict):
    """Every page under docs/ copied, then {filename: text -> text} applied; a page check then
    reads a full set of pages with one thing wrong, so it trips on that thing and not on a page
    missing from a one-file copy."""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="cascadia-prove-failable-"))
    try:
        d = tmp / "docs"
        d.mkdir()
        for p in DOCS.glob("*.html"):
            shutil.copyfile(p, d / p.name)
        for name, fn in mutations.items():
            p = d / name
            before = p.read_text(encoding="utf-8") if p.exists() else ""
            after = fn(before)
            if after == before:
                raise RuntimeError("the mutation of %s changed nothing; the scenario would prove nothing" % name)
            p.write_text(after, encoding="utf-8")
        with _repoint("DOCS", d):
            yield
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@contextmanager
def _gov_copy(filename: str, mutate_text):
    """governance/<filename> copied and mutated; GOV repointed at the copy's folder."""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="cascadia-prove-failable-"))
    try:
        before = (GOV / filename).read_text(encoding="utf-8")
        after = mutate_text(before)
        if after == before:
            raise RuntimeError("the mutation of %s changed nothing; the scenario would prove nothing" % filename)
        (tmp / filename).write_text(after, encoding="utf-8")
        with _repoint("GOV", tmp):
            yield
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _first_staged(manifest: dict) -> str:
    return next(k for k in manifest["files"] if k.startswith("data/raw/staging/event/"))


def _flip_sha(manifest: dict):
    e = manifest["files"][_first_staged(manifest)]
    e["sha256"] = ("0" if e["sha256"][0] != "0" else "1") + e["sha256"][1:]


def _bump_first_locked(rows: list[dict]):
    r = next(r for r in rows if r["period"] == "locked")
    r["point"] = "%.6f" % (float(r["point"]) + 1)


def _sub_once(pattern: str, repl: str):
    def fn(text: str) -> str:
        out, n = re.subn(pattern, repl, text, count=1)
        if not n:
            raise RuntimeError("pattern %r not found; the scenario would prove nothing" % pattern)
        return out
    return fn


def _move_results_below_first_section(text: str) -> str:
    m = re.search(r'(?s)<div class="table-wrap"><table id="case-results">.*?</table></div>', text)
    if not m:
        raise RuntimeError("no results table; the scenario would prove nothing")
    rest = text[:m.start()] + text[m.end():]
    end = rest.index("</div>", rest.index('id="cs1"'))
    return rest[:end] + m.group(0) + rest[end:]


def _first_eligible_token() -> str:
    s = private_sections()
    t = s["firm_tokens"][0]
    return re.sub(r"\\s[+*]", " ", t).replace("\\b", "").split("(")[0]


def _scenarios():
    yield (check_hashes, "one staged page's recorded SHA-256 altered by one hex digit in a copy of the manifest",
           lambda: _json_copy("MANIFEST", _flip_sha))
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
    yield (check_exclusion, "an audit row added for a report key the record table does not hold: the per-field count and the distinct-key total no longer agree",
           lambda: _csv_copy("AUDIT", lambda rows: rows.append(dict(rows[0], mdr_report_key="0000000"))))
    yield (check_chronology, "a forecast row whose target equals its origin",
           lambda: _csv_copy("FORECAST", lambda rows: rows[0].__setitem__("target", rows[0]["origin"])))
    yield (check_locked_once, "one locked row's point forecast moved by one report in the working copy: a second locked result",
           lambda: _csv_copy("FORECAST", _bump_first_locked))
    yield (check_asof, "freeze.toml's as_of_date moved back a day",
           lambda: _gov_copy("freeze.toml", lambda t: re.sub(r'as_of_date = "(\d{4}-\d{2})-(\d{2})"',
                                                            lambda m: 'as_of_date = "%s-%02d"' % (m.group(1), int(m.group(2)) - 1), t, count=1)))
    yield (check_cohort, "forecast rows for a code that never entered the cohort gate (DXY, the reference series)",
           lambda: _csv_copy("FORECAST", lambda rows: rows.append(dict(rows[0], product_code="DXY"))))
    yield (check_names, "a private token written into a page under docs/",
           lambda: _docs_copy("probe.html", "<p>%s</p>" % _first_eligible_token()))
    yield (check_emdash, "an em dash written into a page under docs/",
           lambda: _docs_copy("probe.html", "<p>a " + chr(0x2014) + " b</p>"))
    yield (check_known_events, "a verified Class I event removed from the derived recall set",
           lambda: _csv_copy("RECALL_CTX", lambda rows: [rows.remove(r) for r in list(rows) if r["res_event_number"] == "91955"]))
    yield (check_cohort_facts, "the module page's cohort typed as Class III, as the template once did",
           lambda: _docs_tree_copy({"index.html": _sub_once(r'(<span data-cohort-fact="classes">)[^<]*(</span>)', r"\1Class III\2")}))
    yield (check_cohort_facts, "the summary-eligibility statement re-pointed at a code the source lists as ineligible",
           lambda: _docs_tree_copy({"index.html": _sub_once(r'data-eligible="[^"]*"', 'data-eligible="DSQ"')}))
    yield (check_cohort_facts, "the eligibility statement's words swapped to name a code the source lists as ineligible, its attributes left right",
           lambda: _docs_tree_copy({"index.html": _sub_once(r'(data-cohort-fact="summary"[^>]*>)([A-Z]{3})( (?:is|are) on FDA)',
                                                            r"\1DSQ\3")}))
    yield (check_cohort_facts, "an unmarked sentence calling every code ineligible for summary reporting",
           lambda: _docs_tree_copy({"index.html": _sub_once(r"</main>", "<p>All of these codes are ineligible for malfunction summary reporting.</p></main>")}))
    yield (check_words_before_chart, "a forty-five-word paragraph written between section 01's H2 and its chart",
           lambda: _docs_tree_copy({"index.html": _sub_once(r'(?s)(<div id="s1"[^>]*>.*?</h2>)', r"\1<p>" + "word " * 45 + "</p>")}))
    yield (check_words_before_chart, "section 02's chart cards removed: a section that leads with no chart",
           lambda: _docs_tree_copy({"index.html": lambda t: _sub_once(r'(?s)(<div id="s2"[^>]*>.*?)class="chart-card ', r'\1class="was-card ')(
               _sub_once(r'(?s)(<div id="s2"[^>]*>.*?)class="chart-card ', r'\1class="was-card ')(t))}))
    yield (check_case_study, "the case study's opening padded to more than its word limit",
           lambda: _docs_tree_copy({"case-study.html": _sub_once(r'(data-case="opening"[^>]*>)', r"\1" + "word " * 70)}))
    yield (check_case_study, "the results table moved below the first section",
           lambda: _docs_tree_copy({"case-study.html": lambda t: _move_results_below_first_section(t)}))
    yield (check_case_study, "a second H1 written into the case study",
           lambda: _docs_tree_copy({"case-study.html": _sub_once(r"</main>", "<h1>A second title</h1></main>")}))
    yield (check_review, "an episode claimed for a month that does not satisfy the rule",
           lambda: _csv_copy("QUEUE", lambda rows: rows.append(dict(rows[0], episode_start="2024-01", episode_end="2024-02", months_in_episode="2"))
                             if rows and rows[0]["product_code"] else rows.append({"product_code": "DSQ", "model_in_use": "baseline_a", "episode_start": "2024-01", "episode_end": "2024-02", "months_in_episode": "2", "max_excess_over_point": "0", "status": "x"})))


def prove_failable():
    proofs = []
    for check, scenario, ctx in _scenarios():
        probe = []
        label = scenario
        try:
            if check is check_hashes and not (RAW / "staging" / "event").exists():
                proofs.append((check.__name__, scenario, None, "skipped: no staged pages on disk (a fresh clone; restore them first)"))
                continue
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
            with ExitStack() as stack:
                # Building the corrupted copy is not the check. A scenario whose setup raises
                # proves nothing about the check, so it is recorded as NOT tripped and fails the
                # gate, rather than counted as proof (which is how it used to be counted).
                try:
                    stack.enter_context(ctx())
                except Exception as exc:  # noqa: BLE001
                    proofs.append((check.__name__, label + "  [setup raised %s: proves nothing]" % type(exc).__name__, False, ""))
                    continue
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
