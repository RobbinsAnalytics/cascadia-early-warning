"""acquire.py -- bounded, paced, hashed extraction from openFDA. Keyless.

THIS SCRIPT RE-PULLS THE SOURCE. Running it is a deliberate refresh, never a
side effect of a build (PRINCIPLES rule 1). The default `run.ps1 build` never
calls it.

Sources, each recorded in governance/source-register.md and hashed in
data/raw/manifest.json:

    S-01  record-level /device/event, one request per product code per receipt
          window, 2016-01-01 to 2026-08-31, limit=1000, skip paging, sorted by
          date_received so paging is deterministic. Windows are planned from the
          S-02 daily series so no window exceeds the 25,000-record skip ceiling.
          Pages land in data/raw/staging/ (gitignored; the freeze is the hash).
    S-02  count=date_received and count=date_of_event per code, the whole
          series in one request each, committed under data/raw/counts/.
          The independent path for M-01 and the day-one cohort gate input.
    S-03  classification bulk (whole table).
    S-04  enforcement bulk (recall class lives only here).
    S-05  recall bulk (product code, root cause, K and P numbers).
          S-03 to S-05 are zips under data/raw/bulk/ (gitignored, hashed);
          the export dates come from download.json, snapshotted beside them.
    S-06  the FDA list of product codes eligible for malfunction summary
          reporting, if the page yields it; otherwise the classification
          table's own summary_malfunction_reporting field stands in.

A FAILED PARTITION IS MISSING DATA, NEVER ZERO. A window whose pages did not
all arrive is recorded as incomplete in data/raw/extraction_log.json and the
build refuses to treat it as a count of zero.

THE WHOLE EXTRACTION RESTARTS IF THE SOURCE MOVES MID-RUN. Every response
carries meta.last_updated; the first one seen in a run is the run's datum and
any later response that differs aborts the run with the mismatch printed.

BUDGET. Without a key openFDA allows 240 requests a minute and 1,000 a day per
IP. Requests are paced at one a second, every one is written to a ledger, and a
batch that would take the trailing 24 hours past DAILY_CAP refuses to start.

Usage (name the interpreter by path; see CLAUDE.md):
    python src/acquire.py counts            # S-02 for the cohort and DXY
    python src/acquire.py plan              # windows and request budget, no calls
    python src/acquire.py extract           # S-01, from the plan
    python src/acquire.py bulk              # S-03, S-04, S-05
    python src/acquire.py vmsr              # S-06
    python src/acquire.py register          # rewrite governance/source-register.md
    python src/acquire.py restore           # fresh clone: refetch staging, verify
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = pathlib.Path(__file__).resolve().parent.parent
RAW = REPO / "data" / "raw"
COUNTS = RAW / "counts"
STAGING = RAW / "staging"
BULK = RAW / "bulk"
VMSR = RAW / "vmsr"
MANIFEST = RAW / "manifest.json"
EXTRACTION_LOG = RAW / "extraction_log.json"
LEDGER = STAGING / "_request_ledger.jsonl"
GOV = REPO / "governance"

API = "https://api.fda.gov"
DOWNLOAD_INDEX = "https://api.fda.gov/download.json"
VMSR_PAGE = ("https://www.fda.gov/medical-devices/medical-device-reporting-mdr-"
             "how-report-medical-device-problems/voluntary-malfunction-summary-"
             "reporting-program")

# D2. Seven Cardiovascular Class III codes, plus DXY as a reference code whose
# 2020 to 2025 series was verified by two independent reads on 2026-10-06
# (4,403 reports; 546, 561, 784, 922, 773, 817 by year). DXY is never forecast.
COHORT = ["DSQ", "OZD", "PYX", "NPT", "NIK", "LWS", "DSP"]
REFERENCE = ["DXY"]
COUNT_FIELDS = ["date_received", "date_of_event"]

WINDOW_START = "20160101"
WINDOW_END = "20260831"
# 999, NOT 1000. Without a key a search request with limit=1000 is refused
# with HTTP 403 API_KEY_MISSING; 999 is answered. Measured 2026-10-06 after
# the first extraction attempt failed on every window. The documented limit
# of 1,000 is the keyed limit.
PAGE = 999
WINDOW_MAX = 25000          # records per planned window; last skip <= 24975
SKIP_MAX = 25000            # the API's documented ceiling
MIN_INTERVAL = 1.0          # seconds between requests
DAILY_CAP = 950             # of the 1,000 allowed; leaves room for a probe
RETRY_AFTER_CAP = 120

USER_AGENT = ("Cascadia Early Warning (portfolio analytics; "
              "contact ajayrobbins@hotmail.com)")

BULK_ENDPOINTS = {
    "S-03": "classification",
    "S-04": "enforcement",
    "S-05": "recall",
}


# ---------------------------------------------------------------------------
# manifest and ledger
# ---------------------------------------------------------------------------

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {"_what_this_is": (
        "One entry per response the module froze, keyed by repo-relative path. "
        "sha256 is of the raw response body as received (before gzip, for "
        "staged pages). src/validate.py recomputes every hash; "
        "src/validate_freeze.py protects this file itself. Exclusion queries "
        "carry a label and no URL, because the URL would carry the tokens."),
        "files": {}}


def save_manifest(m: dict) -> None:
    """Merge-safe: re-read what is on disk and lay this process's entries over
    it, so a bulk download and an API batch running side by side never clobber
    each other's entries. Each process only ever writes its own keys."""
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    on_disk = {}
    if MANIFEST.exists():
        try:
            on_disk = json.loads(MANIFEST.read_text(encoding="utf-8")).get("files", {})
        except ValueError:
            on_disk = {}
    on_disk.update(m["files"])
    m["files"] = dict(sorted(on_disk.items()))
    tmp = MANIFEST.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(m, indent=1, sort_keys=False) + "\n",
                   encoding="utf-8", newline="\n")
    tmp.replace(MANIFEST)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ledger_append(entry: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry) + "\n")


