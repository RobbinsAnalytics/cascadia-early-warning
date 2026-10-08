"""live_edge_lane.py -- the live-edge lane's checks, so the workflow YAML stays thin.

PRINCIPLES v1.1.0 Principle 12 and LIVE-EDGE-CHECKLIST v1.0.0, built for
.github/workflows/live-edge.yml (and its read-only twin, live-edge-check.yml).
Decision record D23. Every subcommand exits 0 on pass and 1 on fail, and a
failure prints the values it compared (PRINCIPLES rule 8). Standard library
only, except `gates`, which imports src/validate.py.

    allowlist      --out FILE           read the allow-list from HEAD with `git show`, reject
                                        globs and forbidden entries, save it OUTSIDE the tree
    rerender-check --list FILE          the tree must equal HEAD; rebuild both pages; each must
                                        equal its committed bytes; restore; the tree must equal
                                        HEAD again
    outcome                             the run's own record says ok or "skipped: source
                                        unchanged"; anything else fails the run
    gates                               the src/validate.py checks that can run without the
                                        gitignored staging pages, DuckDB and private list
    path-check     --list FILE          every changed or untracked path is on the list
    bundle         --list FILE --out T  path-check, then every changed path into one tar
    apply          --list FILE --bundle T
                                        lay a bundle over a clean checkout: regular files on
                                        the list only
    stage          --list FILE          `git add` by name, only listed paths, nothing left over
    range-check    --list FILE --base SHA
                                        base..HEAD is exactly one commit, a child of base, every
                                        path in it on the list
    verify-live    --list FILE          poll each page's public URL until it serves the
                                        committed bytes, or fail at the timeout

Every subcommand that takes --list re-reads the list at the commit `allowlist` read it
from, re-applies every refusal, and refuses a saved copy that differs. With the global
--head SHA (the workflow passes ${{ github.sha }}), that commit must be the run's own.

TWO JOBS, BECAUSE A CHECK IS ONLY AS GOOD AS THE PROCESS RUNNING IT (D23, attack read
findings 1 to 3). The build job runs the pull, the third-party packages and the page
build with a read-only token, and hands over only a bundle of listed files. The publish
job checks out the run's commit afresh, runs this script (standard library only) from
that checkout, applies the bundle, and is the only job that ever sees a write token,
and then only in its push step.

    python src/live_edge_lane.py --head "$RUN_SHA" allowlist --out "$RUNNER_TEMP/allowlist.json"
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import pathlib
import subprocess
import sys
import tarfile
import time
import tomllib
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = pathlib.Path(__file__).resolve().parent.parent
LIST_PATH = "governance/live-edge-allowlist.txt"
PAGE_URL = "https://www.robbinsanalytics.com/cascadia-early-warning/"

# Never on the list (LIVE-EDGE-CHECKLIST, "The allow-list"; Build Brief 2.5 step 3): the list
# itself, the workflows, the code, the templates and assets, the freeze's own file and every
# frozen path (read from freeze.toml at the same commit, below), and the files that govern the
# repo. A folder here (trailing "/") forbids everything under it.
FORBIDDEN = [
    LIST_PATH,
    ".github/",
    "src/",
    "docs/template.html",
    "docs/case-study-template.html",
    "docs/assets/",
    "governance/freeze.toml",
    "governance/decision-record.md",
    "data/conformed/record_facts.json",
    "data/raw/",
    "data/reference/",
    "data/conformed/",
    "config/",
    ".githooks/",
    ".claude/",
    ".gitattributes",
    ".gitignore",
    "requirements.txt",
    "requirements-live.txt",
    "run.ps1",
    "CLAUDE.md",
]

# The src/validate.py checks that run without the gitignored staging pages, the DuckDB record
# table and the private list (Build Brief 2.5 B5, established in a bare clone). The six that
# cannot are named with the reason; they run on Aaron's machine through `run.ps1 validate`.
LANE_CHECKS = [
    "check_extraction_log", "check_chronology", "check_locked_once", "check_emdash", "check_asof",
    "check_cohort", "check_review", "check_known_events", "check_cohort_facts", "check_words_before_chart",
    "check_case_study", "check_chart_subtitles", "check_chart_bullets", "check_c4_summary_dates",
    "check_case_card", "check_chart_descriptions", "check_table_expand", "check_low_contrast_class",
    "check_tooltip_capability",
]
NOT_IN_LANE = {
    "check_hashes": "needs the gitignored staging pages (data/raw/staging/)",
    "check_m01": "needs the gitignored DuckDB record table",
    "check_dates": "needs the gitignored DuckDB record table",
    "check_uniqueness": "needs the gitignored DuckDB record table",
    "check_exclusion": "needs the private exclusion list, which is never committed; fails closed without it",
    "check_names": "needs the private exclusion list, which is never committed; fails closed without it",
}


class LaneFail(Exception):
    pass


# ---------------------------------------------------------------------------
# git
# ---------------------------------------------------------------------------

def git(repo: pathlib.Path, *args: str, binary: bool = False, check: bool = True):
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=not binary)
    if check and r.returncode != 0:
        err = r.stderr if not binary else r.stderr.decode("utf-8", "replace")
        raise LaneFail("git %s exited %d: %s" % (" ".join(args), r.returncode, err.strip()))
    return r


def changed_paths(repo: pathlib.Path) -> list[str]:
    """Every path git sees as changed, staged or untracked (not ignored), by name."""
    out = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames").stdout
    paths = []
    for rec in out.split("\0"):
        if rec:
            paths.append(rec[3:])
    return sorted(set(paths))


def show_bytes(repo: pathlib.Path, rev: str, path: str) -> bytes:
    return git(repo, "show", "%s:%s" % (rev, path), binary=True).stdout


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------------------
# the list
# ---------------------------------------------------------------------------

def parse_list(text: str) -> list[str]:
    entries, bad = [], []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        why = None
        if any(ch in line for ch in "*?["):
            why = "a glob"
        elif "#" in line:
            why = "an inline comment"
        elif "\\" in line or line.startswith("/") or ":" in line:
            why = "not a repo-relative POSIX path"
        elif any(part in ("", ".", "..") for part in line.rstrip("/").split("/")):
            why = "an empty, '.' or '..' component"
        if why:
            bad.append("line %d %r: %s" % (n, line, why))
        else:
            entries.append(line)
    if bad:
        raise LaneFail("the allow-list carries entries the lane refuses:\n  " + "\n  ".join(bad))
    if not entries:
        raise LaneFail("the allow-list names nothing")
    return entries


def glob_prefix(pattern: str) -> str:
    """A frozen glob's literal folder: data/raw/counts/*.json -> data/raw/counts/."""
    cut = min((pattern.index(ch) for ch in "*?[" if ch in pattern), default=None)
    if cut is None:
        return pattern
    head = pattern[:cut]
    return head[: head.rfind("/") + 1]


