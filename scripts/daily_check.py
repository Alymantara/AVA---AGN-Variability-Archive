#!/usr/bin/env python
"""Did the scheduled AVA jobs run, and did they succeed?

Reads the run log the cron wrapper writes (``<paths.logs>/cron_runs.tsv``, see ``scripts/cron_job.sh``), the lcodb
crawl state and the newest data in the databases, prints one line per check and a summary, and exits

    0  every check passed (warnings allowed),
    1  a job did not run in time, failed, or the archive tables are stale,

so that cron mail / alerting fires on a failure (``MAILTO`` in the crontab).

    python scripts/daily_check.py                          # production: the daily jobs within their windows
    python scripts/daily_check.py --since 2026-11-20T09:00:00Z --jobs lcodb_daily_test pipeline_test ...
                                                           # a test run (scripts/make_crontab.py --test)

The code check fetches the branch from GitHub and warns when this checkout is behind it (an update is waiting),
ahead of it, or has uncommitted edits; it never updates anything (``--no-git`` skips it).

Data checks (newest frame, newest calibration, newest download) are warnings only: on a new machine, or in a
quiet stretch with no observations, there may be nothing new and that is not a failure. Read only, except
``--web``, which also writes a short, path-free copy for the website's unlisted report page (``ava.web.report``,
``<site>/report/``).
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

#: production jobs and the hours after which a missing run is a failure (scripts/make_crontab.py)
JOBS = {"lcodb_daily": 26, "pipeline": 26, "cleanup": 26, "lco_usage": 7}
#: how the report page names the jobs
JOB_LABELS = {"lcodb_daily": "Archive sync", "pipeline": "Nightly pipeline", "cleanup": "Clean-up",
              "lco_usage": "LCO usage plots"}


def job_label(name: str) -> str:
    base = name.removesuffix("_test")
    return JOB_LABELS.get(base, base) + (" (test)" if name.endswith("_test") else "")


def utc(s: str) -> datetime:
    return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc) \
        if ("+" in str(s) or str(s).endswith("Z")) else datetime.fromisoformat(str(s)).replace(tzinfo=timezone.utc)


def read_runs(path: Path) -> list[dict]:
    out = []
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        parts = line.split("\t")
        if len(parts) == 4:
            try:
                out.append(dict(name=parts[0], start=utc(parts[1]), end=utc(parts[2]), rc=int(parts[3])))
            except ValueError:
                continue
    return out


def log_tail(path: Path, n: int = 6) -> str:
    if not path.exists():
        return ""
    lines = [l for l in path.read_text(errors="replace").splitlines() if l.strip()]
    return "\n".join("      " + l for l in lines[-n:])


class Report:
    """Prints each check; ``web=(check, text)`` also records a short, path-free line for the report page."""

    def __init__(self):
        self.fail = self.warn = 0
        self.items: list[dict] = []

    def _web(self, level, web):
        if web:
            self.items.append({"level": level, "check": web[0], "text": web[1]})

    def ok(self, msg, web=None):
        print(f"OK    {msg}")
        self._web("ok", web)

    def warning(self, msg, web=None):
        self.warn += 1
        print(f"WARN  {msg}")
        self._web("warn", web)

    def failure(self, msg, detail="", web=None):
        self.fail += 1
        print(f"FAIL  {msg}")
        if detail:
            print(detail)
        self._web("fail", web)


def check_jobs(rep: Report, log_dir: Path, jobs: dict, since: datetime | None, now: datetime):
    runs = read_runs(log_dir / "cron_runs.tsv")
    for name, max_h in jobs.items():
        mine = [r for r in runs if r["name"] == name and (since is None or r["start"] >= since)]
        if not mine:
            started = (log_dir / f"{name}.log").exists() and since is not None and any(
                l.startswith("=== ") and "start" in l and utc(l.split()[1]) >= since
                for l in (log_dir / f"{name}.log").read_text(errors="replace").splitlines() if l.startswith("=== "))
            rep.failure(f"{name}: " + ("started but not finished yet (still running?)" if started else
                                       "no run recorded" + (f" since {since:%Y-%m-%d %H:%M}Z" if since else "")),
                        web=(job_label(name), "still running" if started else "did not run"))
            continue
        last = mine[-1]
        age_h = (now - last["end"]).total_seconds() / 3600
        took = (last["end"] - last["start"]).total_seconds() / 60
        if last["rc"] != 0:
            rep.failure(f"{name}: last run {last['start']:%Y-%m-%d %H:%M}Z exited {last['rc']} after {took:.1f} min "
                        f"(log: {log_dir / (name + '.log')})", log_tail(log_dir / f"{name}.log"),
                        web=(job_label(name), f"failed (run of {last['start']:%d %b %H:%M} UTC)"))
        elif since is None and max_h and age_h > max_h:
            rep.failure(f"{name}: last run {age_h:.0f} h ago (expected within {max_h} h)",
                        web=(job_label(name), f"last ran {age_h:.0f} h ago (expected within {max_h} h)"))
        else:
            rep.ok(f"{name}: ran {last['start']:%Y-%m-%d %H:%M}Z, {took:.1f} min, exit 0",
                   web=(job_label(name), f"ran {last['start']:%d %b %H:%M} UTC, {took:.0f} min"))


def check_lcodb(rep: Report, lcfg, now: datetime, expect_sync: bool):
    state = lcfg.db_dir / "state.sqlite"
    if not state.exists():
        rep.failure(f"lcodb: {state} not found", web=("Archive tables", "not found"))
        return
    with closing(sqlite3.connect(f"file:{state}?mode=ro", uri=True)) as con:
        con.row_factory = sqlite3.Row
        last = con.execute("SELECT * FROM runs WHERE command IN ('daily', 'sync') ORDER BY id DESC LIMIT 1").fetchone()
        if last is None:
            rep.warning("lcodb: no sync / daily run recorded yet", web=("Archive tables", "no sync recorded yet"))
        else:
            msg = f"lcodb: last {last['command']} {last['started']} -> {last['status']}, {last['n_new']} new frames"
            (rep.ok if last["status"] == "ok" else rep.failure)(
                msg, web=("Archive tables", f"last sync {last['status']}, {last['n_new']} new frames"))
        rows = con.execute("SELECT proposal_id, synced_until FROM sync_state WHERE active = 1 AND synced_until "
                           "IS NOT NULL").fetchall()
    if rows:
        oldest = min(rows, key=lambda r: r["synced_until"])
        age_h = (now - utc(oldest["synced_until"])).total_seconds() / 3600
        msg = f"lcodb: active proposals synced up to {oldest['synced_until']} (oldest: {oldest['proposal_id']}, {age_h:.0f} h ago)"
        web = ("Archive coverage", f"synced to {age_h:.0f} h ago")
        if expect_sync and age_h > 30:
            rep.failure(msg + "; expected within 30 h (is `lcodb daily` running?)",
                        web=(web[0], web[1] + " (expected within 30 h)"))
        else:
            rep.ok(msg, web=web)


def git(*args, timeout=60) -> str:
    import subprocess
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}   # never wait for a password under cron
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, check=True,
                          timeout=timeout, env=env).stdout.strip()


def check_code(rep: Report, cfg) -> None:
    """Is this checkout the same as GitHub? Fetches the branch (updates only the remote-tracking ref; the working
    tree is never touched) and compares. Behind, ahead or local edits are warnings: update by hand
    (``git pull``), never automatically. Remote and branch: ``deploy.git_remote`` / ``deploy.git_branch``
    in the AVA config (default origin / main)."""
    import subprocess
    dep = cfg._raw.get("deploy", {}) or {}
    remote, branch = dep.get("git_remote") or "origin", dep.get("git_branch") or "main"
    web = "Code version"
    try:
        head = git("rev-parse", "--short", "HEAD")
        git("fetch", "--quiet", remote, branch)
        behind = int(git("rev-list", "--count", f"HEAD..{remote}/{branch}"))
        ahead = int(git("rev-list", "--count", f"{remote}/{branch}..HEAD"))
        dirty = bool(git("status", "--porcelain", "--untracked-files=no"))
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        err = getattr(exc, "stderr", "") or str(exc)
        rep.warning(f"code: could not compare with {remote}/{branch}: {err.strip().splitlines()[-1] if err.strip() else exc}",
                    web=(web, "could not reach GitHub to compare"))
        return
    parts = []
    if behind:
        parts.append(f"{behind} new commit{'s' if behind != 1 else ''} on GitHub: update with `git pull`")
    if ahead:
        parts.append(f"{ahead} local commit{'s' if ahead != 1 else ''} not on GitHub")
    if dirty:
        parts.append("uncommitted local changes")
    if parts:
        rep.warning(f"code: {head} vs {remote}/{branch}: " + "; ".join(parts),
                    web=(web, "; ".join(p.replace(": update with `git pull`", " (update needed)") for p in parts)))
    else:
        rep.ok(f"code: {head}, same as {remote}/{branch}", web=(web, "up to date with GitHub"))


def short_date(v) -> str | None:
    """A database time as 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM' (UTC), for the report page."""
    if not v:
        return None
    s = str(v).replace("T", " ").replace("Z", "")
    return s[:16] if len(s) >= 16 and s[10] == " " else s[:10]