def ledger_last_24h() -> int:
    if not LEDGER.exists():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    n = 0
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        try:
            t = datetime.fromisoformat(e["utc"])
        except (KeyError, ValueError):
            continue
        if t >= cutoff and e.get("api"):
            n += 1
    return n


# ---------------------------------------------------------------------------
# client
# ---------------------------------------------------------------------------

class SourceMoved(Exception):
    """meta.last_updated changed mid-run. The extraction restarts."""


class Budget(Exception):
    """The daily budget would be exceeded. Nothing was requested."""


class Client:
    def __init__(self, api: bool = True):
        self.api = api
        self._last = 0.0
        self.requests_made = 0
        # meta.last_updated is PER ENDPOINT: on 2026-10-06 510k and pma said
        # 2026-09-28, event 2026-09-29, recall 2026-10-05. One datum across
        # endpoints aborted the first exclusion run for a move that was not one.
        self.datum: dict[str, str] = {}

    def _raw(self, url: str, timeout: int = 120, _retried: bool = False,
             label: str | None = None) -> tuple[bytes, dict]:
        gap = MIN_INTERVAL - (time.monotonic() - self._last)
        if gap > 0:
            time.sleep(gap)
        self._last = time.monotonic()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "application/json"})
        started = now_utc()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                headers = dict(resp.headers)
                status = resp.status
        except urllib.error.HTTPError as exc:
            ledger_append({"utc": started, "api": self.api,
                           "label": label or url, "status": exc.code})
            if exc.code == 429 and not _retried:
                wait = RETRY_AFTER_CAP
                try:
                    wait = min(RETRY_AFTER_CAP,
                               max(5, int(exc.headers.get("Retry-After", "60"))))
                except (TypeError, ValueError):
                    pass
                print("  throttled (429); waiting %ds then retrying once" % wait)
                time.sleep(wait)
                return self._raw(url, timeout, True, label)
            if exc.code == 404:
                # openFDA answers "No matches found!" with a 404 and a JSON
                # body. That is a real answer (an empty window), not a failure.
                body = exc.read()
                return body, {"status": 404, "headers": dict(exc.headers)}
            try:
                # Print the body: a 403 here is API_KEY_MISSING, which the
                # status code alone does not say. Learned on 2026-10-06 when
                # 78 windows failed before anyone read why.
                print("  HTTP %d: %s" % (exc.code, exc.read()[:200].decode("utf-8", "replace").replace("\n", " ")))
            except Exception:  # noqa: BLE001
                pass
            raise
        except (TimeoutError, urllib.error.URLError) as exc:
            ledger_append({"utc": started, "api": self.api,
                           "label": label or url, "status": "network"})
            if _retried:
                raise
            print("  network failure (%s); waiting 20s then retrying once"
                  % (getattr(exc, "reason", None) or exc))
            time.sleep(20)
            return self._raw(url, timeout, True, label)
        self.requests_made += 1
        ledger_append({"utc": started, "api": self.api,
                       "label": label or url, "status": status, "bytes": len(body)})
        return body, {"status": status, "headers": headers}

    def get_json(self, url: str, label: str | None = None) -> tuple[bytes, dict, dict]:
        """Returns (body, parsed, info). Enforces the last_updated datum."""
        body, info = self._raw(url, label=label)
        try:
            parsed = json.loads(body.decode("utf-8"))
        except ValueError:
            parsed = {}
        lu = (parsed.get("meta") or {}).get("last_updated")
        if lu:
            ep = endpoint_of(url)
            seen = self.datum.get(ep)
            if seen is None:
                self.datum[ep] = lu
            elif lu != seen:
                raise SourceMoved("meta.last_updated for %s moved from %s to %s at %s"
                                  % (ep, seen, lu, label or url))
        return body, parsed, info


