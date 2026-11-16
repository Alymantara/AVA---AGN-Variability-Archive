"""Database schema. Same `frames` table in both DBs; spectra DB adds the standard matching.

To store a new header keyword: add it to HEADER_COLUMNS and run `lcodb reextract`.
The column is created on the next open (ALTER TABLE) and filled from the stored headers,
without downloading anything again.
"""

# Columns derived from the archive listing that were added after the first release
# (auto-added to existing databases on open).
DERIVED_COLUMNS = {
    'date_utc': 'TEXT',              # 'YYYY-MM-DD HH:MM:SS' (UTC, start of exposure)
    'tel_key': 'TEXT',               # telescope from the file name, e.g. '1m010' (TELID is only '1m0a')
    'is_best': 'INTEGER DEFAULT 1',  # photometry: 1 for the highest reduction level of each exposure
    'camera': 'TEXT',                # the physical detector (archive instrument_id, e.g. 'fa14'); cameras move
                                     # between telescopes, so intercalibrate light curves by camera, not telid
    'camera_type': 'TEXT',
    'ava_id': 'INTEGER',             # AVA master-table id of the target (NULL: standard, or not an AVA source)
    'ava_data_id': 'TEXT',           # AVA data_id, e.g. 'fairall_9'           # sinistro / spectral / muscat / floyds / unknown (from the camera prefix)
}

# column -> (FITS keyword, sqlite type)
HEADER_COLUMNS = {
    'airmass': ('AIRMASS', 'REAL'),
    'agfwhm': ('AGFWHM', 'REAL'),         # guider FWHM (arcsec)
    'l1fwhm': ('L1FWHM', 'REAL'),         # BANZAI image FWHM (arcsec), reduced frames
    'l1zp': ('L1ZP', 'REAL'),
    'l1zperr': ('L1ZPERR', 'REAL'),
    'l1mean': ('L1MEAN', 'REAL'),
    'l1sigma': ('L1SIGMA', 'REAL'),
    'skymag': ('SKYMAG', 'REAL'),
    'wmsskybr': ('WMSSKYBR', 'REAL'),
    'wmscloud': ('WMSCLOUD', 'REAL'),
    'wmshumid': ('WMSHUMID', 'REAL'),
    'moondist': ('MOONDIST', 'REAL'),
    'moonfrac': ('MOONFRAC', 'REAL'),
    'moonalt': ('MOONALT', 'REAL'),
    'sunalt': ('SUNALT', 'REAL'),
    'altitude': ('ALTITUDE', 'REAL'),
    'azimuth': ('AZIMUTH', 'REAL'),
    'cat_ra': ('CAT-RA', 'TEXT'),
    'cat_dec': ('CAT-DEC', 'TEXT'),
    'srctype': ('SRCTYPE', 'TEXT'),
    'moltype': ('MOLTYPE', 'TEXT'),
    'groupid': ('GROUPID', 'TEXT'),       # request-group name
    'userid': ('USERID', 'TEXT'),
    'aperwid': ('APERWID', 'REAL'),       # FLOYDS slit width (arcsec)
    'apertype': ('APERTYPE', 'TEXT'),
    'rotmode': ('ROTMODE', 'TEXT'),
    'rotskypa': ('ROTSKYPA', 'REAL'),
    'confmode': ('CONFMODE', 'TEXT'),
    'ccdsum': ('CCDSUM', 'TEXT'),
    'pixscale': ('PIXSCALE', 'REAL'),
    'naxis1': ('NAXIS1', 'INTEGER'),
    'naxis2': ('NAXIS2', 'INTEGER'),
    'gain': ('GAIN', 'REAL'),
    'rdnoise': ('RDNOISE', 'REAL'),
    'saturate': ('SATURATE', 'REAL'),
    'utstop': ('UTSTOP', 'TEXT'),
}

