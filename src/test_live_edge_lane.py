"""Drive src/live_edge_lane.py offline, in throwaway git repositories.

No network: a local bare repository stands in for origin and a local HTTP server
for the public site. A tiny build script stands in for src/build_page.py, so each
subcommand is tested on its own logic. No repo file is touched. Exit non-zero on any
failure. The `gates` subcommand needs the real repository and is run by the workflows
and by Build Brief 2.5's local proof instead.

    .venv/Scripts/python.exe src/test_live_edge_lane.py
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import live_edge_lane as lane  # noqa: E402

FAILS: list[str] = []

LIST = """# test list
data/live/
governance/run_history.jsonl
docs/index.html
docs/case-study.html
"""
FREEZE = """[freeze]
module = "t"
as_of_date = "2026-08-31"
baseline = "x"
protected_paths = ["data/conformed/x.csv", "data/raw/counts/*.json"]
"""
# The stand-in build: both pages from the template and the live record, as build_page does.
BUILD = """import pathlib
r = pathlib.Path(__file__).resolve().parent
t = (r / "docs" / "template.html").read_text(encoding="utf-8")
h = r / "governance" / "run_history.jsonl"
n = len(h.read_text(encoding="utf-8").splitlines()) if h.exists() else 0
for name in ("index.html", "case-study.html"):
    (r / "docs" / name).write_text(t.replace("@@N@@", str(n)) + name + "\\n", encoding="utf-8", newline="\\n")