def newest(db: Path, sql: str):
    if not db or not Path(db).exists():
        return None
    try:
        with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as con:
            return con.execute(sql).fetchone()[0]
    except sqlite3.Error:
        return None


def check_data(rep: Report, cfg, lcfg):
    phot, spec = lcfg.db_path("photometry"), lcfg.db_path("spectra")
    for label, db, sql in (("newest photometry frame in the archive tables", phot, "SELECT MAX(day_obs) FROM frames"),
                           ("newest FLOYDS frame in the archive tables", spec, "SELECT MAX(day_obs) FROM frames")):
        v = newest(db, sql)
        (rep.ok if v else rep.warning)(f"data: {label}: {v or 'none'}", web=(label[0].upper() + label[1:].replace(" in the archive tables", ""), short_date(v) or "none"))
    try:
        from ava.pipeline.tasks.calibrate import frame_db_path
        fq = frame_db_path()
    except Exception:  # noqa: BLE001 - informative only
        fq = None
    v = newest(fq, "SELECT MAX(processed_utc) FROM frame_qc")
    (rep.ok if v else rep.warning)(f"data: newest calibrated frame: {v or 'none yet'}", web=("Newest calibrated frame", short_date(v) or "none yet"))
    v = newest(cfg.db_path, "SELECT MAX(last_success_utc) FROM download_state")
    (rep.ok if v else rep.warning)(f"data: newest successful download: {v or 'none yet'}", web=("Newest successful download", short_date(v) or "none yet"))
    v = newest(spec, "SELECT MAX(reduced_utc) FROM spec_qc")
    (rep.ok if v else rep.warning)(f"data: newest reduced spectrum: {v or 'none yet'}", web=("Newest reduced spectrum", short_date(v) or "none yet"))