FRAMES = """
CREATE TABLE IF NOT EXISTS frames (
    id INTEGER PRIMARY KEY,          -- archive frame id
    basename TEXT NOT NULL,
    exp_key TEXT NOT NULL,           -- site-camera-date-frameno: shared by a raw frame and its products
    filename TEXT, extension TEXT,
    proposal_id TEXT, instrument_id TEXT, site_id TEXT, telescope_id TEXT,
    date_obs TEXT, day_obs TEXT, mjd_obs REAL,
    exptime REAL, filter TEXT, obstype TEXT, rlevel INTEGER,
    object TEXT, ra REAL, dec REAL,  -- ra/dec: centre of the archive footprint (deg)
    block_id INTEGER, request_id INTEGER,
    public_date TEXT, version_id INTEGER, md5 TEXT,
    related TEXT,                    -- JSON list of related frame ids (calibrations / raw)
    raw_id INTEGER,                  -- for products: id of the raw frame
    is_standard INTEGER DEFAULT 0,
    airmass_calc REAL,               -- computed from site, footprint and mid-exposure time
    header_status INTEGER DEFAULT 0, -- 0 none, 1 own header, 2 inherited from raw/product twin, -1 failed
    first_seen TEXT, last_seen TEXT
);
CREATE INDEX IF NOT EXISTS ix_frames_exp ON frames(exp_key);
CREATE INDEX IF NOT EXISTS ix_frames_obj ON frames(object);
CREATE INDEX IF NOT EXISTS ix_frames_date ON frames(date_obs);
CREATE INDEX IF NOT EXISTS ix_frames_prop ON frames(proposal_id, rlevel);
CREATE INDEX IF NOT EXISTS ix_frames_type ON frames(obstype, rlevel);
CREATE INDEX IF NOT EXISTS ix_frames_block ON frames(block_id);
CREATE INDEX IF NOT EXISTS ix_frames_hdr ON frames(header_status, rlevel);
CREATE INDEX IF NOT EXISTS ix_frames_site ON frames(site_id, instrument_id);

CREATE TABLE IF NOT EXISTS headers (
    frame_id INTEGER PRIMARY KEY REFERENCES frames(id),
    fetched_at TEXT, md5 TEXT,
    header BLOB                      -- zlib-compressed JSON of the full FITS header
);
"""

VIEWS = """
CREATE TABLE IF NOT EXISTS local_files (   -- frames downloaded by AVA (ava.lco.download)
    frame_id INTEGER PRIMARY KEY, kind TEXT, role TEXT, data_id TEXT,
    path TEXT, md5 TEXT, md5_ok INTEGER, bytes INTEGER, downloaded_utc TEXT
);
CREATE TABLE IF NOT EXISTS target_link (   -- LCO object name -> AVA source (rebuilt by `lcodb link`)
    object TEXT PRIMARY KEY, ava_id INTEGER, ava_data_id TEXT, ava_name TEXT,
    sep_arcsec REAL, matched_by TEXT, pos_source TEXT, obj_ra REAL, obj_dec REAL,
    n_phot INTEGER, n_spec INTEGER, review TEXT, candidate_ava_id INTEGER, updated TEXT
);
CREATE INDEX IF NOT EXISTS ix_link_ava ON target_link(ava_id);

DROP VIEW IF EXISTS targets;
CREATE VIEW targets AS              -- per object / proposal / instrument / filter (exposures, not files)
SELECT object, MAX(ava_id) AS ava_id, proposal_id, instrument_id, filter,
       COUNT(DISTINCT exp_key) AS n_exposures, MIN(date_obs) AS first_obs, MAX(date_obs) AS last_obs,
       AVG(ra) AS ra, AVG(dec) AS dec, SUM(CASE WHEN rlevel = (SELECT MIN(rlevel) FROM frames) THEN exptime END) AS total_exptime
FROM frames
GROUP BY object, proposal_id, instrument_id, filter;
"""

