"""Refresh the LCO statistics in the AVA database (in place) and export its CSV copies.

  python3 -m ava.lcodb link            # first: LCO target names -> AVA ids (reads the AVA DB `agn` table)
  python3 tools/ava_crossmatch.py      # then: this script

The AVA database (lcodb config `ava.db`, normally data/ava.db) is the source of truth.  This script
NEVER rebuilds it and never touches the curated `agn` table (names, coordinates, literature values,
pipeline columns) or `agn_master` (the original master CSV, kept for provenance).  In one transaction,
after an automatic backup to <db dir>/backups/, it replaces only the derived tables:

  agn_lco      LCO / FLOYDS statistics per AVA id, recomputed from the LCO DBs (db_* columns)
  lco_targets  every LCO target name and the AVA id it is linked to (copy of lcodb `target_link`)
  agn_full     view: agn + agn_lco

Optional: --citation-edits applies curated cite_name / cite_url edits to `agn` (in place).

CSV exports (reference only, regenerated every run) in --outdir (default: the lcodb config `ava.csv` dir):
  ava.csv                    agn_full (with a header row)
  ava_nohead.csv             agn in the legacy column layout (pipeline columns excluded), no header row
  ava_lco_crossmatch.csv     AVA source -> LCO names, separation, how matched, review flags
  ava_lco_updated.csv        agn with the original LCO columns replaced by the recomputed values
                             (previous values kept as <col>_prev); used by the report
  lco_targets_not_in_ava.csv LCO targets with no AVA counterpart
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from ava.lcodb import ava as avamod  # noqa: E402
from ava.lcodb.config import load_config  # noqa: E402

FILTERS = {'B': 'B', 'V': 'V', 'u': 'up', 'g': 'gp', 'r': 'rp', 'i': 'ip', 'z': 'zs', 'Y': 'Y'}


def cadence(mjds):
    m = np.unique(np.round(np.sort(np.asarray(mjds, float)), 4))
    return float(np.median(np.diff(m))) if len(m) > 1 else np.nan


def stats(ph, sp):
    r = {f'lco_{k}': int((ph['filter'] == f).sum()) for k, f in FILTERS.items()}
    if len(ph):
        visits = ph.groupby('block_id')['mjd_obs'].min()
        r.update(lco_start=ph['day_obs'].min(), lco_end=ph['day_obs'].max(), lco_cadence=cadence(visits),
                 lco_visits=len(visits), lco_images=len(ph), lco_exp_h=ph['exptime'].sum() / 3600,
                 lco_proposals=';'.join(sorted(ph['proposal_id'].unique())))
    else:
        r.update(lco_start=None, lco_end=None, lco_cadence=np.nan, lco_visits=0, lco_images=0, lco_exp_h=0.0,
                 lco_proposals='')
    if len(sp):
        ep = sp.groupby('block_id')['mjd_obs'].min()
        r.update(floyds_epochs=len(ep), floyds_cadence=cadence(ep), floyds_start=sp['day_obs'].min(),
                 floyds_end=sp['day_obs'].max(), floyds_frames=len(sp), floyds_exp_h=sp['exptime'].sum() / 3600,
                 floyds_proposals=';'.join(sorted(sp['proposal_id'].unique())))
    else:
        r.update(floyds_epochs=0, floyds_cadence=np.nan, floyds_start=None, floyds_end=None, floyds_frames=0,
                 floyds_exp_h=0.0, floyds_proposals='')
    return r


def apply_citations(ava, path):
    """Apply curated citation edits (AVA/ava_citation_edits.csv) to cite_name / cite_url, in the AVA format:
    every entry ends with '|', and cite_url holds the ADS bibcode (empty for submitted / in prep) at the same
    position.  action=add appends an entry (skipped if the bibcode or text is already there);
    action=replace swaps the entry whose cite_name contains `old` (e.g. an 'in prep' that is now published,
    or a wrong bibcode) for the new text and bibcode, keeping its position."""
    if not path or not os.path.exists(path):
        return ava, []
    ed = pd.read_csv(path, dtype=str, keep_default_na=False)
    out, log = ava.copy(), []
    for r in ed.itertuples():
        i = out.index[out['id'] == int(r.id)]
        if len(i) != 1:
            log.append(f'id {r.id} ({r.name}) not in the AVA table: skipped')
            continue
        i = i[0]
        cn = out.at[i, 'cite_name'] if isinstance(out.at[i, 'cite_name'], str) else ''
        cu = out.at[i, 'cite_url'] if isinstance(out.at[i, 'cite_url'], str) else ''
        names = cn.split('|')[:-1] if cn else []
        urls = cu.split('|')[:-1] if cu else []
        urls += [''] * (len(names) - len(urls))
        new_name, new_url = r.cite_name.strip(), r.cite_url.strip()
        if r.action == 'replace':
            k = [j for j, n in enumerate(names) if r.old and r.old in n]
            if not k:
                if new_name in names or (new_url and new_url in urls):
                    continue   # already applied
                log.append(f'{r.name}: "{r.old}" not found, nothing replaced')
                continue
            j = k[0]
            if names[j] == new_name and urls[j] == new_url:
                continue
            log.append(f'{out.at[i, "name"]}: "{names[j]}" [{urls[j]}] -> "{new_name}" [{new_url}]')
            names[j], urls[j] = new_name, new_url
        else:
            if (new_url and new_url in urls) or new_name in [n.strip() for n in names]:
                continue
            names.append(new_name)
            urls.append(new_url)
            log.append(f'{out.at[i, "name"]}: + {new_name}' + (f' [{new_url}]' if new_url else ''))
        out.at[i, 'cite_name'] = '|'.join(names) + '|'
        out.at[i, 'cite_url'] = '|'.join(urls) + '|'
    return out, log


#: agn columns owned by the AVA pipeline (ava.database.update) — not part of the legacy CSV layout.
PIPELINE_COLUMNS = ('lco_active', 'lt_active', 'agn_gaia_dr3_id')


def read_agn(db):
    con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    try:
        return pd.read_sql('SELECT * FROM agn ORDER BY id', con)
    finally:
        con.close()


def backup(db):
    """Online SQLite backup to <db dir>/backups/<name>_<UTC stamp>_pre-crossmatch.db; returns its path."""
    out = Path(db).parent / 'backups'
    out.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    dst_path = out / f'{Path(db).stem}_{stamp}_pre-crossmatch.db'
    src, dst = sqlite3.connect(f'file:{db}?mode=ro', uri=True), sqlite3.connect(dst_path)
    try:
        src.backup(dst)
    finally:
        src.close(), dst.close()
    return dst_path


def _sqltype(dtype):
    if pd.api.types.is_bool_dtype(dtype) or pd.api.types.is_integer_dtype(dtype):
        return 'INTEGER'
    if pd.api.types.is_float_dtype(dtype):
        return 'REAL'
    return 'TEXT'


def _plain(v):
    if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA:
        return None
    return v.item() if hasattr(v, 'item') else v


def _replace_table(con, name, df):
    con.execute(f'DROP TABLE IF EXISTS "{name}"')
    cols = ', '.join(f'"{c}" {_sqltype(t)}' for c, t in df.dtypes.items())
    con.execute(f'CREATE TABLE "{name}" ({cols})')
    con.executemany(f'INSERT INTO "{name}" VALUES ({",".join("?" * df.shape[1])})',
                    [tuple(_plain(v) for v in row) for row in df.itertuples(index=False)])


def update_db(db, lco, links, cite_updates):
    """Replace the derived tables (and apply citation edits) in ONE transaction; `agn` rows are never
    added, removed or otherwise modified."""
    con = sqlite3.connect(db, isolation_level=None, timeout=60)
    try:
        con.execute('BEGIN IMMEDIATE')
        n_agn = con.execute('SELECT count(*) FROM agn').fetchone()[0]
        for i, cn, cu in cite_updates:
            con.execute('UPDATE agn SET cite_name=?, cite_url=? WHERE id=?', (cn, cu, i))
        con.execute('DROP VIEW IF EXISTS agn_full')
        _replace_table(con, 'agn_lco', lco)
        _replace_table(con, 'lco_targets', links)
        con.execute('CREATE INDEX ix_lco_targets_ava ON lco_targets(ava_id)')
        con.execute('CREATE VIEW agn_full AS SELECT a.*, l.* FROM agn a LEFT JOIN agn_lco l ON l.db_ava_id = a.id')
        if con.execute('SELECT count(*) FROM agn').fetchone()[0] != n_agn:
            raise RuntimeError('agn row count changed — aborting')
        con.execute('COMMIT')
    except Exception:
        con.execute('ROLLBACK')
        raise
    finally:
        con.close()


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--db', help='AVA database (default: lcodb config ava.db)')
    p.add_argument('--outdir', help='CSV export directory (default: directory of lcodb config ava.csv)')
    p.add_argument('--config', help='lcodb config (default: LCODB_CONFIG or the packaged default)')
    p.add_argument('--citation-edits', help='CSV of curated citation edits to apply to agn (in place)')
    p.add_argument('--dry-run', action='store_true', help='compute and export the CSVs; do not write the DB')
    a = p.parse_args()
    cfg = load_config(a.config)
    ava_cfg = cfg.get('ava') or {}
    db = Path(a.db) if a.db else cfg.resolve(ava_cfg.get('db'))
    if not db or not db.exists():
        sys.exit(f'AVA database not found: {db} (set `ava.db` in the lcodb config or pass --db)')
    outdir = Path(a.outdir) if a.outdir else cfg.resolve(ava_cfg.get('csv')).parent
    cons = {k: sqlite3.connect(f'file:{cfg.db_path(k)}?mode=ro', uri=True) for k in ('spectra', 'photometry')}
    links = pd.read_sql('SELECT * FROM target_link', cons['photometry'])
    if links.empty:
        sys.exit('target_link is empty: run `python3 -m ava.lcodb link` first')

    ava = read_agn(db)
    cite_updates, cite_log = [], []
    if a.citation_edits:
        edited, cite_log = apply_citations(ava, a.citation_edits)
        for i in edited.index[(edited.cite_name.fillna('') != ava.cite_name.fillna(''))
                              | (edited.cite_url.fillna('') != ava.cite_url.fillna(''))]:
            cite_updates.append((int(edited.at[i, 'id']), edited.at[i, 'cite_name'], edited.at[i, 'cite_url']))
        ava = edited
    outdir.mkdir(parents=True, exist_ok=True)

    ph = pd.read_sql("SELECT ava_id, filter, day_obs, mjd_obs, block_id, exptime, proposal_id FROM frames "
                     "WHERE is_best=1 AND ava_id IS NOT NULL", cons['photometry'])
    sp = pd.read_sql("SELECT ava_id, day_obs, mjd_obs, block_id, exptime, proposal_id FROM frames "
                     "WHERE rlevel=0 AND obstype='SPECTRUM' AND is_standard=0 AND ava_id IS NOT NULL", cons['spectra'])
    php, spp = dict(list(ph.groupby('ava_id'))), dict(list(sp.groupby('ava_id')))
    empty_ph, empty_sp = ph.iloc[:0], sp.iloc[:0]

    xm_rows, st_rows = [], []
    for _, s in ava.iterrows():
        i = int(s['id'])
        L = links[links.ava_id == i]
        cand = links[links.candidate_ava_id == i]
        ra, dec = s.get('ra_deg'), s.get('dec_deg')
        xm_rows.append(dict(
            id=i, name=s['name'], data_id=s.get('data_id'), ava_ra=ra, ava_dec=dec,
            lco_names=' | '.join(L.object) or None,
            sep_arcsec=' | '.join('' if pd.isna(x) else f'{x:.1f}' for x in L.sep_arcsec) or None,
            matched_by=' | '.join(L.matched_by) or None,
            name_only=bool((L.matched_by == 'name').any()),
            review='; '.join([f'{o}: {r}' for o, r in zip(L.object, L.review) if isinstance(r, str)]
                             + [f'{o}: {r}' for o, r in zip(cand.object, cand.review)]) or None,
            n_phot=int(L.n_phot.sum()), n_spec=int(L.n_spec.sum())))
        st = stats(php.get(i, empty_ph), spp.get(i, empty_sp))
        st_rows.append(dict(ava_id=i, lco_names=' | '.join(L.object), **st))
    xm = pd.DataFrame(xm_rows)
    st = pd.DataFrame(st_rows)
    today = pd.Timestamp.utcnow().strftime('%Y-%m-%d')
    lco = st.add_prefix('db_')
    lco['db_updated'] = today

    # ---- the database (in place) ----
    if a.dry_run:
        print(f'DRY RUN: {db} not modified')
    else:
        bk = backup(db)
        update_db(db, lco, links, cite_updates)
        print(f'{db}: agn_lco / lco_targets / agn_full refreshed ({len(cite_updates)} citation edits); backup {bk}')

    # ---- CSV exports (reference copies) ----
    agn_now = ava if a.dry_run else read_agn(db)
    xm.to_csv(outdir / 'ava_lco_crossmatch.csv', index=False)
    upd = agn_now.copy()
    for c in st.columns:
        if c == 'ava_id':
            continue
        out = 'lco_id_db' if c == 'lco_names' else c
        if out in upd.columns:
            upd[f'{out}_prev'] = upd[out]
        upd[out] = st[c].values
    upd['lco_db_updated'] = today
    upd.to_csv(outdir / 'ava_lco_updated.csv', index=False)
    agn_now.merge(lco, left_on='id', right_on='db_ava_id', how='left').to_csv(outdir / 'ava.csv', index=False)
    agn_now.drop(columns=[c for c in PIPELINE_COLUMNS if c in agn_now]).to_csv(
        outdir / 'ava_nohead.csv', index=False, header=False)
    new = links[links.ava_id.isna()].rename(columns={'obj_ra': 'ra', 'obj_dec': 'dec', 'pos_source': 'pos'})
    new = new[['object', 'ra', 'dec', 'pos', 'n_phot', 'n_spec', 'review']].sort_values(
        ['n_phot', 'n_spec'], ascending=False)
    new.to_csv(outdir / 'lco_targets_not_in_ava.csv', index=False)
    print(f'CSV exports written to {outdir}')

    for line in cite_log:
        print('  citation', line)
    print(f'AVA sources: {len(ava)}; with LCO data: {xm.lco_names.notna().sum()} '
          f'(name only: {xm.name_only.sum()}); to review: {xm.review.notna().sum()}; '
          f'LCO targets not in AVA: {len(new)}')
    print(xm[['name', 'lco_names', 'sep_arcsec', 'matched_by', 'n_phot', 'n_spec']].to_string())
    rv = xm[xm.review.notna()]
    if len(rv):
        print('\nto review:')
        print(rv[['name', 'review']].to_string(index=False))


if __name__ == '__main__':
    main()
