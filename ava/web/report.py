"""Daily status for the website's unlisted report page (``web/report/``).

``scripts/daily_check.py --web`` writes ``<web.data_dir>/report/daily_report.json``: the overall result and one
short line per check. The lines are written for the page and carry **no** host name, path, log text, proposal ID
or token: just which job or check, whether it is fine, and when. The full report stays in the cron mail.

The page has no link from the rest of the site and is not indexed by search engines, but it is public: it shows
nothing that points to the machine. The folder itself is closed to the web (``report/.htaccess``); only the page
reads the file.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

HISTORY_DAYS = 30
HTACCESS = "# Daily report for web/report/ only (scripts/daily_check.py --web).\nRequire all denied\n"


def report_dir(cfg) -> Path:
    web = cfg._raw.get("web", {}) or {}
    return cfg._resolve(web.get("data_dir") or "web/data") / "report"


def _atomic_write(path: Path, text: str, mode: int = 0o644) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def prepare(out: Path) -> None:
    """Create the report folder, closed to direct web access (the page reads the file server-side)."""
    out.mkdir(parents=True, exist_ok=True)
    (out / ".htaccess").write_text(HTACCESS)


def write_report(out: Path, now: datetime, items: list[dict], n_fail: int, n_warn: int) -> Path:
    """Write today's report and keep the last HISTORY_DAYS days' results. ``items``: {level, check, text}."""
    out.mkdir(parents=True, exist_ok=True)
    path = out / "daily_report.json"
    try:
        old = json.loads(path.read_text())
    except (OSError, ValueError):
        old = {}
    day = f"{now:%Y-%m-%d}"
    status = "failed" if n_fail else ("warnings" if n_warn else "passed")
    history = [h for h in old.get("history", []) if h.get("day") != day]
    history.append({"day": day, "status": status, "failures": n_fail, "warnings": n_warn})
    report = {
        "checked_utc": f"{now:%Y-%m-%dT%H:%M:%SZ}",
        "status": status,
        "failures": n_fail,
        "warnings": n_warn,
        "items": items,
        "history": history[-HISTORY_DAYS:],
    }
    _atomic_write(path, json.dumps(report, indent=1) + "\n")
    return path
