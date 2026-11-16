"""
Publish pipeline outputs into the website's own data folder.

The website (``web/``) never reads pipeline paths. After each update the
``publish_web`` step copies what it shows into ``web.data_dir`` (default
``web/data``):

  ava.db                       consistent snapshot of the AVA database
  filter_dict.txt              filter names / wavelengths / colours
  plots/<data_id>/*.png        per-target figures (lco_latest_<data_id>*.png)
  usage/lco_usage_<sem>.png    LCO time-usage plots (when ``web.usage_src`` is set)

Only changed files are copied (size + mtime); every write goes to a temporary
file that is renamed into place, so the live site never serves a half-written
file. The source database is opened read-only, and a snapshot with no AGN is
refused. A target with no plots in its source folder keeps whatever was
published before (a missing mount never wipes the site); with ``prune`` the
plots that the pipeline no longer produces are removed.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

HTACCESS = """# Published data for the AVA website (written by ava.web.publish).
# Plots are public; the database snapshot and text files are not.
<FilesMatch "\\.(db|sqlite|txt|tmp)$">
  Require all denied
</FilesMatch>
Options -Indexes
"""


@dataclass
class PublishSummary:
    dest: Path
    agn: int = 0
    targets_with_plots: int = 0
    plots_copied: int = 0
    plots_pruned: int = 0
    usage_copied: int = 0
    filter_dict_copied: bool = False
    changes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {k: (str(v) if isinstance(v, Path) else v) for k, v in self.__dict__.items() if k != "changes"}


def _same(src: Path, dst: Path) -> bool:
    if not dst.exists():
        return False
    a, b = src.stat(), dst.stat()
    return a.st_size == b.st_size and int(a.st_mtime) == int(b.st_mtime)


def _atomic_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dst.parent, prefix=f".{dst.name}.", suffix=".tmp")
    os.close(fd)
    try:
        shutil.copy2(src, tmp)
        os.chmod(tmp, 0o644)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _copy_if_changed(src: Path, dst: Path, dry_run: bool, s: PublishSummary) -> bool:
    if _same(src, dst):
        return False
    s.changes.append(f"{src} -> {dst}")
    if not dry_run:
        _atomic_copy(src, dst)
    return True


def snapshot_db(src: Path, dest: Path, dry_run: bool = False) -> tuple[int, list[str]]:
    """Copy ``src`` to ``dest/ava.db`` with the SQLite backup API. Returns (n_agn, data_ids)."""
    with closing(sqlite3.connect(f"file:{src}?mode=ro", uri=True)) as con:
        n = con.execute("SELECT COUNT(*) FROM agn").fetchone()[0]
        if n == 0:
            raise RuntimeError(f"refusing to publish: {src} has no rows in agn")
        ids = [r[0] for r in con.execute(
            "SELECT data_id FROM agn WHERE data_id IS NOT NULL AND data_id != ''")]
        if dry_run:
            return n, ids
        dest.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=dest, prefix=".ava.db.", suffix=".tmp")
        os.close(fd)
        try:
            with closing(sqlite3.connect(tmp)) as out:
                con.backup(out)
            os.chmod(tmp, 0o644)
            os.replace(tmp, dest / "ava.db")
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    return n, ids


def publish(
    *,
    db: Path,
    filter_dict: Path,
    dest: Path,
    plots_dir_for: Callable[[str], Path],
    targets: Iterable[str] | None = None,
    usage_src: Path | None = None,
    prune: bool = False,
    dry_run: bool = False,
) -> PublishSummary:
    """Refresh the website data folder.

    Parameters
    ----------
    plots_dir_for
        ``data_id -> folder`` holding that target's ``lco_latest_<data_id>*.png``
        (the pipeline's ``cfg.target_plots_dir``).
    targets
        Only publish plots for these data_ids (default: every AGN in the database).
        The database snapshot and filter dictionary are always refreshed.
    """
    dest = Path(dest)
    s = PublishSummary(dest=dest)
    s.agn, ids = snapshot_db(Path(db), dest, dry_run)
    s.filter_dict_copied = _copy_if_changed(Path(filter_dict), dest / "filter_dict.txt", dry_run, s)

    wanted = set(targets) if targets is not None else None
    for t in ids:
        if (wanted is not None and t not in wanted) or "/" in t or t.startswith("."):
            continue
        src_dir = Path(plots_dir_for(t))
        files = sorted(src_dir.glob(f"lco_latest_{t}*.png")) if src_dir.is_dir() else []
        if not files:
            continue
        s.targets_with_plots += 1
        out_dir = dest / "plots" / t
        s.plots_copied += sum(_copy_if_changed(f, out_dir / f.name, dry_run, s) for f in files)
        if prune and out_dir.is_dir():
            keep = {f.name for f in files}
            for old in out_dir.glob("*.png"):
                if old.name not in keep:
                    s.plots_pruned += 1
                    s.changes.append(f"prune {old}")
                    if not dry_run:
                        old.unlink()

    if usage_src is not None and Path(usage_src).is_dir():
        s.usage_copied = sum(_copy_if_changed(f, dest / "usage" / f.name, dry_run, s)
                             for f in sorted(Path(usage_src).glob("lco_usage_*.png")))

    if not dry_run:
        (dest / ".htaccess").write_text(HTACCESS)
    return s


def publish_from_config(cfg, targets: Iterable[str] | None = None, dry_run: bool = False, **overrides) -> PublishSummary:
    """``publish`` with every path taken from the AVA config (``web`` section)."""
    web = cfg._raw.get("web", {}) or {}
    plots = cfg._raw.get("plots", {}) or {}
    usage = overrides.pop("usage_src", None) or web.get("usage_src")
    kw = dict(
        db=cfg.db_path,
        filter_dict=cfg._resolve(plots.get("filter_dict") or "data/reference/filter_dict.txt"),
        dest=cfg._resolve(web.get("data_dir") or "web/data"),
        plots_dir_for=cfg.target_plots_dir,
        usage_src=cfg._resolve(usage) if usage else None,
        prune=bool(web.get("prune", False)),
    )
    kw.update({k: v for k, v in overrides.items() if v is not None})
    return publish(targets=targets, dry_run=dry_run, **kw)