def endpoint_of(url: str) -> str:
    m = re.search(r"/device/(\w+)\.json", url)
    return m.group(1) if m else url.split("?")[0]


def require_budget(n: int) -> None:
    used = ledger_last_24h()
    if used + n > DAILY_CAP:
        raise Budget("this batch needs %d requests; %d used in the trailing 24h; "
                     "cap %d. Nothing was requested." % (n, used, DAILY_CAP))
    print("budget: %d requested, %d used in trailing 24h, cap %d" % (n, used, DAILY_CAP))


def record(manifest: dict, relpath: str, body: bytes, source_id: str,
           url: str | None, parsed: dict | None, extra: dict | None = None) -> None:
    meta = (parsed or {}).get("meta") or {}
    results = meta.get("results") or {}
    entry = {
        "source": source_id,
        "url": url,
        "retrieved_utc": now_utc(),
        "bytes": len(body),
        "sha256": sha256_bytes(body),
        "meta_last_updated": meta.get("last_updated"),
        "results_total": results.get("total"),
        "results_skip": results.get("skip"),
        "results_limit": results.get("limit"),
    }
    if extra:
        entry.update(extra)
    manifest["files"][relpath] = entry
    save_manifest(manifest)


# ---------------------------------------------------------------------------
# S-02 counts
# ---------------------------------------------------------------------------

def count_url(code: str, field: str) -> str:
    return ("%s/device/event.json?search=device.device_report_product_code:%s"
            "&count=%s" % (API, code, field))


