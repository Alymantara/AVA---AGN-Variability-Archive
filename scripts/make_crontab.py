#!/usr/bin/env python
"""Write the AVA crontab for THIS machine: its Python, repository, config files and log folder.

    python scripts/make_crontab.py --test                 # each job ONCE, a few minutes from now, in safe mode
    python scripts/make_crontab.py --production           # the daily timetable
    python scripts/make_crontab.py --test --install       # put it in the user's crontab (between AVA markers)
    python scripts/make_crontab.py --remove               # take the AVA block out of the crontab again

Every job runs through ``scripts/cron_job.sh``, which logs to ``<paths.logs>/<job>.log`` and records each run in
``<paths.logs>/cron_runs.tsv``; ``scripts/daily_check.py`` reads that record.

``--test`` (safe: nothing is downloaded or deleted; one target):

    lcodb_daily_test   lcodb daily (the real, incremental archive crawl: a few hundred listing requests at most;
                       ``--no-archive`` replaces it with ``lcodb status``, no request)
    pipeline_test      15 min after the crawl (--pipeline-after; the two never share the lcodb databases):
                       run_pipeline.py --target <one target> with the nightly steps, downloads in dry run
                       (search only), without publishing to the website (``--with-publish`` adds it)
    cleanup_test       scripts/cleanup.py in dry run (lists what it would delete)
    lco_usage_test     scripts/lco_usage.py without the live snapshot, without publishing
    daily_check_test   scripts/daily_check.py for the four test jobs: PASSED / FAILED in daily_check_test.log

Each test line has a fixed day and month, so it runs once (then again a year later unless removed: run
``--remove`` or ``--production --install`` after the test).

``--production`` (UTC: run the machine in UTC; Debian's cron ignores CRON_TZ, so none is written):

    01:00 daily        lcodb_daily     scripts/lcodb_daily.sh
    02:00 daily        pipeline        run_pipeline.py with pipeline.prefect.nightly_steps, all targets
    05:00 daily        cleanup         scripts/cleanup.py: dry run until --cleanup-live (read the first nights' logs)
    every 6 h          lco_usage       scripts/lco_usage.py --live-snapshot
    07:00 daily        daily_check     scripts/daily_check.py (non-zero exit -> cron mails MAILTO)

The pipeline line replaces the Prefect deployment of deployment_guide section 7.3 (use one or the other).
"""
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

BEGIN, END = "# >>> AVA scheduled jobs (scripts/make_crontab.py) >>>", "# <<< AVA scheduled jobs <<<"
STEP_FLAGS = {"init": "-o", "download_data": "-d", "extract": "-e", "calibrate_data": "-c", "pytics": "-t",
              "plot": "-p", "merge_data": "-m", "save": "-s", "spec_init": "-O", "spec_download_data": "-D",
              "spec_reduce_data": "-R", "spec_products_data": "-P", "publish": "-w"}


def q(x) -> str:
    return shlex.quote(str(x))


def job_line(when: str, name: str, log_dir: Path, *cmd) -> str:
    return f"{when}  cd {q(REPO)} && scripts/cron_job.sh {name} {q(log_dir)} -- " + " ".join(q(c) for c in cmd)


def nightly_flags(steps, publish=True) -> list[str]:
    flags = [STEP_FLAGS[s] for s in steps if s in STEP_FLAGS and (publish or s != "publish")]
    unknown = [s for s in steps if s not in STEP_FLAGS]
    if unknown:
        raise SystemExit(f"unknown nightly step(s) in pipeline.prefect.nightly_steps: {unknown}")
    return flags