def probe(rep: Report, cfg, log_dir: Path) -> None:
    """What a cron job needs, checked in the environment this process has (make_crontab.py --check runs it under
    ``env -i`` plus the crontab's variables): token from its file, configs, SExtractor, banzai-floyds, writable
    log folder and Prefect home, pipeline import."""
    import importlib
    import tempfile

    from ava.lco.token import describe, find_token
    from ava.lcodb.config import load_config

    rep.ok(f"python {sys.executable}; AVA config {cfg._path}")
    try:
        lcfg = load_config(cfg.lcodb_config_path)
        rep.ok(f"lcodb config {lcfg.path}; databases {lcfg.db_dir}")
    except Exception as exc:  # noqa: BLE001
        rep.failure(f"lcodb config: {type(exc).__name__}: {exc}")
    tok, src, tried = find_token(ava_cfg=cfg)
    (rep.ok if tok else rep.failure)(f"LCO token: {'from ' + src if tok else 'NOT found. Looked at: ' + describe(tried)}")
    try:
        from ava.pipeline.tasks.sextract import sextractor_binary
        exe = sextractor_binary(cfg.photometry.sextractor.binary)
        (rep.ok if exe else rep.failure)(f"SExtractor: {exe or 'not found (' + str(cfg.photometry.sextractor.binary) + ')'}")
        from ava.pipeline.tasks.spec_reduce import reduction_settings
        py = reduction_settings()["python"]
        (rep.ok if py and Path(py).exists() else rep.failure)(f"banzai-floyds python: {py}")
    except Exception as exc:  # noqa: BLE001
        rep.failure(f"pipeline import: {type(exc).__name__}: {exc}")
    home = os.environ.get("PREFECT_HOME")
    for label, folder in (("log folder", log_dir), ("PREFECT_HOME", Path(home) if home else None)):
        if folder is None:
            rep.warning(f"{label}: not set (Prefect uses ~/.prefect)")
            continue
        try:
            folder.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=folder):
                pass
            rep.ok(f"{label} writable: {folder}")
        except OSError as exc:
            rep.failure(f"{label} {folder}: {exc}")
    try:
        importlib.import_module("ava.pipeline.flows")
        rep.ok("pipeline flows import (Prefect " + importlib.import_module("prefect").__version__ + ")")
    except Exception as exc:  # noqa: BLE001
        rep.failure(f"pipeline flows import: {type(exc).__name__}: {exc}")