PHOTOMETRY_EXTRA = """
DROP VIEW IF EXISTS images;
CREATE VIEW images AS               -- one row per exposure: BANZAI (91), or the old pipeline (90) if no 91 exists
SELECT f.*, COALESCE(f.airmass, f.airmass_calc) AS airmass_best,
       COALESCE(f.l1fwhm, f.agfwhm) AS seeing_best
FROM frames f WHERE f.is_best = 1;

DROP VIEW IF EXISTS image_quality;
CREATE VIEW image_quality AS        -- the basic per-image quality columns
SELECT id, basename, rlevel, instrument_id, filter, object, exptime,
       date_utc, day_obs, mjd_obs AS mjd, COALESCE(airmass, airmass_calc) AS airmass,
       naxis1, naxis2, site_id AS observatory,
       CASE WHEN skymag = 22.0 THEN NULL ELSE skymag END AS skymag,   -- 22.0 = placeholder
       tel_key AS telid, camera, camera_type, pixscale,
       CASE WHEN l1fwhm > 0 THEN l1fwhm END AS l1fwhm                 -- old pipeline uses -99
FROM frames WHERE is_best = 1;

DROP VIEW IF EXISTS camera_epochs;
CREATE VIEW camera_epochs AS        -- when each camera was on each telescope (for intercalibration)
SELECT camera, camera_type, site_id, tel_key AS telid,
       MIN(date_utc) AS first_utc, MAX(date_utc) AS last_utc, COUNT(*) AS n_images
FROM frames WHERE is_best = 1
GROUP BY camera, camera_type, site_id, tel_key;
"""