def header(log_dir: Path, mailto: str | None) -> list[str]:
    """The jobs' environment. cron starts with almost none, so everything a run needs is set here: the Python and
    configs, Prefect's home and settings (ava.utils.prefect_env), and TMPDIR if this shell has one."""
    from ava.utils import prefect_env

    py = Path(sys.executable)
    pe = prefect_env.apply()
    env = [f"SHELL=/bin/bash", f"PATH={py.parent}:/usr/local/bin:/usr/bin:/bin", f"AVA_PYTHON={py}"]
    for var in ("AVA_CONFIG", "LCODB_CONFIG", "TMPDIR"):
        if os.environ.get(var):
            env.append(f"{var}={os.environ[var]}")
    env += [f"{k}={v}" for k, v in pe.items() if v]
    if mailto:
        env.append(f"MAILTO={mailto}")
    return [BEGIN, f"# generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M}Z on {os.uname().nodename}; "
                   f"logs in {log_dir}"] + env


def production(cfg, log_dir: Path, mailto: str | None, cleanup_live: bool = False) -> list[str]:
    py = sys.executable
    steps = list(cfg.pipeline.prefect.nightly_steps)
    cleanup = ["--live"] if cleanup_live else []        # dry run until --cleanup-live (read the first nights' logs)
    lines = header(log_dir, mailto) + [
        job_line("0 1 * * *", "lcodb_daily", log_dir, "bash", "scripts/lcodb_daily.sh"),
        job_line("0 2 * * *", "pipeline", log_dir, py, "scripts/run_pipeline.py", *nightly_flags(steps)),
        job_line("0 5 * * *", "cleanup", log_dir, py, "scripts/cleanup.py", *cleanup),
        job_line("0 */6 * * *", "lco_usage", log_dir, py, "scripts/lco_usage.py", "--live-snapshot"),
        job_line("0 7 * * *", "daily_check", log_dir, py, "scripts/daily_check.py"),
        END]
    return lines


def test(cfg, log_dir: Path, mailto: str | None, target: str, start_in: int, gap: int, check_after: int,
         no_archive: bool, with_publish: bool, pipeline_after: int = 15) -> tuple[list[str], datetime]:
    """One-shot lines. cron reads the times in the machine's local time zone, so they are computed in local time.
    The pipeline starts ``pipeline_after`` minutes after the archive crawl (which takes ~11 min), so the two never
    use the lcodb databases at the same time; cleanup and LCO usage follow it ``gap`` minutes apart."""
    py = sys.executable
    t0 = datetime.now().astimezone().replace(second=0, microsecond=0) + timedelta(minutes=start_in)

    def at(minutes):
        t = t0 + timedelta(minutes=minutes)
        return f"{t.minute} {t.hour} {t.day} {t.month} *"

    steps = list(cfg.pipeline.prefect.nightly_steps)
    flags = nightly_flags(steps, publish=with_publish)
    lcodb = (["bash", "scripts/lcodb_daily.sh"] if not no_archive else [py, "-m", "ava.lcodb", "status"])
    jobs = ["lcodb_daily_test", "pipeline_test", "cleanup_test", "lco_usage_test"]
    since = t0.astimezone(timezone.utc) - timedelta(minutes=1)
    lines = header(log_dir, mailto) + [
        "# TEST: each line runs once (fixed day and month); remove with --remove or replace with --production --install",
        job_line(at(0), "lcodb_daily_test", log_dir, *lcodb),
        job_line(at(pipeline_after), "pipeline_test", log_dir, py, "scripts/run_pipeline.py", "--target", target,
                 "--download-mode", "dry_run", "--spec-mode", "dry_run", *flags),
        job_line(at(pipeline_after + gap), "cleanup_test", log_dir, py, "scripts/cleanup.py"),
        job_line(at(pipeline_after + 2 * gap), "lco_usage_test", log_dir, py, "scripts/lco_usage.py", "--no-publish"),
        job_line(at(check_after), "daily_check_test", log_dir, py, "scripts/daily_check.py",
                 "--since", since.strftime("%Y-%m-%dT%H:%M:%SZ"), "--jobs", *jobs),
        END]
    return lines, t0


def current_crontab() -> list[str]:
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return r.stdout.splitlines() if r.returncode == 0 else []