def cmd_counts() -> int:
    codes = COHORT + REFERENCE
    jobs = [(c, f) for c in codes for f in COUNT_FIELDS if not (c in REFERENCE and f != "date_received")]
    require_budget(len(jobs))
    manifest = load_manifest()
    client = Client()
    COUNTS.mkdir(parents=True, exist_ok=True)
    for code, field in jobs:
        url = count_url(code, field)
        body, parsed, info = client.get_json(url)
        if info["status"] == 404:
            print("  %s %s: no matches" % (code, field))
        rel = "data/raw/counts/%s_%s.json" % (code, field)
        (REPO / rel).write_bytes(body)
        n = sum(r["count"] for r in parsed.get("results", []))
        record(manifest, rel, body, "S-02", url, parsed,
               {"series_total": n, "buckets": len(parsed.get("results", []))})
        print("  %s %-14s %9d reports in %5d day buckets   last_updated %s"
              % (code, field, n, len(parsed.get("results", [])),
                 (parsed.get("meta") or {}).get("last_updated")))
    print("requests made: %d" % client.requests_made)
    return 0


# ---------------------------------------------------------------------------
# S-01 extraction, planned from S-02
# ---------------------------------------------------------------------------

def daily_series(code: str, field: str = "date_received") -> dict[str, int]:
    p = COUNTS / ("%s_%s.json" % (code, field))
    if not p.exists():
        sys.exit("no count series for %s %s; run `acquire.py counts` first" % (code, field))
    data = json.loads(p.read_text(encoding="utf-8"))
    return {r["time"]: r["count"] for r in data.get("results", [])}


def plan_windows(code: str) -> list[dict]:
    """Windows of consecutive receipt days whose record total stays under
    WINDOW_MAX, within the extraction range, one or more per year. Planned from
    the S-02 daily series so the API's 25,000 skip ceiling is never reached and
    every window has an expected total to reconcile against."""
    series = daily_series(code)
    days = sorted(d for d in series if WINDOW_START <= d <= WINDOW_END)
    windows = []
    by_year: dict[str, list[str]] = {}
    for d in days:
        by_year.setdefault(d[:4], []).append(d)
    for year in sorted(by_year):
        ydays = by_year[year]
        total = sum(series[d] for d in ydays)
        y_start = max(WINDOW_START, year + "0101")
        y_end = min(WINDOW_END, year + "1231")
        if total <= WINDOW_MAX:
            windows.append({"code": code, "start": y_start, "end": y_end,
                            "expected": total})
            continue
        # split the year at day boundaries, greedily
        cur_start, cur_total = y_start, 0
        for i, d in enumerate(ydays):
            if cur_total + series[d] > WINDOW_MAX and cur_total > 0:
                prev = ydays[i - 1]
                windows.append({"code": code, "start": cur_start, "end": prev,
                                "expected": cur_total})
                cur_start, cur_total = d, 0
            cur_total += series[d]
        windows.append({"code": code, "start": cur_start, "end": y_end,
                        "expected": cur_total})
    return windows


def page_url(code: str, start: str, end: str, skip: int) -> str:
    return ("%s/device/event.json?search=device.device_report_product_code:%s"
            "+AND+date_received:[%s+TO+%s]&sort=date_received:asc&limit=%d&skip=%d"
            % (API, code, start, end, PAGE, skip))