SPECTRA_EXTRA = """
DROP VIEW IF EXISTS exposures;
CREATE VIEW exposures AS            -- one row per raw exposure, with its BANZAI 1d product if any
SELECT r.*, p.id AS product_id, p.filename AS product_filename,
       COALESCE(r.airmass, p.airmass, r.airmass_calc) AS airmass_best
FROM frames r LEFT JOIN frames p ON p.exp_key = r.exp_key AND p.rlevel = 91
       AND p.basename LIKE '%-1d'
WHERE r.rlevel = 0;

CREATE TABLE IF NOT EXISTS calib_match (
    spec_id INTEGER,                 -- raw SPECTRUM frame (science or standard)
    calib_id INTEGER,                -- raw ARC or LAMPFLAT frame
    obstype TEXT, rank INTEGER,      -- rank within obstype
    dt_hours REAL,                   -- calib time - spectrum time
    same_block INTEGER, same_slit INTEGER, calib_aperwid REAL,
    PRIMARY KEY (spec_id, calib_id)
);
CREATE INDEX IF NOT EXISTS ix_calib_spec ON calib_match(spec_id, obstype, rank);

CREATE TABLE IF NOT EXISTS std_match (
    sci_id INTEGER, std_id INTEGER, rank INTEGER,
    dt_hours REAL,                   -- std time - science time
    same_block INTEGER, same_slit INTEGER,
    std_object TEXT, std_proposal TEXT, std_aperwid REAL, std_airmass REAL,
    PRIMARY KEY (sci_id, std_id)
);
CREATE INDEX IF NOT EXISTS ix_std_sci ON std_match(sci_id, rank);

DROP VIEW IF EXISTS spectrum_standards;
CREATE VIEW spectrum_standards AS   -- the standard to use for each science spectrum (same FLOYDS unit, <= max_dt_days):
                                    --   1. the nearest standard taken with the SAME slit width, else
                                    --   2. the nearest standard taken with the 2" slit, else
                                    --   3. the nearest standard with any slit
                                    -- (same observing block wins over time in each case). std_choice says which.
                                    -- Standards within 30 d (standards.preferred_dt_days) always win over the wider
                                    -- search window (max_dt_days); std_window says 'within_30d' or 'wide_window'.
WITH r AS (
  SELECT m.*,
         ROW_NUMBER() OVER (PARTITION BY sci_id ORDER BY same_block DESC, ABS(dt_hours)) AS r_any,
         ROW_NUMBER() OVER (PARTITION BY sci_id, COALESCE(same_slit, 0) ORDER BY same_block DESC, ABS(dt_hours)) AS r_slit,
         ROW_NUMBER() OVER (PARTITION BY sci_id, (ABS(COALESCE(std_aperwid, 0) - 2.0) < 0.05)
                            ORDER BY same_block DESC, ABS(dt_hours)) AS r_two
  FROM std_match m),
best AS (
  SELECT sci_id, std_id, std_object, std_proposal, std_aperwid, std_airmass, dt_hours, same_block, same_slit,
         CASE WHEN same_slit = 1 THEN 'same_slit'
              WHEN ABS(COALESCE(std_aperwid, 0) - 2.0) < 0.05 THEN 'nearest_2arcsec'
              ELSE 'nearest_any' END AS std_choice,
         CASE WHEN same_block = 1 OR ABS(dt_hours) <= 720 THEN 'within_30d' ELSE 'wide_window' END AS std_window,
         ROW_NUMBER() OVER (PARTITION BY sci_id ORDER BY
              CASE WHEN same_block = 1 OR ABS(dt_hours) <= 720 THEN 0 ELSE 1 END,
              CASE WHEN same_slit = 1 AND r_slit = 1 THEN 1
                   WHEN ABS(COALESCE(std_aperwid, 0) - 2.0) < 0.05 AND r_two = 1 THEN 2
                   WHEN r_any = 1 THEN 3 ELSE 9 END) AS pick
  FROM r)
SELECT s.id AS sci_id, s.basename, s.object, s.ava_id, s.instrument_id, s.date_utc, s.mjd_obs, s.aperwid,
       COALESCE(s.airmass, s.airmass_calc) AS airmass,
       b.std_id, f.basename AS std_basename, b.std_object, b.std_proposal, b.std_aperwid, b.std_airmass,
       b.dt_hours, b.same_block, b.std_choice, b.std_window
FROM frames s
LEFT JOIN best b ON b.sci_id = s.id AND b.pick = 1
LEFT JOIN frames f ON f.id = b.std_id
WHERE s.rlevel = 0 AND s.obstype = 'SPECTRUM' AND s.is_standard = 0;

DROP VIEW IF EXISTS block_calibs;
DROP VIEW IF EXISTS spectrum_calibs;
CREATE VIEW spectrum_calibs AS      -- best arc and best lamp flat of every raw spectrum
SELECT s.id AS spec_id, s.basename, s.object, s.is_standard, s.date_utc, s.mjd_obs, s.aperwid,
       a.calib_id AS arc_id, fa.basename AS arc_basename, a.dt_hours AS arc_dt_hours, a.same_block AS arc_same_block,
       l.calib_id AS flat_id, fl.basename AS flat_basename, l.dt_hours AS flat_dt_hours, l.same_block AS flat_same_block
FROM frames s
LEFT JOIN calib_match a ON a.spec_id = s.id AND a.obstype = 'ARC' AND a.rank = 1
LEFT JOIN frames fa ON fa.id = a.calib_id
LEFT JOIN calib_match l ON l.spec_id = s.id AND l.obstype = 'LAMPFLAT' AND l.rank = 1
LEFT JOIN frames fl ON fl.id = l.calib_id
WHERE s.rlevel = 0 AND s.obstype = 'SPECTRUM';
"""

STATE = """
CREATE TABLE IF NOT EXISTS sync_state (
    proposal_id TEXT PRIMARY KEY, title TEXT, active INTEGER, is_standard_source INTEGER DEFAULT 0,
    synced_until TEXT,               -- frames observed before this are in the DBs
    full_crawl_done TEXT, n_frames INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, command TEXT, started TEXT, finished TEXT,
    n_new INTEGER, n_updated INTEGER, status TEXT, message TEXT
);
CREATE TABLE IF NOT EXISTS unknown_instruments (
    instrument_id TEXT PRIMARY KEY, n_frames INTEGER, last_seen TEXT
);
"""