def main(argv=None) -> int:
    from ava.config import cfg
    from ava.lcodb.config import load_config

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--log-dir", type=Path, default=None, help="default: paths.logs of the AVA config")
    p.add_argument("--since", default=None, help="UTC time: only runs that started after it count (test runs)")
    p.add_argument("--jobs", nargs="+", default=None, help=f"job names to check (default: {' '.join(JOBS)})")
    p.add_argument("--no-data", action="store_true", help="skip the database checks (jobs only)")
    p.add_argument("--no-git", action="store_true", help="skip comparing this checkout with GitHub")
    p.add_argument("--probe", action="store_true",
                   help="instead: check what a cron job needs in THIS environment (token file, configs, SExtractor, "
                        "banzai-floyds, writable folders, imports); scripts/make_crontab.py --check runs it under env -i")
    p.add_argument("--web", action="store_true",
                   help="also write the short, path-free report for the website's unlisted page (web.data_dir/report)")
    a = p.parse_args(argv)

    now = datetime.now(timezone.utc)
    log_dir = a.log_dir or cfg._resolve(cfg._raw.get("paths", {}).get("logs") or "logs")
    since = utc(a.since) if a.since else None
    jobs = {j: JOBS.get(j.removesuffix("_test"), 26) for j in a.jobs} if a.jobs else dict(JOBS)
    lcfg = load_config(os.environ.get("LCODB_CONFIG") or cfg.lcodb_config_path)

    print(f"AVA daily check  {now:%Y-%m-%d %H:%M}Z  host {os.uname().nodename}  logs {log_dir}")
    rep = Report()
    if a.probe:
        probe(rep, cfg, log_dir)
        print(f"\n{'FAILED' if rep.fail else 'PASSED'}: {rep.fail} failure(s), {rep.warn} warning(s)")
        return 1 if rep.fail else 0
    if time.strftime("%Z") not in ("UTC", "GMT"):
        rep.warning(f"system time zone is {time.strftime('%Z')}: cron runs the schedule in local time unless the "
                    "crontab sets CRON_TZ=UTC (cronie) or the machine runs in UTC",
                    web=("Clock", "machine not on UTC: jobs may run at the wrong time"))
    check_jobs(rep, log_dir, jobs, since, now)
    if not a.no_data:
        check_lcodb(rep, lcfg, now, expect_sync=any(j.startswith("lcodb_daily") for j in jobs) and since is None)
        check_data(rep, cfg, lcfg)
    if not a.no_git:
        check_code(rep, cfg)
    print(f"\n{'FAILED' if rep.fail else 'PASSED'}: {rep.fail} failure(s), {rep.warn} warning(s)")
    if a.web:
        from ava.web.report import prepare, report_dir, write_report
        try:
            out = report_dir(cfg)
            prepare(out)
            write_report(out, now, rep.items, rep.fail, rep.warn)
            print(f"web report written ({len(rep.items)} lines): <site>/report/")
        except OSError as exc:
            print(f"WARN  web report not written: {exc}")
    return 1 if rep.fail else 0


if __name__ == "__main__":
    sys.exit(main())
