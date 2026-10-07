"""recall_context.py -- M-06: the bounded recall context, from the two bulk files.

Recall records whose product code is a cohort code, deduplicated to events on
res_event_number, with the class from the enforcement endpoint joined on
event_id. No firm name, no reason text, no product description: the controlled
root-cause vocabulary, the dates, the counts.

    python src/recall_context.py          the timeline (data/conformed/recall_context.csv)
    python src/recall_context.py --count  the one pre-registered count, after review.py,
                                          exactly as governance/pre-registration.md defines it
                                          (data/conformed/recall_count.json)

Both bulk zips must hash as the manifest records them; the JSON is unzipped
beside them (gitignored) so a second path could read it with DuckDB. None
does yet: M-06 has no Path 2, and src/validate.py checks the derived set
only against the hand-verified known events (D19).
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys
import zipfile
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from acquire import COHORT, MANIFEST, REPO  # noqa: E402
from build_model import read_csv, write_csv  # noqa: E402
from forecast import add_months  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BULK = REPO / "data" / "raw" / "bulk"
CONF = REPO / "data" / "conformed"
WINDOW_START, WINDOW_END = "2016-01-01", "2026-08-31"
EVALUATED_START, EVALUATED_END = "2024-01", "2026-08"
LOOKBACK = 18


def unzip_checked(prefix: str) -> pathlib.Path:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    zips = sorted(BULK.glob(prefix + "*.zip"))
    if not zips:
        sys.exit("no %s bulk zip" % prefix)
    z = zips[0]
    rel = "data/raw/bulk/" + z.name
    want = manifest["files"][rel]["sha256"]
    h = hashlib.sha256()
    with z.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != want:
        sys.exit("%s moved since the freeze" % rel)
    out = z.with_suffix("")
    if not out.exists():
        with zipfile.ZipFile(z) as zf:
            name = [n for n in zf.namelist() if n.endswith(".json")][0]
            out.write_bytes(zf.read(name))
    return out


def norm_code(c: str | None) -> str:
    return (c or "").strip().strip("-").upper()


def timeline() -> list[dict]:
    recall = json.loads(unzip_checked("device-recall").read_text(encoding="utf-8"))["results"]
    enf = json.loads(unzip_checked("device-enforcement").read_text(encoding="utf-8"))["results"]
    enf_by_event: dict[str, list[dict]] = defaultdict(list)
    for r in enf:
        if r.get("event_id"):
            enf_by_event[str(r["event_id"])].append(r)
    in_scope = [r for r in recall if norm_code(r.get("product_code")) in COHORT]
    k_pop = sum(1 for r in in_scope if r.get("k_numbers"))
    p_pop = sum(1 for r in in_scope if r.get("pma_numbers"))
    events: dict[str, list[dict]] = defaultdict(list)
    for r in in_scope:
        events[str(r.get("res_event_number") or "")].append(r)
    rows = []
    for ev, recs in events.items():
        if not ev:
            continue
        init = min((r.get("event_date_initiated") or "9999") for r in recs)
        posted = sorted({r.get("event_date_posted") for r in recs if r.get("event_date_posted")})
        codes = sorted({norm_code(r.get("product_code")) for r in recs})
        causes = sorted({(r.get("root_cause_description") or "").strip() for r in recs} - {""})
        # pre-registration section 3: a flag, never the text, which can carry names
        cites = any(re.search(r"\b(report|reports|complaint|complaints)\b", (r.get("reason_for_recall") or ""), re.I)
                    for r in recs)
        e = enf_by_event.get(ev, [])
        classes = sorted({(x.get("classification") or "").strip() for x in e} - {""})
        rdates = sorted({x.get("report_date") for x in e if x.get("report_date")})
        cdates = sorted({x.get("center_classification_date") for x in e if x.get("center_classification_date")})
        rows.append({
            "res_event_number": ev,
            "product_codes": "|".join(codes),
            "event_date_initiated": init if init != "9999" else "",
            "event_date_posted": posted[0] if posted else "",
            "classification": "|".join(classes),
            "enforcement_report_date": rdates[0] if rdates else "",
            "enforcement_classification_date": cdates[0] if cdates else "",
            "root_cause": "|".join(causes),
            "reason_cites_reports": "true" if cites else "false",
            "product_records": len(recs),
            "records_with_k_numbers": sum(1 for r in recs if r.get("k_numbers")),
            "records_with_pma_numbers": sum(1 for r in recs if r.get("pma_numbers")),
            "in_enforcement": "true" if e else "false",
        })
    rows = [r for r in rows if r["event_date_initiated"] and WINDOW_START <= r["event_date_initiated"] <= WINDOW_END]
    rows.sort(key=lambda r: (r["event_date_initiated"], r["res_event_number"]))
    write_csv(CONF / "recall_context.csv", rows)
    n_class1 = sum(1 for r in rows if "Class I" in r["classification"].split("|"))
    print("recall context: %d in-scope product records, %d events in window, %d Class I; "
          "k_numbers populated on %d of %d in-scope records (%.1f%%), pma_numbers on %d"
          % (len(in_scope), len(rows), n_class1, k_pop, len(in_scope), 100.0 * k_pop / max(1, len(in_scope)), p_pop))
    meta = {"in_scope_product_records": len(in_scope), "events_in_window": len(rows), "class_i_events": n_class1,
            "records_with_k_numbers": k_pop, "records_with_pma_numbers": p_pop,
            "events_not_in_enforcement": sum(1 for r in rows if r["in_enforcement"] == "false")}
    (CONF / "recall_context_meta.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8", newline="\n")
    return rows


def count() -> int:
    rows = read_csv(CONF / "recall_context.csv")
    queue = [q for q in read_csv(CONF / "review_queue.csv") if q["product_code"]]
    work = {w["product_code"]: w for w in read_csv(CONF / "review_workload.csv")}
    class1 = []
    for r in rows:
        if "Class I" not in r["classification"].split("|"):
            continue
        init_m = r["event_date_initiated"][:7]
        for code in r["product_codes"].split("|"):
            if code in work and EVALUATED_START <= init_m <= EVALUATED_END:
                class1.append((code, init_m, r["res_event_number"]))
    # the pre-registered count: episodes whose start falls in the 18 months before a Class I initiation
    ep_in_window = []
    for q in queue:
        for code, init_m, ev in class1:
            if q["product_code"] == code and add_months(init_m, -LOOKBACK) <= q["episode_start"] <= add_months(init_m, -1):
                ep_in_window.append((q["product_code"], q["episode_start"], ev))
    preceded = {(code, ev) for code, init_m, ev in class1
                for q in queue if q["product_code"] == code
                and add_months(init_m, -LOOKBACK) <= q["episode_start"] <= add_months(init_m, -1)}
    # the trivial always-flag rule: every evaluated month flagged
    always_preceded = {(code, ev) for code, init_m, ev in class1
                       if add_months(init_m, -1) >= EVALUATED_START and add_months(init_m, -LOOKBACK) <= EVALUATED_END}
    out = {
        "definition": "governance/pre-registration.md, section 'The one pre-registered count'",
        "evaluated_span": [EVALUATED_START, EVALUATED_END],
        "lookback_months": LOOKBACK,
        "class_i_initiations_in_evaluated_span_by_forecast_code": len(class1),
        "class_i_initiations": [{"product_code": c, "initiated": m, "res_event_number": e} for c, m, e in class1],
        "episodes_total": len(queue),
        "episodes_whose_start_falls_in_the_18_months_before_a_class_i_initiation": len({(c, s) for c, s, _ in ep_in_window}),
        "class_i_initiations_preceded_by_an_episode_start": len(preceded),
        "always_flag_rule": {
            "class_i_initiations_preceded": len(always_preceded),
            "flagged_months_per_evaluated_month": 1.0,
            "note": "flags every month, so it precedes every initiation with an evaluated month in its window, at a workload of one flag per month",
        },
        "fixed_rule_workload_episodes_per_evaluated_month": {c: w["episodes_per_evaluated_month"] for c, w in work.items()},
        "reading": "association only; the shuffled-dates null that would make this a test is a build-forward candidate",
    }
    (CONF / "recall_count.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("pre-registered count: %d Class I initiation(s) in the evaluated span; %d preceded by an episode start; "
          "%d episode(s) start in a window; always-flag precedes %d"
          % (len(class1), len(preceded), out["episodes_whose_start_falls_in_the_18_months_before_a_class_i_initiation"],
             len(always_preceded)))
    return 0


def main(argv: list[str]) -> int:
    if "--count" in argv:
        return count()
    timeline()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