def overlaps(entry: str, forbidden: str) -> bool:
    if entry == forbidden:
        return True
    if entry.endswith("/") and forbidden.startswith(entry):
        return True
    if forbidden.endswith("/") and entry.startswith(forbidden):
        return True
    return False


def forbidden_at(repo: pathlib.Path, rev: str) -> list[str]:
    freeze = tomllib.loads(show_bytes(repo, rev, "governance/freeze.toml").decode("utf-8"))["freeze"]
    frozen = [glob_prefix(p) for p in freeze.get("protected_paths", [])]
    return FORBIDDEN + frozen


def allowed(path: str, entries: list[str]) -> bool:
    return any(path == e or (e.endswith("/") and path.startswith(e)) for e in entries)


def list_at(repo: pathlib.Path, rev: str) -> tuple[bytes, list[str]]:
    """The list at a commit, with every refusal applied: globs, forbidden entries, no page."""
    raw = show_bytes(repo, rev, LIST_PATH)
    entries = parse_list(raw.decode("utf-8"))
    forb = forbidden_at(repo, rev)
    hits = ["%s (overlaps %s)" % (e, f) for e in entries for f in forb if overlaps(e, f)]
    if hits:
        raise LaneFail("the allow-list at %s names paths a run may never change:\n  %s"
                       % (rev[:12], "\n  ".join(sorted(set(hits)))))
    if not pages(entries):
        raise LaneFail("the allow-list names no page; the re-render check would check nothing")
    return raw, entries