def without_ava_block(lines: list[str]) -> list[str]:
    out, inside = [], False
    for l in lines:
        if l.strip() == BEGIN:
            inside = True
        elif l.strip() == END:
            inside = False
        elif not inside:
            out.append(l)
    return out


def install(block: list[str] | None, log_dir: Path) -> None:
    old = current_crontab()
    log_dir.mkdir(parents=True, exist_ok=True)
    backup = log_dir / f"crontab.before.{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    backup.write_text("\n".join(old) + ("\n" if old else ""))
    new = without_ava_block(old) + (block or [])
    subprocess.run(["crontab", "-"], input="\n".join(new) + "\n", text=True, check=True)
    print(f"crontab updated (previous one saved to {backup})")


def main(argv=None) -> int:
    from ava.config import cfg
    from ava.pipeline.flows import load_targets

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--test", action="store_true")
    mode.add_argument("--production", action="store_true")
    mode.add_argument("--remove", action="store_true", help="remove the AVA block from the crontab")
    p.add_argument("--install", action="store_true", help="write it into the user's crontab (AVA block replaced)")
    p.add_argument("--log-dir", type=Path, default=None, help="default: paths.logs of the AVA config")
    p.add_argument("--mailto", default=None, help="MAILTO: where cron mails a failing job's output")
    p.add_argument("--target", default=None, help="test: the one target to run (default: the first active one)")
    p.add_argument("--start-in", type=int, default=3, help="test: minutes until the first job (default 3)")
    p.add_argument("--gap", type=int, default=3, help="test: minutes between the jobs (default 3)")
    p.add_argument("--pipeline-after", type=int, default=15,
                   help="test: minutes between the archive crawl and the pipeline (default 15: lcodb daily ~11 min)")
    p.add_argument("--check-after", type=int, default=60,
                   help="test: minutes after the first job for daily_check (default 60)")
    p.add_argument("--cleanup-live", action="store_true",
                   help="production: cleanup deletes (--live). Default: dry run, so the first nights only list "
                        "what would be deleted; read <logs>/cleanup.log, then re-run with --cleanup-live")
    p.add_argument("--no-archive", action="store_true", help="test: no LCO archive request (lcodb status instead)")
    p.add_argument("--with-publish", action="store_true", help="test: also publish to the website (-w)")
    a = p.parse_args(argv)

    log_dir = (a.log_dir or cfg._resolve(cfg._raw.get("paths", {}).get("logs") or "logs")).resolve()
    import time
    if time.strftime("%Z") not in ("UTC", "GMT"):
        print(f"# WARNING: this machine's time zone is {time.strftime('%Z')}. cron runs the times in local time "
              "(Debian's cron ignores CRON_TZ): set the machine to UTC (timedatectl set-timezone UTC) or the "
              "production times are not UTC.", file=sys.stderr)
    if a.remove:
        install(None, log_dir)
        return 0
    if a.production:
        lines = production(cfg, log_dir, a.mailto, a.cleanup_live)
        missing = [s for s in ("pytics", "spec_download_data", "spec_reduce_data", "spec_products_data")
                   if s not in cfg.pipeline.prefect.nightly_steps]
        if missing:
            print(f"# NOTE: pipeline.prefect.nightly_steps lacks {missing}", file=sys.stderr)
    else:
        target = a.target or (load_targets() or [None])[0]
        if not target:
            raise SystemExit("no active target: pass --target DATA_ID")
        lines, t0 = test(cfg, log_dir, a.mailto, target, a.start_in, a.gap, a.check_after, a.no_archive,
                         a.with_publish, a.pipeline_after)
        print(f"# test: first job at {t0:%H:%M} local time, daily_check at "
              f"{t0 + timedelta(minutes=a.check_after):%H:%M}; result in {log_dir}/daily_check_test.log",
              file=sys.stderr)
    if a.install:
        install(lines, log_dir)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
