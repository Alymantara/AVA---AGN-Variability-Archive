"""
ava.web.releases — copy the public data-release files into the website data folder.

``<web.data_dir>/releases/<release>/<data_id>/...`` mirrors exactly the files that
:func:`ava.database.releases.public_files` allows (registered, AGN flagged ``available = 1``, release public):

* a file is copied only when new or changed (size + mtime), through a temporary file, and its SHA-256 is
  checked against the database first (a file edited after registration is skipped and reported: re-run
  ``tools/register_release.py``);
* anything else under ``releases/`` (a withheld AGN, a release not public yet, an unregistered file) is removed,
  so withdrawing a flag withdraws the download at the next publish.
"""

from __future__ import annotations

from pathlib import Path

from ava.database import releases as R

HTACCESS = """# Public data-release files (written by ava.web.releases): downloadable, no directory listings.
<FilesMatch ".">
  Require all granted
</FilesMatch>
<FilesMatch "\\.tmp$">
  Require all denied
</FilesMatch>
Options -Indexes
"""


def publish_releases(db: Path, releases_root: Path, dest: Path, dry_run: bool = False, today=None) -> dict:
    """Mirror the public release files into ``dest/releases``. Returns counts and the list of problems."""
    from ava.web.publish import PublishSummary, _copy_if_changed, _same

    out_root = Path(dest) / "releases"
    s = PublishSummary(dest=Path(dest))
    keep, copied, problems = set(), 0, []
    for f in R.public_files(Path(db), today):
        src = Path(releases_root) / f["release"] / f["path"]
        dst = out_root / f["release"] / f["path"]
        if not src.is_file():
            problems.append(f"missing: {src}")
            continue
        if dst.exists() and _same(src, dst):
            keep.add(dst)
            continue
        if R._sha256(src) != f["sha256"]:
            problems.append(f"changed since registration (re-register): {src}")
            continue
        keep.add(dst)
        copied += _copy_if_changed(src, dst, dry_run, s)
    pruned = 0
    if out_root.is_dir():
        for p in sorted(out_root.rglob("*"), reverse=True):          # files first, then emptied folders
            if p.is_file() and p not in keep and p.name != ".htaccess":
                pruned += 1
                if not dry_run:
                    p.unlink()
            elif p.is_dir() and not dry_run and not any(p.iterdir()):
                p.rmdir()
    if not dry_run and keep:
        out_root.mkdir(parents=True, exist_ok=True)
        (out_root / ".htaccess").write_text(HTACCESS)
    return {"release_files": len(keep), "copied": copied, "pruned": pruned, "problems": problems}


def publish_releases_from_config(cfg, dry_run: bool = False) -> dict:
    web = cfg._raw.get("web", {}) or {}
    return publish_releases(cfg.db_path, R.releases_dir(cfg), cfg._resolve(web.get("data_dir") or "web/data"),
                            dry_run)