def load_saved(repo: pathlib.Path, saved: str, head: str | None = None) -> dict:
    """The list as `allowlist` saved it, re-read and re-checked at the commit it was read from.

    `head` is the commit the run started from, passed into the step by the workflow
    (`${{ github.sha }}`), which no earlier step can rewrite. A saved list read from any
    other commit is refused (D23, attack read finding 3)."""
    p = pathlib.Path(saved).resolve()
    if repo.resolve() in p.parents:
        raise LaneFail("the saved list %s is inside the work tree; it must live outside it" % p)
    rec = json.loads(p.read_text(encoding="utf-8"))
    if head is not None and rec["commit"] != head:
        raise LaneFail("the saved list was read from %s, not from the run's commit %s" % (rec["commit"], head))
    raw, entries = list_at(repo, rec["commit"])
    if sha(raw) != rec["sha256"]:
        raise LaneFail("the saved list does not match %s at %s: saved %s, at the commit %s"
                       % (LIST_PATH, rec["commit"][:12], rec["sha256"], sha(raw)))
    if entries != rec["entries"]:
        raise LaneFail("the saved entries differ from the list at %s" % rec["commit"][:12])
    return rec


def pages(entries: list[str]) -> list[str]:
    return [e for e in entries if e.startswith("docs/") and e.endswith(".html")]


# ---------------------------------------------------------------------------
# subcommands
# ---------------------------------------------------------------------------