def cmd_plan(codes: list[str] | None = None) -> int:
    codes = codes or COHORT
    total_calls = 0
    for code in codes:
        ws = plan_windows(code)
        calls = sum(-(-w["expected"] // PAGE) if w["expected"] else 1 for w in ws)
        total_calls += calls
        print("%s: %d windows, %d expected records, %d requests"
              % (code, len(ws), sum(w["expected"] for w in ws), calls))
        for w in ws:
            if w["end"][:4] != w["start"][:4] or w["start"][4:] != "0101" or w["end"][4:] not in ("1231", WINDOW_END[4:]):
                print("    split window %s..%s  %d" % (w["start"], w["end"], w["expected"]))
    print("total requests for extraction: %d; used in trailing 24h: %d; cap %d"
          % (total_calls, ledger_last_24h(), DAILY_CAP))
    return 0


def load_log() -> dict:
    if EXTRACTION_LOG.exists():
        return json.loads(EXTRACTION_LOG.read_text(encoding="utf-8"))
    return {"_what_this_is": (
        "One entry per planned extraction window: the expected total from the "
        "S-02 series, the API's own results.total, the pages fetched, the "
        "distinct report keys seen, and a status. A window that is not "
        "'complete' is MISSING DATA, never zero, and the build refuses it."),
        "windows": {}}


def save_log(log: dict) -> None:
    log["windows"] = dict(sorted(log["windows"].items()))
    EXTRACTION_LOG.write_text(json.dumps(log, indent=1) + "\n",
                              encoding="utf-8", newline="\n")


def cmd_extract(codes: list[str] | None = None) -> int:
    codes = codes or COHORT
    plans = [w for c in codes for w in plan_windows(c)]
    log = load_log()
    todo = [w for w in plans
            if log["windows"].get("%s_%s_%s" % (w["code"], w["start"], w["end"]), {}).get("status") != "complete"]
    need = sum(-(-w["expected"] // PAGE) if w["expected"] else 1 for w in todo)
    print("%d windows planned, %d still to fetch, %d requests" % (len(plans), len(todo), need))
    # Fit the batch to what is left of the day rather than refusing it whole:
    # whole windows only, in plan order, so a window is never half-fetched by
    # design. What does not fit is reported and waits for the next day.
    used = ledger_last_24h()
    room = DAILY_CAP - used
    fitted, spent = [], 0
    for w in todo:
        cost = -(-w["expected"] // PAGE) if w["expected"] else 1
        if spent + cost > room:
            break
        fitted.append(w)
        spent += cost
    if len(fitted) < len(todo):
        print("budget: %d used in trailing 24h, cap %d; %d of %d windows fit (%d requests); "
              "%d wait for the next day" % (used, DAILY_CAP, len(fitted), len(todo), spent,
                                             len(todo) - len(fitted)))
    else:
        print("budget: %d requested, %d used in trailing 24h, cap %d" % (spent, used, DAILY_CAP))
    todo = fitted
    if not todo:
        raise Budget("no window fits the remaining budget (%d used, cap %d)" % (used, DAILY_CAP))
    manifest = load_manifest()
    client = Client()
    # The datum: the count series' last_updated, so the extraction is refused
    # if the source has moved since the counts were taken.
    lu_counts = {v.get("meta_last_updated") for k, v in manifest["files"].items()
                 if v.get("source") == "S-02"}
    lu_counts.discard(None)
    if len(lu_counts) == 1:
        client.datum["event"] = next(iter(lu_counts))
        print("datum meta.last_updated for event, from S-02: %s" % client.datum["event"])
    elif len(lu_counts) > 1:
        sys.exit("the S-02 count series carry more than one last_updated: %s" % sorted(lu_counts))

    consecutive_failures = 0
    for w in todo:
        if consecutive_failures >= 3:
            # CIRCUIT BREAKER. On 2026-10-06 a wrong page size made every
            # request fail with 403 and the loop spent 78 requests learning
            # that one fact. Three failures in a row is a broken request
            # shape, not three unlucky windows; stop and let a human read.
            print("ABORT: three consecutive windows failed; the request shape is "
                  "wrong and the budget is not spent finding out 78 times")
            break
        code, start, end = w["code"], w["start"], w["end"]
        key = "%s_%s_%s" % (code, start, end)
        keys: set[str] = set()
        pages, api_total, status = 0, None, "incomplete"
        skip = 0
        d = STAGING / "event" / code
        d.mkdir(parents=True, exist_ok=True)
        try:
            while True:
                url = page_url(code, start, end, skip)
                body, parsed, info = client.get_json(url)
                if info["status"] == 404:
                    api_total = 0
                    status = "complete"
                    break
                meta = parsed.get("meta", {})
                api_total = meta["results"]["total"]
                results = parsed.get("results", [])
                for r in results:
                    keys.add(r.get("mdr_report_key"))
                rel = "data/raw/staging/event/%s/%s_p%03d.json.gz" % (code, key, pages + 1)
                with gzip.open(REPO / rel, "wb", compresslevel=6) as gz:
                    gz.write(body)
                record(manifest, rel, body, "S-01", url, parsed,
                       {"records_in_page": len(results), "stored": "gzip"})
                pages += 1
                skip += PAGE
                if skip >= api_total or not results:
                    status = "complete" if len(keys) == api_total else "key_mismatch"
                    break
                if skip > SKIP_MAX:
                    status = "skip_ceiling"
                    break
        except SourceMoved as exc:
            status = "source_moved"
            print("ABORT: %s" % exc)
            log["windows"][key] = {"code": code, "start": start, "end": end,
                                   "expected": w["expected"], "api_total": api_total,
                                   "pages": pages, "distinct_keys": len(keys),
                                   "status": status, "utc": now_utc()}
            save_log(log)
            return 2
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            status = "failed: %s" % (getattr(exc, "code", None) or exc)
        log["windows"][key] = {"code": code, "start": start, "end": end,
                               "expected": w["expected"], "api_total": api_total,
                               "pages": pages, "distinct_keys": len(keys),
                               "status": status, "utc": now_utc()}
        save_log(log)
        flag = "" if status == "complete" and api_total == w["expected"] else "   ** CHECK **"
        print("  %-24s expected %6d  api %6s  keys %6d  pages %3d  %s%s"
              % (key, w["expected"], api_total, len(keys), pages, status, flag))
        consecutive_failures = consecutive_failures + 1 if status.startswith("failed") else 0
    print("requests made: %d" % client.requests_made)
    incomplete = [k for k, v in log["windows"].items() if v["status"] != "complete"]
    if incomplete:
        print("\n%d window(s) not complete: %s" % (len(incomplete), ", ".join(incomplete)))
        return 1
    return 0


# ---------------------------------------------------------------------------
# S-03 to S-05 bulk
# ---------------------------------------------------------------------------

def cmd_bulk() -> int:
    manifest = load_manifest()
    client = Client(api=False)
    BULK.mkdir(parents=True, exist_ok=True)
    body, parsed, _ = client.get_json(DOWNLOAD_INDEX)
    rel = "data/raw/openfda_download_index.json"
    (REPO / rel).write_bytes(body)
    record(manifest, rel, body, "S-00", DOWNLOAD_INDEX, parsed)
    device = parsed["results"]["device"]
    for sid, ep in BULK_ENDPOINTS.items():
        info = device[ep]
        parts = info["partitions"]
        print("%s %s export %s, %d partition(s), %s records"
              % (sid, ep, info["export_date"], len(parts), info["total_records"]))
        for p in parts:
            url = p["file"]
            name = url.rsplit("/", 1)[-1]
            target = BULK / name
            part = BULK / (name + ".part")
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            h = hashlib.sha256()
            n = 0
            with urllib.request.urlopen(req, timeout=600) as resp, part.open("wb") as fh:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    fh.write(chunk)
                    h.update(chunk)
                    n += len(chunk)
            part.replace(target)
            ledger_append({"utc": now_utc(), "api": False, "label": url, "status": 200, "bytes": n})
            manifest["files"]["data/raw/bulk/" + name] = {
                "source": sid, "url": url, "retrieved_utc": now_utc(),
                "bytes": n, "sha256": h.hexdigest(),
                "export_date": info["export_date"],
                "records_declared": p.get("records"),
                "size_mb_declared": p.get("size_mb"),
            }
            save_manifest(manifest)
            print("  %s  %d bytes  sha256 %s" % (name, n, h.hexdigest()[:16]))
    return 0


# ---------------------------------------------------------------------------
# S-06 VMSR eligible-code list
# ---------------------------------------------------------------------------

def cmd_vmsr() -> int:
    manifest = load_manifest()
    VMSR.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(VMSR_PAGE, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Cascadia Early Warning",
        "Accept": "text/html"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            html = resp.read()
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        print("VMSR page not retrievable: %s" % exc)
        return 1
    (VMSR / "vmsr_page.html").write_bytes(html)
    record(manifest, "data/raw/vmsr/vmsr_page.html", html, "S-06", VMSR_PAGE, None)
    text = html.decode("utf-8", errors="replace")
    # The page carries one attachment link, /media/<id>/download, and its
    # anchor text ("Comprehensive List of Eligible Product Codes") sits on a
    # different line from the href, so match the href and keep the text as
    # the label if it is nearby.
    links = []
    # The list itself is a zip on accessdata.fda.gov, linked from the
    # "Comprehensive List of Eligible Product Codes" button; the page's one
    # /media/ link is the MDUFA IV commitment letter, which a first pass
    # mistook for the list.
    for m in re.finditer(r'href="(https://www\.accessdata\.fda\.gov/premarket/ftparea/VMSR[^"]*)"', text):
        links.append((m.group(1), "Comprehensive List of Eligible Product Codes (zip)"))
    for m in re.finditer(r'href="(/media/\d+/download[^"]*)"', text):
        after = text[m.end():m.end() + 400]
        t = re.search(r">([^<]{4,120})<", after)
        links.append((m.group(1).replace("&amp;", "&"), t.group(1).strip() if t else "media attachment"))
    print("candidate links:")
    for href, label in links:
        print("  %s  %s" % (label, href))
    for href, label in links:
        if "media" in href or href.lower().endswith((".xlsx", ".pdf", ".csv")):
            url = href if href.startswith("http") else "https://www.fda.gov" + href
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Cascadia Early Warning"})
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    body = resp.read()
                    ctype = resp.headers.get("Content-Type", "")
                    cd = resp.headers.get("Content-Disposition", "")
            except (urllib.error.HTTPError, urllib.error.URLError) as exc:
                print("  could not fetch %s: %s" % (url, exc))
                continue
            if url.lower().endswith(".zip") or "zip" in ctype:
                ext = ".zip"
            elif "spreadsheet" in ctype or ".xlsx" in cd:
                ext = ".xlsx"
            elif "pdf" in ctype:
                ext = ".pdf"
            else:
                ext = ".bin"
            name = "vmsr_eligible_product_codes" + ext
            (VMSR / name).write_bytes(body)
            record(manifest, "data/raw/vmsr/" + name, body, "S-06", url, None,
                   {"content_type": ctype, "link_text": label.strip()})
            print("  saved %s (%d bytes, %s)" % (name, len(body), ctype))
            return 0
    print("no eligible-code list link found on the page")
    return 1


# ---------------------------------------------------------------------------
# source register
# ---------------------------------------------------------------------------

REGISTER_HEAD = """# Source register - Cascadia Early Warning

*Phase 1 artifact. Owner: Aaron Robbins. Established 2026-10-06. Generated by
`src/acquire.py register` from `data/raw/manifest.json`; the narrative below
the tables is maintained by hand in `src/acquire.py` and the per-response
table is rewritten from the manifest.*

This file is the authoritative record of **what was pulled, from where, when,
and what it hashes to.** Nothing downstream re-downloads. `src/validate.py`
recomputes every hash in the manifest and fails the build if any moved;
`src/validate_freeze.py` protects the manifest itself.

**Publisher.** openFDA, U.S. Food and Drug Administration, `https://api.fda.gov`
and `https://download.open.fda.gov`. Keyless; 240 requests a minute and 1,000 a
day per IP. Every response's `meta.disclaimer` says to assume all results are
unvalidated, and the page repeats it.

**Not committed to git, deliberately.** The S-01 record-level pages carry
narratives, patient arrays and addresses and run to hundreds of megabytes.
They sit gzipped in `data/raw/staging/` and the freeze is asserted by the
SHA-256 of each response body as received, recorded in `data/raw/manifest.json`.
The S-03 to S-05 bulk zips are likewise hashed and ignored. The S-02 count
series, the download index and the VMSR page are small and are committed.
This is the module's deliberate departure from PRINCIPLES rule 1's mechanism,
the same one `cascadia-matter-ledger-analytics` records.

**The source moves weekly and in place.** openFDA states that every record may
change on a refresh, and `date_changed` exists on records. Each response's
`meta.last_updated` is recorded; an extraction whose responses disagree on it
is aborted and restarted. That is why the hash is the freeze.

"""


def cmd_register() -> int:
    manifest = load_manifest()
    files = manifest["files"]
    by_source: dict[str, list[tuple[str, dict]]] = {}
    for rel, e in files.items():
        by_source.setdefault(e.get("source", "?"), []).append((rel, e))
    L = [REGISTER_HEAD]
    a = L.append
    a("## Summary by source\n")
    a("| Source | What | Responses | Bytes | meta.last_updated / export |")
    a("|---|---|---:|---:|---|")
    what = {"S-00": "download.json index", "S-01": "record-level event pages",
            "S-02": "count series per code", "S-03": "classification bulk",
            "S-04": "enforcement bulk", "S-05": "recall bulk",
            "S-06": "VMSR eligible-code list", "S-08": "exclusion-set queries (labels only)"}
    for sid in sorted(by_source):
        rows = by_source[sid]
        lus = sorted({str(e.get("meta_last_updated") or e.get("export_date") or "")
                      for _, e in rows} - {""})
        a("| %s | %s | %d | %s | %s |" % (sid, what.get(sid, ""), len(rows),
                                         format(sum(e["bytes"] for _, e in rows), ","),
                                         ", ".join(lus) or "n/a"))
    a("")
    for sid in sorted(by_source):
        a("## %s · %s\n" % (sid, what.get(sid, "")))
        a("| Path | Retrieved (UTC) | Bytes | SHA-256 | Total | Note |")
        a("|---|---|---:|---|---:|---|")
        for rel, e in sorted(by_source[sid]):
            note = ""
            if e.get("series_total") is not None:
                note = "series total %s" % format(e["series_total"], ",")
            elif e.get("records_in_page") is not None:
                note = "%d records in page" % e["records_in_page"]
            elif e.get("records_declared") is not None:
                note = "%s records declared" % format(e["records_declared"], ",")
            a("| `%s` | %s | %s | `%s` | %s | %s |"
              % (rel, e.get("retrieved_utc", ""), format(e["bytes"], ","), e["sha256"],
                 "" if e.get("results_total") is None else format(e["results_total"], ","),
                 note))
        a("")
    (GOV / "source-register.md").write_text("\n".join(L), encoding="utf-8", newline="\n")
    print("wrote governance/source-register.md: %d responses" % len(files))
    return 0


# ---------------------------------------------------------------------------
# restore (fresh clone)
# ---------------------------------------------------------------------------

def cmd_restore() -> int:
    manifest = load_manifest()
    todo = [(rel, e) for rel, e in manifest["files"].items()
            if rel.startswith("data/raw/staging/") and e.get("url") and not (REPO / rel).exists()]
    require_budget(len(todo))
    client = Client()
    bad = 0
    for rel, e in todo:
        body, parsed, info = client.get_json(e["url"])
        if sha256_bytes(body) != e["sha256"]:
            bad += 1
            print("  MOVED  %s" % rel)
            continue
        (REPO / rel).parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(REPO / rel, "wb", compresslevel=6) as gz:
            gz.write(body)
        print("  ok     %s" % rel)
    print("%d restored, %d moved since the freeze" % (len(todo) - bad, bad))
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    try:
        if cmd == "counts":
            return cmd_counts()
        if cmd == "plan":
            return cmd_plan(rest or None)
        if cmd == "extract":
            return cmd_extract(rest or None)
        if cmd == "bulk":
            return cmd_bulk()
        if cmd == "vmsr":
            return cmd_vmsr()
        if cmd == "register":
            return cmd_register()
        if cmd == "restore":
            return cmd_restore()
    except Budget as exc:
        print("BUDGET: %s" % exc)
        return 3
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