"""


def check(ok: bool, what: str, detail: str = "") -> None:
    print("  %s  %s%s" % ("ok  " if ok else "FAIL", what, (" (%s)" % detail) if detail else ""))
    if not ok:
        FAILS.append(what)


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def g(cwd, *args):
    r = sh(cwd, "git", *args)
    if r.returncode != 0:
        raise RuntimeError("git %s: %s" % (" ".join(args), r.stderr))
    return r.stdout


def write(p: pathlib.Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(s.encode("utf-8"))


def run(repo, *argv) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = lane.main(["--repo", str(repo), *argv])
    return code, buf.getvalue()


def fixture(tmp: pathlib.Path, list_text: str = LIST) -> tuple[pathlib.Path, pathlib.Path]:
    """A bare origin with one commit on main, and a working clone of it."""
    seed = tmp / "seed"
    seed.mkdir(parents=True)
    g(seed, "init", "-q", "-b", "main")
    for k, v in (("user.name", "t"), ("user.email", "t@example.invalid"), ("core.autocrlf", "false")):
        g(seed, "config", k, v)
    write(seed / lane.LIST_PATH, list_text)
    write(seed / "governance" / "freeze.toml", FREEZE)
    write(seed / "governance" / "run_history.jsonl", '{"run": 1}\n')
    write(seed / "data" / "conformed" / "x.csv", "a\n1\n")
    write(seed / "docs" / "template.html", "<p>runs @@N@@</p>\n")
    write(seed / "build.py", BUILD)
    sh(seed, sys.executable, "build.py")
    g(seed, "add", "--", lane.LIST_PATH, "governance/freeze.toml", "governance/run_history.jsonl", "data/conformed/x.csv",
      "docs/template.html", "docs/index.html", "docs/case-study.html", "build.py")
    g(seed, "commit", "-q", "-m", "seed")
    origin = tmp / "origin.git"
    g(tmp, "clone", "-q", "--bare", str(seed), str(origin))
    work = tmp / "work"
    g(tmp, "clone", "-q", "-c", "core.autocrlf=false", str(origin), str(work))
    for k, v in (("user.name", "t"), ("user.email", "t@example.invalid"), ("core.autocrlf", "false")):
        g(work, "config", k, v)
    return origin, work


def live_run(work: pathlib.Path) -> None:
    """What a passing live run does to the tree: a vintage, a history line, both pages rebuilt."""
    write(work / "data" / "live" / "counts" / "20261013T140000" / "DSQ.json", "{}\n")
    with (work / "governance" / "run_history.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write('{"run": 2}\n')
    sh(work, sys.executable, "build.py")


BUILD_CMD = ["--build-cmd", sys.executable, "build.py"]


def write_run(work: pathlib.Path, status: str, passed: bool = True, failed: bool = False, health_started: str | None = None):
    started = "2026-10-13T14:17:00+00:00"
    run = {"started_utc": started, "status": status, "passed": passed, "error": None, "vintage": None, "notes": [],
           "checks": [{"check": "c", "value": 1, "expected": None, "passed": not failed}]}
    write(work / "data" / "live" / "last_live_run.json", json.dumps(run))
    write(work / "governance" / "health.json", json.dumps({"last_run": {"started_utc": health_started or started}}))


def part_two() -> None:
    """Attack read findings 1 to 5 (D23): the run's commit pins the list, the refusals are re-run on
    every load, the run's record decides, and the publish job takes only a bundle of listed files."""
    import tarfile
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        saved = str(tmp / "allowlist.json")
        origin, work = fixture(tmp / "a")
        head = g(work, "rev-parse", "HEAD").strip()

        print("--head: the run's commit")
        code, out = run(work, "--head", head, "allowlist", "--out", saved)
        check(code == 0, "the list read at the run's commit passes")
        code, out = run(work, "--head", "0" * 40, "allowlist", "--out", str(tmp / "x.json"))
        check(code == 1 and "not the run's commit" in out, "HEAD other than the run's commit is refused")
        # A build that commits a widened list locally and forges the saved copy to point at it.
        write(work / lane.LIST_PATH, LIST + "src/\n")
        g(work, "commit", "-q", "-am", "widen the list")
        forged_commit = g(work, "rev-parse", "HEAD").strip()
        raw = lane.show_bytes(work, forged_commit, lane.LIST_PATH)
        forged = tmp / "forged.json"
        forged.write_text(json.dumps({"commit": forged_commit, "sha256": lane.sha(raw),
                                      "entries": lane.parse_list(raw.decode())}), encoding="utf-8")
        code, out = run(work, "--head", head, "path-check", "--list", str(forged))
        check(code == 1 and "not from the run's commit" in out, "a saved list forged at another commit is refused by --head")
        code, out = run(work, "path-check", "--list", str(forged))
        check(code == 1 and "never change" in out, "and the forbidden entries are re-checked on every load, --head or not")
        g(work, "reset", "-q", "--hard", head)

        print("outcome: the run's own record decides")
        for status, passed, failed, hs, want, what in (
                ("ok", True, False, None, 0, "ok publishes"),
                ("skipped: source unchanged since 2026-09-29", True, False, None, 0, "a null run publishes"),
                ("stopped: upstream failure", True, False, None, 1, "an outage fails loudly"),
                ("stopped: rate limited", True, False, None, 1, "a rate limit fails loudly"),
                ("ok", False, True, None, 1, "a failed check fails"),
                ("ok", True, False, "2026-10-06T00:00:00+00:00", 1, "a health record from another run fails")):
            write_run(work, status, passed, failed, hs)
            code, out = run(work, "outcome")
            check(code == want, what, out.strip().splitlines()[-1][:100] if code != want else "")
        g(work, "checkout", "--", ".")
        for p in ("data/live/last_live_run.json", "governance/health.json"):
            if (work / p).exists() and p not in g(work, "ls-files"):
                (work / p).unlink()

        print("bundle and apply: the publish job takes bytes, never code")
        live_run(work)
        bundle = tmp / "b.tar"
        code, out = run(work, "--head", head, "bundle", "--list", saved, "--out", str(bundle))
        check(code == 0 and len(tarfile.open(bundle).getnames()) == 4, "the build job bundles its four listed paths")
        fresh = tmp / "fresh"
        g(tmp, "clone", "-q", "-c", "core.autocrlf=false", str(origin), str(fresh))
        for k, v in (("user.name", "t"), ("user.email", "t@example.invalid")):
            g(fresh, "config", k, v)
        saved2 = str(tmp / "allowlist2.json")
        run(fresh, "--head", head, "allowlist", "--out", saved2)
        code, out = run(fresh, "--head", head, "apply", "--list", saved2, "--bundle", str(bundle))
        same = all((fresh / p).read_bytes() == (work / p).read_bytes() for p in tarfile.open(bundle).getnames())
        code2, _ = run(fresh, "--head", head, "path-check", "--list", saved2)
        check(code == 0 and same and code2 == 0, "a fresh checkout takes the bundle byte for byte, inside the list")
        g(fresh, "reset", "-q", "--hard", head)
        g(fresh, "clean", "-q", "-fd")

        def evil(name: str, kind: str = "file") -> pathlib.Path:
            t = tmp / ("evil-%d.tar" % abs(hash((name, kind))))
            with tarfile.open(t, "w") as tf:
                ti = tarfile.TarInfo(name)
                if kind == "link":
                    ti.type, ti.linkname = tarfile.SYMTYPE, "../../src"
                else:
                    ti.size = 2
                tf.addfile(ti, io.BytesIO(b"x\n") if kind == "file" else None)
            return t
        for name, kind, what in (("src/live_edge_lane.py", "file", "an off-list member"),
                                 ("data/live/../../src/x.py", "file", "a '..' member"),
                                 ("/etc/x", "file", "an absolute member"),
                                 ("data/live/counts", "link", "a link member")):
            code, out = run(fresh, "--head", head, "apply", "--list", saved2, "--bundle", str(evil(name, kind)))
            check(code == 1 and "nothing written" in out and sh(fresh, "git", "status", "--porcelain").stdout == "",
                  "apply refuses %s and writes nothing" % what)


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        saved = str(tmp / "allowlist.json")
        origin, work = fixture(tmp / "a")

        print("allowlist")
        code, out = run(work, "allowlist", "--out", saved)
        check(code == 0 and json.loads(pathlib.Path(saved).read_text())["entries"][0] == "data/live/", "HEAD's list is read and saved outside the tree")
        code, out = run(work, "allowlist", "--out", str(work / "inside.json"))
        check(code == 1 and "inside the work tree" in out, "a saved copy inside the tree is refused")
        for bad, why in (("docs/*.html", "a glob"), ("src/", "src/"), (lane.LIST_PATH, "the list itself"),
                         (".github/workflows/live-edge.yml", "a workflow"), ("docs/template.html", "a template"),
                         ("governance/freeze.toml", "freeze.toml"), ("data/conformed/x.csv", "a frozen path"),
                         ("data/raw/counts/DSQ_date_received.json", "a file under a frozen glob"),
                         ("data/", "a folder over frozen paths"), ("docs/", "a folder over the templates"),
                         ("data/conformed/record_facts.json", "the record-facts JSON"), ("../x", "a '..' path")):
            sub = tmp / ("bad%d" % abs(hash(bad)))
            _, w = fixture(sub, LIST + bad + "\n")
            code, out = run(w, "allowlist", "--out", str(sub / "l.json"))
            check(code == 1 and "LANE FAIL" in out, "the list refuses %s" % why, out.strip().splitlines()[-1][:90] if code != 1 else "")

        print("rerender-check")
        code, out = run(work, "rerender-check", "--list", saved, *BUILD_CMD)
        check(code == 0 and sh(work, "git", "status", "--porcelain").stdout == "", "pages rebuilt from HEAD match, tree restored")
        write(work / "docs" / "template.html", "<p>changed @@N@@</p>\n")
        code, out = run(work, "rerender-check", "--list", saved, *BUILD_CMD)
        check(code == 1 and "differs from HEAD before the re-render" in out, "a changed template in the tree fails it")
        g(work, "checkout", "--", "docs/template.html")
        write(work / "docs" / "template.html", "<p>shipped unseen @@N@@</p>\n")
        g(work, "commit", "-q", "-am", "template change with the pages not rebuilt")
        code, out = run(work, "rerender-check", "--list", saved, *BUILD_CMD)
        check(code == 1 and "first difference" in out and sh(work, "git", "status", "--porcelain").stdout == "",
              "committed code that changes the pages fails it, with the bytes, and restores the tree")
        g(work, "reset", "-q", "--hard", "origin/main")

        print("path-check")
        code, out = run(work, "path-check", "--list", saved)
        check(code == 1 and "nothing changed" in out, "a run that changed nothing fails")
        live_run(work)
        code, out = run(work, "path-check", "--list", saved)
        check(code == 0, "a run inside the list passes", out.strip().splitlines()[-1] if code else "")
        write(work / "notes.txt", "x\n")
        code, out = run(work, "path-check", "--list", saved)
        check(code == 1 and "notes.txt" in out, "an untracked off-list file fails it")
        (work / "notes.txt").unlink()
        write(work / "data" / "conformed" / "x.csv", "a\n2\n")
        code, out = run(work, "path-check", "--list", saved)
        check(code == 1 and "data/conformed/x.csv" in out, "a changed frozen file fails it")
        g(work, "checkout", "--", "data/conformed/x.csv")
        write(work / lane.LIST_PATH, LIST + "notes.txt\n")
        write(work / "notes.txt", "x\n")
        code, out = run(work, "path-check", "--list", saved)
        check(code == 1 and "notes.txt" in out and lane.LIST_PATH in out,
              "the list edited in the tree mid-run: HEAD's list still governs")
        g(work, "checkout", "--", lane.LIST_PATH)
        (work / "notes.txt").unlink()
        rec = json.loads(pathlib.Path(saved).read_text())
        tampered = tmp / "tampered.json"
        tampered.write_text(json.dumps(dict(rec, entries=rec["entries"] + ["notes.txt"])), encoding="utf-8")
        code, out = run(work, "path-check", "--list", str(tampered))
        check(code == 1 and "saved entries differ" in out, "a saved list that differs from HEAD's is refused")

        print("stage, commit, range-check, push")
        code, out = run(work, "stage", "--list", saved)
        staged = sh(work, "git", "diff", "--cached", "--name-only").stdout.split()
        check(code == 0 and "data/live/counts/20261013T140000/DSQ.json" in staged and len(staged) == 4,
              "listed paths staged by name, the folder expanded to its files", str(staged))
        g(work, "commit", "-q", "-m", "live edge: test run")
        code, out = run(work, "range-check", "--list", saved)
        check(code == 0, "one commit, a child of origin/main, every path listed", out.strip().splitlines()[-1][:120])
        write(work / "governance" / "run_history.jsonl", (work / "governance" / "run_history.jsonl").read_text() + '{"run": 3}\n')
        g(work, "commit", "-q", "-am", "a second commit")
        code, out = run(work, "range-check", "--list", saved)
        check(code == 1 and "holds 2 commits" in out, "two commits in the range fail it")
        g(work, "reset", "-q", "--soft", "HEAD~1")
        g(work, "reset", "-q", "--", "governance/run_history.jsonl")
        g(work, "checkout", "--", "governance/run_history.jsonl")
        write(work / "notes.txt", "x\n")
        g(work, "add", "--", "notes.txt")
        g(work, "commit", "-q", "--amend", "-m", "live edge: with an off-list file forced in")
        code, out = run(work, "range-check", "--list", saved)
        check(code == 1 and "notes.txt" in out, "an off-list path in the commit fails it")
        g(work, "reset", "-q", "--soft", "HEAD~1")
        g(work, "rm", "-q", "--cached", "--", "notes.txt")
        (work / "notes.txt").unlink()
        g(work, "commit", "-q", "-m", "live edge: test run")
        code, _ = run(work, "range-check", "--list", saved)
        other = tmp / "other"
        g(tmp, "clone", "-q", "-c", "core.autocrlf=false", str(origin), str(other))
        for k, v in (("user.name", "o"), ("user.email", "o@example.invalid"), ("core.autocrlf", "false")):
            g(other, "config", k, v)
        write(other / "README.md", "moved\n")
        g(other, "add", "--", "README.md")
        g(other, "commit", "-q", "-m", "main moved during the run")
        g(other, "push", "-q", "origin", "HEAD:main")
        before = g(origin, "rev-parse", "main").strip()
        r = sh(work, "git", "push", "origin", "HEAD:main")
        check(code == 0 and r.returncode != 0 and g(origin, "rev-parse", "main").strip() == before,
              "main moved during the run: the plain push is refused and origin is untouched", r.stderr.strip().splitlines()[-1][:80])

        print("verify-live")
        site = tmp / "site"
        site.mkdir()
        (site / "index.html").write_bytes(lane.show_bytes(work, "HEAD", "docs/index.html"))
        (site / "case-study.html").write_bytes(b"stale\n")
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a, **k):
                pass
        handler = functools.partial(Quiet, directory=str(site))
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = "http://127.0.0.1:%d/" % srv.server_address[1]
        try:
            code, out = run(work, "verify-live", "--list", saved, "--base-url", base, "--timeout", "2", "--interval", "1")
            check(code == 1 and "case-study.html: expected sha256" in out, "a page still serving old bytes fails at the timeout")
            (site / "case-study.html").write_bytes(lane.show_bytes(work, "HEAD", "docs/case-study.html"))
            code, out = run(work, "verify-live", "--list", saved, "--base-url", base, "--timeout", "2", "--interval", "1")
            check(code == 0, "both pages serving HEAD's bytes pass")
        finally:
            srv.shutdown()
            srv.server_close()

    part_two()
    print()
    print("LIVE EDGE LANE TESTS: %s" % ("PASSED" if not FAILS else "FAILED: " + "; ".join(FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