def cmd_allowlist(repo: pathlib.Path, a) -> None:
    out = pathlib.Path(a.out).resolve()
    if repo.resolve() in out.parents:
        raise LaneFail("--out %s is inside the work tree; the list is kept outside it" % out)
    head = git(repo, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip()
    if a.head is not None and head != a.head:
        raise LaneFail("HEAD is %s, not the run's commit %s" % (head, a.head))
    raw, entries = list_at(repo, head)
    out.write_text(json.dumps({"commit": head, "sha256": sha(raw), "entries": entries}, indent=1) + "\n", encoding="utf-8")
    print("allow-list read from HEAD %s (%s), %d entries, saved outside the tree at %s"
          % (head[:12], sha(raw)[:12], len(entries), out))
    for e in entries:
        print("  %s" % e)


def cmd_rerender(repo: pathlib.Path, a) -> None:
    rec = load_saved(repo, a.list, a.head)
    pg = pages(rec["entries"])
    before = changed_paths(repo)
    if before:
        raise LaneFail("the tree differs from HEAD before the re-render, so the pages would not be built from HEAD:\n  "
                       + "\n  ".join(before))
    cmd = a.build_cmd or [sys.executable, "src/build_page.py"]
    r = subprocess.run(cmd, cwd=repo, capture_output=True, text=True)
    if r.returncode != 0:
        git(repo, "checkout", "HEAD", "--", *pg, check=False)
        raise LaneFail("the rebuild from HEAD exited %d:\n%s\n%s" % (r.returncode, r.stdout[-2000:], r.stderr[-2000:]))
    bad = []
    for p in pg:
        want = show_bytes(repo, "HEAD", p)
        got = (repo / p).read_bytes() if (repo / p).exists() else b""
        if got != want:
            i = next((k for k, (x, y) in enumerate(zip(want, got)) if x != y), min(len(want), len(got)))
            bad.append("%s: committed sha256 %s (%d bytes), rebuilt %s (%d bytes); first difference at byte %d\n"
                       "      committed: %r\n      rebuilt:   %r"
                       % (p, sha(want), len(want), sha(got), len(got), i, want[max(0, i - 60):i + 60], got[max(0, i - 60):i + 60]))
        else:
            print("  re-render matches HEAD: %s sha256 %s" % (p, sha(want)))
    git(repo, "checkout", "HEAD", "--", *pg)
    after = changed_paths(repo)
    if after:
        bad.append("the rebuild wrote paths beyond the pages, left in place for inspection:\n  " + "\n  ".join(after))
    if bad:
        raise LaneFail("re-render check: the pages rebuilt from HEAD are not the committed bytes. Either code nobody "
                       "shipped is on the branch, or the rebuild is not deterministic; both are build-lane work.\n  "
                       + "\n  ".join(bad))
    print("re-render check passed: %d pages rebuilt from HEAD %s equal their committed bytes; tree restored"
          % (len(pg), rec["commit"][:12]))


def cmd_gates(repo: pathlib.Path, a) -> None:
    sys.path.insert(0, str(repo / "src"))
    import validate  # noqa: E402  (importing it runs nothing; its main() is what writes the report)
    by_name = {c.__name__: c for c in validate.CHECKS}
    missing = [n for n in LANE_CHECKS if n not in by_name]
    unaccounted = [n for n in by_name if n not in LANE_CHECKS and n not in NOT_IN_LANE]
    if missing or unaccounted:
        raise LaneFail("validate.py's checks and the lane's list disagree: named here but absent there %s; "
                       "there but neither run nor excused here %s" % (missing, unaccounted))
    failed = []
    for n in LANE_CHECKS:
        res = []
        try:
            by_name[n](res)
            _, ok, detail, failures = res[0]
        except Exception as exc:  # noqa: BLE001
            ok, detail, failures = False, "raised %s: %s" % (type(exc).__name__, exc), []
        print("  %s  %s: %s" % ("PASS" if ok else "FAIL", n, detail))
        if not ok:
            failed.append("%s: %s %s" % (n, detail, failures[:8]))
    for n, why in NOT_IN_LANE.items():
        print("  NOT RUN HERE  %s: %s" % (n, why))
    if failed:
        raise LaneFail("validate.py checks failed:\n  " + "\n  ".join(failed))
    print("gates passed: %d of %d validate.py checks run here; %d need what the runner does not have"
          % (len(LANE_CHECKS), len(by_name), len(NOT_IN_LANE)))


def cmd_path_check(repo: pathlib.Path, a) -> list[str]:
    rec = load_saved(repo, a.list, a.head)
    paths = changed_paths(repo)
    off = [p for p in paths if not allowed(p, rec["entries"])]
    if off:
        raise LaneFail("path check: %d changed or untracked path(s) are not on the allow-list read from %s:\n  %s"
                       % (len(off), rec["commit"][:12], "\n  ".join(off)))
    if not paths:
        raise LaneFail("path check: nothing changed. A passing run always appends its history line, so a run that "
                       "changed nothing did not run")
    print("path check passed: %d changed path(s), every one on the list" % len(paths))
    for p in paths:
        print("  %s" % p)
    return paths


def cmd_stage(repo: pathlib.Path, a) -> None:
    paths = cmd_path_check(repo, a)
    for i in range(0, len(paths), 100):
        git(repo, "add", "--", *paths[i:i + 100])
    staged = sorted(p for p in git(repo, "diff", "--cached", "--name-only", "-z", "--no-renames").stdout.split("\0") if p)
    unstaged = sorted(p for p in git(repo, "diff", "--name-only", "-z").stdout.split("\0") if p)
    untracked = sorted(p for p in git(repo, "ls-files", "--others", "--exclude-standard", "-z").stdout.split("\0") if p)
    if staged != paths or unstaged or untracked:
        raise LaneFail("stage: staged %s; expected %s; left unstaged %s; left untracked %s"
                       % (staged, paths, unstaged, untracked))
    print("staged %d path(s) by name" % len(staged))


def cmd_range_check(repo: pathlib.Path, a) -> None:
    rec = load_saved(repo, a.list, a.head)
    base = git(repo, "rev-parse", "--verify", a.base + "^{commit}").stdout.strip()
    head = git(repo, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip()
    commits = git(repo, "rev-list", "%s..%s" % (base, head)).stdout.split()
    if len(commits) != 1:
        raise LaneFail("range check: %s..HEAD (%s..%s) holds %d commits, not exactly one: %s"
                       % (a.base, base[:12], head[:12], len(commits), [c[:12] for c in commits]))
    parents = git(repo, "rev-list", "--parents", "-n", "1", head).stdout.split()[1:]
    if parents != [base]:
        raise LaneFail("range check: HEAD's parents are %s; the run's commit must have exactly one parent, %s (%s)"
                       % ([p[:12] for p in parents], a.base, base[:12]))
    files = sorted(p for p in git(repo, "diff-tree", "-r", "--no-commit-id", "--name-only", "-z", "--no-renames",
                                  base, head).stdout.split("\0") if p)
    off = [p for p in files if not allowed(p, rec["entries"])]
    if off or not files:
        raise LaneFail("range check: the commit changes %d path(s) off the list %s (of %d)" % (len(off), off, len(files)))
    left = changed_paths(repo)
    if left:
        raise LaneFail("range check: the tree still differs from HEAD after the commit: %s" % left)
    print("range check passed: %s..HEAD is one commit, %s, a child of %s, changing %d listed path(s)"
          % (a.base, head[:12], base[:12], len(files)))


PUBLISHABLE = ("ok", "skipped: source unchanged since ")


def cmd_outcome(repo: pathlib.Path, a) -> None:
    """The run's own record decides whether it is a result to publish (D23, attack read finding 5).
    `ok`, and `skipped: source unchanged` (a null run, Principle 9), publish. Every other status, a
    failed check or an error fails the run loudly: a rate limit or an outage is a failure to observe
    the source, not a result, and it commits nothing. The health record must be this run's."""
    run = json.loads((repo / "data" / "live" / "last_live_run.json").read_text(encoding="utf-8"))
    health = json.loads((repo / "governance" / "health.json").read_text(encoding="utf-8"))
    failed = [c["check"] for c in run.get("checks", []) if not c["passed"]]
    st = run.get("status", "")
    ok = (st == PUBLISHABLE[0] or st.startswith(PUBLISHABLE[1])) and run.get("passed") is True and not failed \
        and run.get("error") is None
    if health.get("last_run", {}).get("started_utc") != run.get("started_utc"):
        raise LaneFail("governance/health.json records the run started %s; data/live/last_live_run.json the run started %s"
                       % (health.get("last_run", {}).get("started_utc"), run.get("started_utc")))
    if not ok:
        raise LaneFail("the run is not a result to publish: status %r, passed %r, failed checks %s, error %r, notes %s"
                       % (st, run.get("passed"), failed, run.get("error"), run.get("notes")))
    print("outcome: %s (vintage %s, %d checks, none failed)" % (st, run.get("vintage"), len(run.get("checks", []))))


def cmd_bundle(repo: pathlib.Path, a) -> None:
    """The build job's hand-off: every changed path, all on the list, as regular files in one tar
    outside the tree. The publish job never runs the build's code; it gets only these bytes."""
    paths = cmd_path_check(repo, a)
    out = pathlib.Path(a.out).resolve()
    if repo.resolve() in out.parents:
        raise LaneFail("--out %s is inside the work tree" % out)
    bad = [p for p in paths if (repo / p).is_symlink() or not (repo / p).is_file()]
    if bad:
        raise LaneFail("bundle: not regular files (a deletion or a link is not something this lane writes): %s" % bad)
    with tarfile.open(out, "w") as tf:
        for p in paths:
            data = (repo / p).read_bytes()
            ti = tarfile.TarInfo(p)
            ti.size, ti.mode, ti.mtime = len(data), 0o644, 0
            tf.addfile(ti, io.BytesIO(data))
            print("  %s  %s" % (sha(data)[:16], p))
    print("bundled %d path(s) into %s" % (len(paths), out))


def cmd_apply(repo: pathlib.Path, a) -> None:
    """The publish job lays the build's bytes over a fresh checkout of the run's commit. Only regular
    files, only listed paths, no '..', no absolute path, no link anywhere on the way."""
    rec = load_saved(repo, a.list, a.head)
    before = changed_paths(repo)
    if before:
        raise LaneFail("apply: the checkout differs from HEAD before anything is applied: %s" % before)
    root = repo.resolve()
    with tarfile.open(pathlib.Path(a.bundle), "r") as tf:
        members = tf.getmembers()
        names = [m.name for m in members]
        bad = []
        for m in members:
            n = m.name
            if not m.isreg():
                bad.append("%s: not a regular file" % n)
            elif n.startswith("/") or "\\" in n or any(x in ("", ".", "..") for x in n.split("/")):
                bad.append("%s: not a plain repo-relative path" % n)
            elif not allowed(n, rec["entries"]):
                bad.append("%s: not on the list" % n)
            elif names.count(n) > 1:
                bad.append("%s: twice in the bundle" % n)
            else:
                for parent in (repo / n).parents:
                    if parent == repo:
                        break
                    if parent.is_symlink():
                        bad.append("%s: %s is a link" % (n, parent))
                        break
        if bad or not members:
            raise LaneFail("apply: the bundle is refused, nothing written:\n  " + ("\n  ".join(bad) or "it is empty"))
        for m in members:
            target = (repo / m.name).resolve()
            if root not in target.parents:
                raise LaneFail("apply: %s resolves outside the tree" % m.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            data = tf.extractfile(m).read()
            target.write_bytes(data)
            print("  %s  %s" % (sha(data)[:16], m.name))
    print("applied %d listed path(s) from the build job's bundle" % len(members))


def fetch(url: str, timeout: int = 30) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "cascadia-early-warning live-edge verify",
                                               "Cache-Control": "no-cache", "Pragma": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return -1, str(exc).encode()


def cmd_verify_live(repo: pathlib.Path, a) -> None:
    rec = load_saved(repo, a.list, a.head)
    head = git(repo, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip()
    want = {}
    for p in pages(rec["entries"]):
        rel = p[len("docs/"):]
        url = a.base_url + ("" if rel == "index.html" else rel)
        want[p] = (url, sha(show_bytes(repo, "HEAD", p)))
    deadline = time.monotonic() + a.timeout
    n, last = 0, {}
    while True:
        n += 1
        pending = []
        for p, (url, h) in want.items():
            if last.get(p, (None, None, None))[2] is True:
                continue
            status, body = fetch("%s?cb=%s-%d" % (url, head[:12], n))
            got = sha(body) if status == 200 else None
            last[p] = (status, got, got == h)
            if got != h:
                pending.append(p)
        print("  attempt %d: %s" % (n, "; ".join("%s %s" % (p, "serves HEAD" if v[2] else "HTTP %s sha256 %s" % (v[0], (v[1] or "-")[:12]))
                                              for p, v in last.items())))
        if not pending:
            print("verify-live passed: every page serves HEAD %s's bytes" % head[:12])
            for p, (url, h) in want.items():
                print("  %s  sha256 %s" % (url, h))
            return
        if time.monotonic() + a.interval > deadline:
            raise LaneFail("verify-live: after %d attempts over %ds the public site does not serve this commit's pages:\n  %s"
                           % (n, a.timeout, "\n  ".join("%s: expected sha256 %s, last served HTTP %s sha256 %s"
                                                         % (want[p][0], want[p][1], last[p][0], last[p][1]) for p in pending)))
        time.sleep(a.interval)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default=str(REPO))
    ap.add_argument("--head", default=None, help="the run's commit (github.sha); the list must come from it")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("allowlist")
    s.add_argument("--out", required=True)
    s = sub.add_parser("rerender-check")
    s.add_argument("--list", required=True)
    s.add_argument("--build-cmd", nargs="+", default=None, help=argparse.SUPPRESS)
    sub.add_parser("gates")
    sub.add_parser("outcome")
    for name in ("path-check", "stage"):
        s = sub.add_parser(name)
        s.add_argument("--list", required=True)
    s = sub.add_parser("bundle")
    s.add_argument("--list", required=True)
    s.add_argument("--out", required=True)
    s = sub.add_parser("apply")
    s.add_argument("--list", required=True)
    s.add_argument("--bundle", required=True)
    s = sub.add_parser("range-check")
    s.add_argument("--list", required=True)
    s.add_argument("--base", default="origin/main")
    s = sub.add_parser("verify-live")
    s.add_argument("--list", required=True)
    s.add_argument("--base-url", default=PAGE_URL)
    s.add_argument("--timeout", type=int, default=1200)
    s.add_argument("--interval", type=int, default=30)
    a = ap.parse_args(argv)
    repo = pathlib.Path(a.repo).resolve()
    fn = {"allowlist": cmd_allowlist, "rerender-check": cmd_rerender, "gates": cmd_gates, "outcome": cmd_outcome,
          "path-check": cmd_path_check, "stage": cmd_stage, "bundle": cmd_bundle, "apply": cmd_apply,
          "range-check": cmd_range_check, "verify-live": cmd_verify_live}[a.cmd]
    try:
        fn(repo, a)
    except LaneFail as exc:
        print("LANE FAIL %s: %s" % (a.cmd, exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
