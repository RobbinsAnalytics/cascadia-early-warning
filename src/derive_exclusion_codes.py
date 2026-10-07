"""derive_exclusion_codes.py -- the product-code set excluded from the cohort.

Reads the private list at governance/exclusion-list.local.txt (gitignored),
asks openFDA which product codes the listed firms have cleared (510(k)),
approved (PMA), recalled, listed under a registration, or reported under in
MAUDE, and writes the union to data/reference/excluded_product_codes.csv with
NO firm name, NO query text and NO per-firm attribution. The count responses
are staged (gitignored) and hashed into data/raw/manifest.json under labels
rather than URLs, because a URL would carry the tokens.

Eleven requests. The MAUDE query is capped at 100 buckets without a key, and
that cap is recorded in the receipt rather than worked around.

    python src/derive_exclusion_codes.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import re
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from acquire import API, REPO, STAGING, Client, load_manifest, record, require_budget  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LOCAL = REPO / "governance" / "exclusion-list.local.txt"
REF = REPO / "data" / "reference"
OUT = REF / "excluded_product_codes.csv"
RECEIPT = REPO / "governance" / "exclusion-receipt.md"


def read_local() -> dict[str, list[str]]:
    if not LOCAL.exists():
        sys.exit("no private list at %s" % LOCAL)
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
            continue
        if cur:
            sections[cur].append(s)
    return sections


def local_sha256() -> str:
    return hashlib.sha256(LOCAL.read_bytes()).hexdigest()


def phrase_query(phrases: list[str]) -> str:
    quoted = ['"%s"' % p.replace(" ", "+") for p in phrases]
    return "(" + "+OR+".join(quoted) + ")"


def queries(sections: dict[str, list[str]]) -> list[tuple[str, str]]:
    """(label, url). Labels are what the manifest and receipt carry."""
    terms = sections.get("search_terms", [])
    phrases = sections.get("search_phrases", [])
    term_q = "+OR+".join(terms) if len(terms) > 1 else terms[0]
    phr_q = phrase_query(phrases)
    q = []
    q.append(("EX-01 510k applicant, primary term",
              "%s/device/510k.json?search=applicant:%s&count=product_code&limit=1000" % (API, term_q)))
    q.append(("EX-02 510k applicant, related phrases",
              "%s/device/510k.json?search=applicant:%s&count=product_code&limit=1000" % (API, phr_q)))
    q.append(("EX-03 pma applicant, primary term",
              "%s/device/pma.json?search=applicant:%s&count=product_code&limit=1000" % (API, term_q)))
    q.append(("EX-04 pma applicant, related phrases",
              "%s/device/pma.json?search=applicant:%s&count=product_code&limit=1000" % (API, phr_q)))
    q.append(("EX-05 recall recalling_firm, primary term",
              "%s/device/recall.json?search=recalling_firm:%s&count=product_code&limit=1000" % (API, term_q)))
    q.append(("EX-06 recall recalling_firm, related phrases",
              "%s/device/recall.json?search=recalling_firm:%s&count=product_code&limit=1000" % (API, phr_q)))
    q.append(("EX-07 registrationlisting registration.name, primary term",
              "%s/device/registrationlisting.json?search=registration.name:%s&count=products.product_code&limit=1000" % (API, term_q)))
    q.append(("EX-08 registrationlisting owner_operator.firm_name, primary term",
              "%s/device/registrationlisting.json?search=registration.owner_operator.firm_name:%s&count=products.product_code&limit=1000" % (API, term_q)))
    q.append(("EX-09 registrationlisting registration.name, related phrases",
              "%s/device/registrationlisting.json?search=registration.name:%s&count=products.product_code&limit=1000" % (API, phr_q)))
    q.append(("EX-10 registrationlisting owner_operator.firm_name, related phrases",
              "%s/device/registrationlisting.json?search=registration.owner_operator.firm_name:%s&count=products.product_code&limit=1000" % (API, phr_q)))
    q.append(("EX-11 event manufacturer_d_name, primary term (100-bucket cap)",
              "%s/device/event.json?search=device.manufacturer_d_name:%s&count=device.device_report_product_code.exact&limit=100" % (API, term_q)))
    return q


def normalise(code: str) -> str:
    return code.strip().strip("-").upper()


def main() -> int:
    sections = read_local()
    qs = queries(sections)
    require_budget(len(qs))
    manifest = load_manifest()
    client = Client()
    d = STAGING / "exclusion"
    d.mkdir(parents=True, exist_ok=True)
    codes: dict[str, set[str]] = {}
    per_query = []
    for i, (label, url) in enumerate(qs, 1):
        body, parsed, info = client.get_json(url, label=label)
        rel = "data/raw/staging/exclusion/ex-%02d.json" % i
        (REPO / rel).write_bytes(body)
        results = parsed.get("results", []) if info["status"] != 404 else []
        found = {normalise(r["term"]) for r in results if r.get("term")}
        found.discard("")
        for c in found:
            codes.setdefault(c, set()).add(label.split()[0])
        rec = (parsed.get("meta") or {}).get("results", {})
        per_query.append((label, len(found), sum(r["count"] for r in results), info["status"]))
        record(manifest, rel, body, "S-08", None, parsed,
               {"label": label, "codes_returned": len(found),
                "bucket_cap": 100 if "event" in url else 1000})
        print("  %-62s %4d codes  %8d records  http %s" % (label, len(found),
                                                           sum(r["count"] for r in results), info["status"]))
    REF.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["product_code", "queries_hit", "query_ids"])
        for c in sorted(codes):
            w.writerow([c, len(codes[c]), " ".join(sorted(codes[c]))])
    sha = local_sha256()
    L = ["# Exclusion receipt", "",
         "*Generated by `src/derive_exclusion_codes.py`. Regenerate; do not hand-edit.*", "",
         "The private token list is not in this repository. Its SHA-256 at the time",
         "the code set was derived:", "", "    %s" % sha, "",
         "Eleven count queries against openFDA firm fields produced the excluded",
         "product-code set in `data/reference/excluded_product_codes.csv`",
         "(%d codes). Query text is not recorded because it carries the tokens;" % len(codes),
         "each query is identified by a label only. The MAUDE query is capped at",
         "100 buckets without an API key, so the set is a lower bound on that",
         "endpoint and the cohort check below does not rely on it alone.", "",
         "| Query | Product codes returned | Records behind them | HTTP |",
         "|---|---:|---:|---|"]
    for label, n, recs, st in per_query:
        L.append("| %s | %d | %s | %s |" % (label, n, format(recs, ","), st))
    L += ["", "## Cohort check", "", "| Code | In the excluded set? |", "|---|---|"]
    from acquire import COHORT  # noqa: E402
    hit = []
    for c in COHORT:
        inset = c in codes
        if inset:
            hit.append(c)
        L.append("| %s | %s |" % (c, "YES, excluded from the cohort" if inset else "no"))
    L += ["", "Record-level removal inside the cohort (reports whose manufacturer or",
          "brand fields match the list) is counted separately in",
          "`governance/exclusion-receipt-records.md`, written by `src/build_model.py`.", ""]
    RECEIPT.write_text("\n".join(L), encoding="utf-8", newline="\n")
    print("\n%d codes in the excluded set; cohort codes in it: %s" % (len(codes), hit or "none"))
    print("private list sha256 %s" % sha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
