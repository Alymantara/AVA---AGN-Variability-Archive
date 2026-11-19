"""Mark AGN as Archived (``agn.ava = 1``): all available data processed and archived.

``agn.ava`` is the status the website shows (see :mod:`ava.database.activity`): 2 Observing is automatic, and a
target that stops observing drops to 0 "to be processed". Archived (1) is the only state set by hand, once a
target's data have been processed; this script is that hand step. A later observation moves it back to Observing
automatically.

    python tools/set_archived.py Mrk_817              # dry run: shows the change
    python tools/set_archived.py Mrk_817 --write      # back up ava.db, then write

Only targets at 0 (to be processed) or NULL are changed; an Observing target (2) is refused unless ``--force``,
because the next activity update would set it back to 2 anyway while it is still observed. After writing, publish
the website snapshot (``python tools/publish_web.py``) so the site shows it.
"""
import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ava.config import cfg  # noqa: E402

ARCHIVED, OBSERVING = 1, 2
LABEL = {2: "Observing", 1: "Archived", 0: "to be processed", None: "tba"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data_id", nargs="+", help="AGN data_id(s), e.g. Mrk_817")
    ap.add_argument("--write", action="store_true", help="back up the database, then write")
    ap.add_argument("--force", action="store_true", help="also change targets that are currently Observing")
    a = ap.parse_args()
    db = Path(cfg.db_path)
    print(f"database: {db}")

    changes = []
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as con:
        for d in a.data_id:
            row = con.execute("SELECT id, ava FROM agn WHERE data_id = ?", (d,)).fetchone()
            if row is None:
                print(f"  {d:18s} not in agn: skipped")
                continue
            i, cur = row[0], (None if row[1] is None else int(row[1]))
            if cur == ARCHIVED:
                print(f"  {d:18s} already Archived")
            elif cur == OBSERVING and not a.force:
                print(f"  {d:18s} is Observing: skipped (use --force)")
            else:
                print(f"  {d:18s} {LABEL.get(cur, cur)} -> Archived")
                changes.append((i, d))
    if not changes:
        print("nothing to change")
        return
    if not a.write:
        print("\n(dry run: nothing written; add --write)")
        return
    backup = db.parent / "backups" / f"ava_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}_before_set_archived.db"
    backup.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as src, sqlite3.connect(backup) as dst:
        src.backup(dst)
    print(f"backup: {backup}")
    with sqlite3.connect(db, timeout=60) as con:
        con.executemany("UPDATE agn SET ava = ? WHERE id = ?", [(ARCHIVED, i) for i, _ in changes])
    print(f"written: {', '.join(d for _, d in changes)} -> Archived. Publish the website: python tools/publish_web.py")


if __name__ == "__main__":
    main()
