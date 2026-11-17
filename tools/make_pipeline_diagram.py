#!/usr/bin/env python
"""
Draw the AVA pipeline overview: external sources, scheduled jobs, on-demand tools, data stores,
deployment boundaries (production VM, development Mac, GitHub) and the website.

One description of the boxes and arrows produces two files:

  docs/figures/ava_pipeline_overview.svg    static vector figure (light colours, for the guides and manuals;
                                             convert for LaTeX with `rsvg-convert -f pdf -o x.pdf x.svg`)
  docs/figures/ava_pipeline_overview.html   interactive page: click a box for what it is, which script /
                                             flag / file, when it runs, and what it reads and writes

    python tools/make_pipeline_diagram.py

Pure standard library; reads nothing from the pipeline. Keep the boxes in step with
docs/guides/deployment_guide.md (sections 6-8) when the pipeline changes.
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_SVG = ROOT / "docs/figures/ava_pipeline_overview.svg"
OUT_HTML = ROOT / "docs/figures/ava_pipeline_overview.html"
W, H = 1680, 1100
DATE = "17 Nov 2026"

# --------------------------------------------------------------------------------------------------
# Colours: (fill, stroke, dash) per kind. Static = literal light colours; web = CSS variables.
# --------------------------------------------------------------------------------------------------
STATIC = {
    "ext": ("#EEF1F6", "#5B6B82", None), "job": ("#E2F1EE", "#1F7A6B", None),
    "step": ("#FFFFFF", "#1F7A6B", None), "ondemand": ("#FBF0DC", "#A4680F", None),
    "db": ("#ECE7F7", "#5A4A9A", None), "file": ("#F5F3F9", "#7C719E", None),
    "temp": ("#FFFFFF", "#7C719E", "5 3"), "tobuild": ("#FFFFFF", "#B23B3B", "5 3"),
    "web": ("#E5F1E2", "#3C7A34", None), "git": ("#EEEEEE", "#3F4652", None),
    "mac": ("#F1F1F1", "#3F4652", None), "legacy": ("#F6F6F6", "#8A8F99", "5 3"),
}
STATIC_TEXT = {"fg": "#1B2230", "sub": "#4A5568", "arrow": "#3A4352", "public": "#2F7A2A",
               "private": "#B23B3B", "bg": "#FFFFFF",
               "r_ext": ("#F7F8FA", "#9AA3B2"), "r_vm": ("#FAFBFC", "#2B3442"),
               "r_web": ("#F5FAF4", "#3C7A34"), "r_vmlabel": "#2B3442"}


def C(mode: str, kind: str) -> tuple[str, str, str | None]:
    if mode == "static":
        return STATIC[kind]
    return (f"var(--{kind}-fill)", f"var(--{kind}-stroke)", STATIC[kind][2])


def T(mode: str, key: str) -> str:
    return STATIC_TEXT[key] if mode == "static" else f"var(--{key})"


SANS = "IBM Plex Sans, Helvetica Neue, Helvetica, Arial, sans-serif"
MONO = "IBM Plex Mono, Menlo, Consolas, monospace"

# --------------------------------------------------------------------------------------------------
# Boxes: id -> (kind, x, y, w, h, lines). Line style: t = title, m = mono, s = small sans, f = flag.
# --------------------------------------------------------------------------------------------------
NODES: dict[str, tuple] = {}


def node(i, kind, x, y, w, h, *lines):
    NODES[i] = (kind, x, y, w, h, lines)


# External services
node("ext_archive", "ext", 28, 120, 220, 84, ("LCO science archive", "t"), ("archive-api.lco.global", "m"),
     ("frame lists · headers · files", "s"))
node("ext_portal", "ext", 28, 216, 220, 70, ("LCO observation portal", "t"), ("observe.lco.global", "m"),
     ("charged + allocated hours", "s"))
node("ext_gaia", "ext", 28, 300, 220, 62, ("Gaia DR3 · VizieR (CDS)", "t"), ("GSPC reference stars", "s"))
node("ext_resolvers", "ext", 28, 376, 220, 62, ("SIMBAD · NED · IRSA", "t"), ("names, z, positions, E(B−V)", "s"))
node("ext_lit", "ext", 28, 452, 220, 84, ("Literature", "t"), ("AGN Black Hole Mass DB · ADS", "s"),
     ("NED · Véron-Cetty & Véron", "s"))

# Scheduled jobs, row 1
node("job_lcodb", "job", 292, 120, 176, 104, ("01:00 · Archive tables", "t"), ("scripts/lcodb_daily.sh", "m"),
     ("sync · headers · airmass", "s"), ("match · link · stats", "s"))
node("job_pipeline", "job", 484, 120, 660, 214, ("02:00 · Daily pipeline (Prefect flow ava_pipeline)", "t"),
     ("run_pipeline.py -d -e -c -t -p -D -R -P -w", "m"))
node("job_cleanup", "job", 1152, 120, 172, 104, ("05:00 · Clean-up", "t"), ("scripts/cleanup.py --live", "m"),
     ("deletes raw frames AVA", "s"), ("has finished with", "s"))
# pipeline steps (chips inside job_pipeline)
CW, CH = 100, 58
for i, (fid, flag, name, out) in enumerate([
        ("st_d", "-d", "Download", "L91 images"), ("st_e", "-e", "SExtractor", "*_cat.fits"),
        ("st_c", "-c", "Calibrate", "frame_qc+parquet"), ("st_t", "-t", "PyTICS", "merged LC, F_var"),
        ("st_p", "-p", "Web plots", "lco_latest_*.png")]):
    node(fid, "step", 500 + 110 * i, 170, CW, CH, (flag, "f"), (name, "t"), (out, "m"))
for i, (fid, flag, name, out) in enumerate([
        ("st_D", "-D", "FLOYDS d/l", "+ standards"), ("st_R", "-R", "Reduce", "banzai-floyds"),
        ("st_P", "-P", "Spec products", "Hβ, [O III] fits")]):
    node(fid, "step", 500 + 110 * i, 240, CW, CH, (flag, "f"), (name, "t"), (out, "m"))
node("st_w", "step", 1050, 170, 80, 128, ("-w", "f"), ("Publish", "t"), ("derived,", "s"), ("variability,", "s"),
     ("releases,", "s"), ("web copy", "s"))

# Scheduled jobs, row 2
node("job_usage", "job", 292, 350, 170, 66, ("Every 6 h · LCO usage", "t"), ("lco_usage.py", "m"),
     ("--live-snapshot", "m"))
node("job_backup", "tobuild", 490, 350, 150, 66, ("Weekly · Backups", "t"), ("TO BUILD (guide §10)", "s"),
     ("sqlite3 .backup, off-VM", "s"))

# Data stores
node("db_phot", "db", 292, 456, 250, 52, ("photometry.sqlite", "t"), ("frames · local_files · frame_qc", "m"))
node("db_spec", "db", 292, 516, 250, 52, ("spectra.sqlite", "t"), ("frames · std_match · spec_qc · …", "m"))
node("db_state", "db", 292, 576, 250, 52, ("state.sqlite", "t"), ("crawl state · run log", "m"))
node("db_ava", "db", 556, 456, 200, 172, ("ava.db", "t"), ("“the database is king”", "s"), ("agn (targets)", "m"),
     ("agn_lco · agn_literature", "m"), ("agn_derived", "m"), ("photometry_variability", "m"),
     ("line_variability", "m"), ("download_state", "m"), ("data_releases …", "m"))
node("f_raw", "temp", 770, 456, 270, 52, ("Raw frames (temporary)", "t"), ("raw_data/<id>/YYYYMMDD/", "m"))
node("f_cat", "file", 1054, 456, 270, 52, ("SExtractor catalogues", "t"), ("sextractor_ava/*_cat.fits", "m"))
node("f_phot", "file", 770, 516, 270, 52, ("Measurements, light curves", "t"), ("measurements.parquet · pytics/", "m"))
node("f_spec", "file", 1054, 516, 270, 52, ("Reduced spectra, line fits", "t"), ("reduced/*-1d · hbeta_fits.parquet", "m"))
node("f_plots", "file", 770, 576, 270, 52, ("Plots", "t"), ("<id>/plots/lco_latest_*.png", "m"))
node("f_rel", "file", 1054, 576, 270, 52, ("Data-release files", "t"), ("releases/<DR>/<id>/", "m"))
node("f_usage", "file", 292, 642, 250, 52, ("LCO usage log + plots", "t"), ("data/lco_usage/ (VM-local)", "m"))
node("f_lit", "file", 556, 642, 200, 52, ("Literature table", "t"), ("data/literature/*.csv", "m"))
node("f_conf", "file", 770, 642, 270, 52, ("Config + reference data", "t"), ("config/*.yaml · data/reference/", "m"))
node("f_backup", "file", 1054, 642, 270, 52, ("Database backups", "t"), ("backups/ (before curated writes)", "m"))

# On demand
OD = [
    [("od_init", "Initialise targets", "run_pipeline.py -o -O"), ("od_port", "Port legacy data", "tools/port_legacy.py"),
     ("od_status", "Backfill status", "tools/backfill_status.py"),
     ("od_backfill", "Backfill download", "scripts/download.py --live"),
     ("od_check", "Check install", "scripts/check_install.py")],
    [("od_add", "Add targets", "tools/add_ava_targets.py"),
     ("od_xmatch", "Cross-match a list", "tools/target_list_crossmatch.py"),
     ("od_lit", "Import literature", "tools/import_literature.py"),
     ("od_derive", "Derived properties", "tools/derive_agn_properties.py"),
     ("od_migrate", "Identity fixes", "tools/db_migrate_*.py")],
    [("od_release", "Register a release", "tools/register_release.py"),
     ("od_publish", "Publish by hand", "tools/publish_web.py"),
     ("od_usage_all", "Redraw all semesters", "lco_usage.py --all"),
     ("od_nh", "N_H backfill", "tools/import_nh.py"),
     ("od_assets", "Website images", "tools/build_web_assets.py")],
]
for r, row in enumerate(OD):
    for c, (i, name, cmd) in enumerate(row):
        node(i, "ondemand", 292 + 208 * c, 744 + 60 * r, 200, 50, (name, "t"), (cmd, "m"))

# Website
node("web_data", "web", 1366, 120, 284, 300, ("web.data_dir (snapshot)", "t"), ("ava/web/publish.py, releases.py", "m"))
node("web_php", "web", 1366, 440, 284, 124, ("web/ PHP pages (Apache)", "t"), ("index · targets · target · data", "m"),
     ("science · publications · about", "m"), ("live (Live Updates)", "m"),
     ("reads the ava.db snapshot", "s"), ("server-side (pdo_sqlite)", "s"))
node("web_public", "web", 1366, 588, 284, 92, ("Public visitors (HTTPS)", "t"), ("see pages, plots, manuals, released data;", "s"),
     ("never the database file", "s"), ("domain + certificate: to arrange", "s"))

# Outside the VM
node("legacy", "legacy", 28, 960, 220, 110, ("Old pipeline machine", "t"), ("SExtractor catalogues", "s"),
     ("raw FLOYDS frames", "s"), ("→ tools/port_legacy.py", "m"))
node("github", "git", 292, 960, 500, 110, ("GitHub · Alymantara/AVA", "t"),
     ("in git: code, config/, data/reference/, data/literature/*.csv,", "s"),
     ("data/ava/*.csv, manuals (PDF), snapshots.csv (install seed only)", "s"),
     ("not in git: ava.db, data/lcodb/ (>100 MB), archive data", "s"))
node("mac", "mac", 808, 960, 516, 110, ("Development Mac", "t"),
     ("test archive data/test_archive · dry-run defaults · no live LCO requests", "s"),
     ("source of the ava.db + lcodb copies (sqlite3 .backup → scp, setup step 7)", "s"),
     ("manuals: .tex → PDF in docs/manuals/ (by the author)", "s"))
node("offvm", "tobuild", 1352, 960, 312, 110, ("Off-VM backup store", "t"), ("TO BUILD", "s"),
     ("databases daily, products weekly", "s"), ("(~0.25 TB)", "s"))

# web.data_dir contents: (path, tag, note)
DATA_ROWS = [
    ("ava.db", "private", "snapshot, .htaccess denies"),
    ("filter_dict.txt, site.json", "private", ""),
    ("plots/<id>/*.png", "public", "from -p, -P"),
    ("usage/lco_usage_*.png", "public", "every 6 h + -w"),
    ("manuals/*.pdf", "public", "web.manuals"),
    ("filters/", "public", "LCO filter curves"),
    ("downloads/<id>/", "public", "if web.downloads"),
    ("releases/<DR>/", "public", "after release date"),
]

# --------------------------------------------------------------------------------------------------
# Arrows: (points, label, label_xy, anchor, dashed)
# --------------------------------------------------------------------------------------------------
ARROWS = [
    ([(248, 150), (292, 150)], None, None, None, False),
    ([(248, 192), (268, 192), (268, 276), (484, 276)], "images, FLOYDS frames", (380, 270), "middle", False),
    ([(248, 250), (256, 250), (256, 383), (292, 383)], "GET /api/proposals", (296, 344), "start", False),
    ([(248, 331), (268, 331)], None, None, None, False, False),
    ([(248, 407), (268, 407)], None, None, None, False, False),
    ([(248, 494), (268, 494), (268, 769), (292, 769)], None, None, None, False),
    ([(468, 200), (476, 200), (476, 456)], "writes", (482, 446), "start", False),
    ([(860, 334), (860, 456)], "reads + writes", (866, 440), "start", False),
    ([(1238, 224), (1238, 430), (990, 430), (990, 456)], "deletes after checks", (1114, 424), "middle", False),
    ([(1130, 270), (1366, 270)], "-w: snapshot + copy", (1250, 262), "middle", False),
    ([(292, 400), (284, 400), (284, 668), (292, 668)], None, None, None, False),
    ([(600, 960), (600, 934)], "clone / pull: code, config, usage seed", (606, 950), "start", False),
    ([(1000, 960), (1000, 934)], "hand copy ava.db + lcodb (once)", (1006, 950), "start", False),
    ([(1508, 420), (1508, 440)], None, None, None, False),
    ([(1508, 564), (1508, 588)], None, None, None, False),
]
# chip-to-chip arrows inside the pipeline box
for y in (199,):
    for i in range(4):
        ARROWS.append(([(600 + 110 * i, y), (610 + 110 * i, y)], None, None, None, False))
ARROWS.append(([(1040, 199), (1050, 199)], None, None, None, False))
for i in range(2):
    ARROWS.append(([(600 + 110 * i, 269), (610 + 110 * i, 269)], None, None, None, False))
ARROWS.append(([(820, 269), (1050, 269)], None, None, None, False))


# --------------------------------------------------------------------------------------------------
# Details shown when a box is clicked (web page only)
# --------------------------------------------------------------------------------------------------
D = {
    "ext_archive": dict(
        kind="External service", run="https://archive-api.lco.global", when="01:00 (job 1) and 02:00 (job 2)",
        what="LCO's science archive: frame listings (with footprints and reduction level), FITS headers and the "
             "files themselves (signed URLs to LCO's S3 storage). Rate limit ~4 requests/s; the code stays below it "
             "(download.rate_per_s 1, lcodb header_rate_per_s 4). Never run two archive jobs at once.",
        reads=[], writes=[], rel=["job_lcodb", "st_d", "st_D", "od_backfill"]),
    "ext_portal": dict(
        kind="External service", run="https://observe.lco.global/api/proposals/", when="every 6 h (job 6)",
        what="The observation portal's proposal list: charged and allocated hours per semester and instrument class "
             "for every KEY* proposal. One paged, read-only GET per run, token from ~/.lco_token.",
        reads=[], writes=[], rel=["job_usage"]),
    "ext_gaia": dict(
        kind="External service", run="VizieR I/355 (Gaia DR3), GSPC; photometry.reference.vizier_servers",
        when="when a target is initialised (-o) or added",
        what="Gaia DR3 synthetic photometry (GSPC) for the field stars: the absolute reference of the photometric "
             "calibration (star_id = Gaia source_id). Also the Gaia counterpart of each new AGN's nucleus.",
        reads=[], writes=[], rel=["od_init", "od_add", "od_xmatch"]),
    "ext_resolvers": dict(
        kind="External services", run="CDS Sesame (SIMBAD), NED, IRSA (extinction), HEASARC (N_H)",
        when="on demand, when adding targets",
        what="Names, positions, redshifts, object types, E(B−V) and N_H for new AVA targets.",
        reads=[], writes=[], rel=["od_add", "od_xmatch", "od_nh"]),
    "ext_lit": dict(
        kind="External sources", run="AGN Black Hole Mass Database, ADS API (~/.ads/dev_key), NED, Véron-Cetty & Véron (2010)",
        when="on demand", what="Published redshift, black-hole mass, Hβ lag, L5100 and AGN type, each with its ADS "
        "bibcode. Built into data/literature/agn_properties.csv by the scripts in data/literature/build/. The "
        "website only links to ADS; it does not query it.",
        reads=[], writes=["data/literature/*.csv"], rel=["f_lit", "od_lit"]),
    "job_lcodb": dict(
        kind="Scheduled job 1 (cron)", run="0 1 * * *  scripts/lcodb_daily.sh  →  python -m ava.lcodb daily",
        when="daily 01:00 UTC, ~11 min; log <db_dir>/daily.log",
        what="Updates the LCO archive tables, in order: sync (new frames of the AVA proposals, flux standards, FLOYDS "
             "calibrations), headers (slit width APERWID of new spectra only, since 2021-09-01), airmass, match "
             "(each spectrum's flux standard, arc and flat), link (LCO names → AVA targets, observing flag agn.ava), "
             "stats (tools/ava_crossmatch.py → agn_lco, after a backup).",
        reads=["LCO archive", "ava.db agn (names)"],
        writes=["photometry.sqlite frames, target_link", "spectra.sqlite frames, headers, std_match, calib_match",
                "state.sqlite sync_state, runs", "ava.db agn_lco, agn.ava"],
        rel=["ext_archive", "db_phot", "db_spec", "db_state", "db_ava", "f_backup"]),
    "job_pipeline": dict(
        kind="Scheduled jobs 2 + 3 (Prefect)", run="scripts/deploy.py --cron \"0 2 * * *\" -d -e -c -t -p -D -R -P -w  "
        "(Prefect server + worker as systemd services); or the plain cron line in linux_setup §17: "
        "scripts/run_pipeline.py -d -e -c -t -p -D -R -P -w",
        when="daily 02:00 UTC, after job 1",
        what="Flow ava_pipeline (ava/pipeline/flows.py). Each target runs ava_target_flow with the photometry steps "
             "then the spectroscopy steps, in that order; targets run in parallel (pipeline.n_cores). The publish "
             "step -w runs once after all targets. Each step skips work already done (catalogue exists, frame_qc at "
             "the current version, night already reduced).",
        reads=["all stores"], writes=["all stores"],
        rel=["st_d", "st_e", "st_c", "st_t", "st_p", "st_D", "st_R", "st_P", "st_w", "job_lcodb"]),
    "st_d": dict(
        kind="Pipeline step -d", run="ava/pipeline/tasks/download.py → ava/lco/download.py", when="job 2, 02:00",
        what="Searches the live archive per target (every LCO spelling, download.daily_proposals, level 91) from the "
             "last successful date minus overlap_days (2). Fetches a frame only if it is not on disk and has no "
             "catalogue yet; md5-checked. download.mode: dry_run in the repository, live in production.",
        reads=["LCO archive", "ava.db download_state", "catalogues (already processed?)"],
        writes=["raw_data/<id>/YYYYMMDD/*.fits.fz", "photometry.sqlite local_files", "ava.db download_state"],
        rel=["ext_archive", "f_raw", "db_phot", "db_ava", "f_cat"]),
    "st_e": dict(
        kind="Pipeline step -e", run="ava/pipeline/tasks/sextract.py (source-extractor binary)", when="job 3",
        what="SExtractor catalogue for every raw image without one (versioned configuration in data/reference/"
             "sextractor/, 16 apertures). Catalogues are kept forever; images are not.",
        reads=["raw images"], writes=["sextractor_ava/<frame>_cat.fits"], rel=["f_raw", "f_cat", "f_conf"]),
    "st_c": dict(
        kind="Pipeline step -c", run="ava/pipeline/tasks/calibrate.py (ava.photometry.process, .calibration)",
        when="job 3",
        what="Per-frame zero point against the Gaia reference stars, AGN magnitude and frame QC. Frame metadata "
             "comes from the image header, or from frame_qc once the image is gone, or (ported legacy catalogues) "
             "from the lcodb listing plus camera_defaults. Skips frames already at the current version.",
        reads=["catalogues", "raw image header", "reference_stars.csv", "photometry.sqlite frames"],
        writes=["photometry.sqlite frame_qc", "measurements.parquet", "AGN light curve"],
        rel=["f_cat", "f_raw", "db_phot", "f_phot"]),
    "st_t": dict(
        kind="Pipeline step -t", run="ava/pipeline/tasks/ensemble.py (PyTICS); --pytics-full refits", when="job 3",
        what="Ensemble intercalibration of all cameras and filters. Daily runs add only the new frames to the stored "
             "solution. Writes the merged AGN light curve and the per-band fractional variability.",
        reads=["frame_qc", "measurements.parquet"],
        writes=["pytics/", "agn_lightcurve_pytics.parquet", "<id>_LCO_merged_lightcurve.csv",
                "ava.db photometry_variability, agn.frac_<band>"],
        rel=["db_phot", "f_phot", "db_ava"]),
    "st_p": dict(
        kind="Pipeline step -p", run="ava/pipeline/tasks/webplot.py (ava.plots.webplots)", when="job 3",
        what="Website figures per target: full, last-6-months and season light curves, sky/seeing/zero-point "
             "diagnostics, field-star RMS, Swift; FLOYDS epochs marked.",
        reads=["frame_qc", "measurements.parquet", "spectra.sqlite (epochs)"],
        writes=["<phot>/<id>/plots/lco_latest_*.png/.pdf"], rel=["db_phot", "f_phot", "db_spec", "f_plots"]),
    "st_D": dict(
        kind="Pipeline step -D", run="ava/pipeline/tasks/spec_download.py (ava.spectroscopy.download)", when="job 2",
        what="Planned offline from spectra.sqlite (so job 1 must run first): each new night's science spectra, arc "
             "and lamp flat, plus the night's flux standard with its own arc and flat. Only missing files are "
             "fetched. spectroscopy.download.mode: dry_run in the repository, live in production.",
        reads=["spectra.sqlite frames, std_match, calib_match", "ava.db download_state"],
        writes=["spectroscopy/raw_data/<id>/YYYYMMDD/", "raw_data/standards/", "ava.db download_state",
                "local_files"],
        rel=["db_spec", "ext_archive", "f_raw", "db_ava"]),
    "st_R": dict(
        kind="Pipeline step -R", run="ava/pipeline/tasks/spec_reduce.py → banzai-floyds fork (own environment)",
        when="job 3",
        what="Reduces nights that have raw science frames and no reduced -1d yet, with the improved banzai-floyds "
             "(commit recorded in every product). QC keywords go to the spectra database.",
        reads=["raw FLOYDS nights + standards", "sky flats"],
        writes=["<spec>/<id>/reduced/YYYYMMDD/*-e91-1d/-2d", "spectra.sqlite spec_qc"],
        rel=["f_raw", "f_spec", "db_spec"]),
    "st_P": dict(
        kind="Pipeline step -P", run="ava/pipeline/tasks/spec_products.py", when="job 3",
        what="Latest spectrum, Hβ-region fit, [O III]-calibrated mean and RMS spectra, broad-Hβ and 5100 Å light "
             "curves, PrepSpec input.",
        reads=["reduced -1d spectra"],
        writes=["hbeta_fits.parquet", "spectra.sqlite spec_lines", "ava.db line_variability",
                "<id>_FLOYDS_Hbeta_lightcurve.csv", "prepspec/", "plots"],
        rel=["f_spec", "db_spec", "db_ava", "f_plots"]),
    "st_w": dict(
        kind="Pipeline step -w", run="ava/pipeline/tasks/publish_web.py → ava/web/publish.py, ava/web/releases.py",
        when="end of job 3, once after all targets",
        what="Refreshes derived properties (agn_derived), the observing flag (agn.ava) and F_var, then copies to "
             "web.data_dir a consistent snapshot of ava.db, changed plots, usage plots (web.usage_src), manuals, "
             "filter curves, per-target downloads and the public data-release files. Atomic writes; a snapshot "
             "with no AGN is refused.",
        reads=["ava.db", "plots", "data/lco_usage/plots", "docs/manuals/*.pdf", "releases/"],
        writes=["ava.db agn_derived, agn.ava, photometry_variability", "web.data_dir/*"],
        rel=["db_ava", "f_plots", "f_usage", "f_rel", "f_phot", "f_spec", "web_data"]),
    "job_cleanup": dict(
        kind="Scheduled job 4 (cron)", run="0 5 * * *  scripts/cleanup.py --live  (ava/archive/cleanup.py)",
        when="daily 05:00 UTC; dry run unless --live or cleanup.mode: live",
        what="Deletes raw frames AVA has finished with, older than retention_days (7, must exceed overlap_days). "
             "Photometry image: catalogue exists and frame_qc row at the current version. FLOYDS night: every "
             "spectrum has its -1d, a spec_qc row and is in hbeta_fits.parquet. Standard night: no target night "
             "still needs it.",
        reads=["catalogues", "frame_qc", "spec_qc", "hbeta_fits.parquet"],
        writes=["deletes raw_data/…", "local_files.deleted_utc"],
        rel=["f_raw", "f_cat", "db_phot", "db_spec", "f_spec"]),
    "job_usage": dict(
        kind="Scheduled job 6 (cron)", run="0 */6 * * *  scripts/lco_usage.py --live-snapshot  (ava/lco/usage.py)",
        when="every 6 h, ~15 s",
        what="Snapshot of LCO's charged totals, then daily curves (estimated from the lcodb databases with a fitted "
             "overhead model, scaled to the charged totals) and the current semester's plot. Changed plots are "
             "copied to <web.data_dir>/usage/ for the Live Updates page. Live only on the VM; dry run elsewhere.",
        reads=["observation portal", "photometry.sqlite", "spectra.sqlite", "snapshots.csv"],
        writes=["data/lco_usage/snapshots.csv (append)", "estimated/overheads.txt", "plots/lco_usage_<sem>.png",
                "web.data_dir/usage/"],
        rel=["ext_portal", "db_phot", "db_spec", "f_usage", "web_data"]),
    "job_backup": dict(
        kind="Scheduled job 5 — TO BUILD", run="(none yet)", when="weekly off-VM copy; databases daily",
        what="Planned: sqlite3 \".backup\" of ava.db and the lcodb databases, plus catalogues, measurements, reduced "
             "spectra and releases/ (~0.25 TB) to an off-VM store.",
        reads=["all databases and products", "data/lco_usage/snapshots.csv (no longer in git after install)"],
        writes=["off-VM store"],
        rel=["db_ava", "db_phot", "db_spec", "db_state", "f_cat", "f_phot", "f_spec", "f_rel", "f_usage", "offvm"]),
    "db_phot": dict(
        kind="Database (lcodb)", run="<db_dir>/photometry.sqlite (lcodb_config.yaml db_dir); ~440 MB",
        when="written daily", what="Every LCO imaging frame of the AVA proposals, links to AVA targets, the "
        "downloaded-file registry and frame_qc (per-frame QC, zero points and the header values calibration "
        "needs, so a frame can be recalibrated after its image is deleted). Not in git: copied by hand.",
        reads=[], writes=[], rel=["job_lcodb", "st_d", "st_c", "st_t", "st_p", "job_cleanup", "job_usage", "mac"]),
    "db_spec": dict(
        kind="Database (lcodb)", run="<db_dir>/spectra.sqlite; ~250 MB", when="written daily",
        what="FLOYDS frames and headers, standard-star and arc/flat matches, spec_qc (reduction QC) and spec_lines "
             "(per-exposure line fits). The spectroscopy download is planned from it. Not in git: copied by hand.",
        reads=[], writes=[], rel=["job_lcodb", "st_D", "st_R", "st_P", "st_p", "job_cleanup", "job_usage", "mac"]),
    "db_state": dict(
        kind="Database (lcodb)", run="<db_dir>/state.sqlite", when="written daily by job 1",
        what="Per-proposal crawl state and run log of lcodb. Not in git: copied by hand.",
        reads=[], writes=[], rel=["job_lcodb", "mac"]),
    "db_ava": dict(
        kind="Database (AVA)", run="paths.database (data/ava.db)", when="written daily and by the curation tools",
        what="The source of truth for the AGN targets (agn), their LCO statistics (agn_lco), literature values "
             "(agn_literature), derived properties (agn_derived), photometric and line variability, download state "
             "and the data releases (data_releases, agn_releases, release_files). Curated writes go through tools/ "
             "scripts that back up first. Not in git (the pipeline writes it): copied by hand once.",
        reads=[], writes=[], rel=["job_lcodb", "st_d", "st_D", "st_t", "st_P", "st_w", "od_add", "od_lit",
                                  "od_derive", "od_migrate", "od_release", "od_nh", "web_data", "mac", "f_backup"]),
    "f_raw": dict(
        kind="Files — temporary", run="<archive_root>/photometry/raw_data/<id>/YYYYMMDD/, spectroscopy/raw_data/…",
        when="written at 02:00, deleted at 05:00 once processed (after retention_days)",
        what="Downloaded images and FLOYDS nights (science, arcs, flats, standards). Rolling buffer ~55 GB. Each "
             "deletion is marked in local_files (path and md5 kept).",
        reads=[], writes=[], rel=["st_d", "st_D", "st_e", "st_c", "st_R", "job_cleanup", "od_backfill", "od_port"]),
    "f_cat": dict(
        kind="Files — kept", run="<phot>/<id>/sextractor_ava/<frame>_cat.fits", when="written by -e",
        what="SExtractor catalogues: kept forever (~55 GB now, 8 GB/year). They mark a frame as processed.",
        reads=[], writes=[], rel=["st_e", "st_c", "job_cleanup", "od_port", "st_d"]),
    "f_phot": dict(
        kind="Files — kept (Parquet)", run="<phot>/<id>/measurements.parquet, agn light curve, pytics/",
        when="written by -c and -t",
        what="Calibrated measurements of every star and the AGN per frame, the AGN light curve, PyTICS solutions "
             "and the merged light curve (published as a download).",
        reads=[], writes=[], rel=["st_c", "st_t", "st_p", "st_w"]),
    "f_spec": dict(
        kind="Files — kept", run="<spec>/<id>/reduced/YYYYMMDD/, hbeta_fits.parquet, prepspec/",
        when="written by -R and -P",
        what="Reduced 1-d and 2-d spectra (~90 GB), the Hβ/[O III] fits and line light curves, PrepSpec input.",
        reads=[], writes=[], rel=["st_R", "st_P", "job_cleanup", "st_w"]),
    "f_plots": dict(
        kind="Files — kept", run="cfg.target_plots_dir: <phot>/<id>/plots/lco_latest_*", when="written by -p and -P",
        what="Per-target website figures; -w copies the changed ones to web.data_dir/plots/<id>/.",
        reads=[], writes=[], rel=["st_p", "st_P", "st_w"]),
    "f_rel": dict(
        kind="Files — kept", run="releases.dir/<DR>/release.yaml + <id>/[<kind>/]<files>",
        when="prepared by hand; published by -w",
        what="Frozen data-release files. tools/register_release.py records them in ava.db; -w copies the public "
             "ones once release_date has passed.",
        reads=[], writes=[], rel=["od_release", "st_w"]),
    "f_usage": dict(
        kind="Files — VM-local (seeded from git)", run="data/lco_usage/: snapshots.csv, allocations.json, estimated/, plots/",
        when="appended every 6 h by job 6",
        what="The log of LCO's charged totals (append only, on the VM only) and the usage plots. snapshots.csv "
             "arrives with the clone as a one-time seed; after that the VM updates it locally and never pushes it "
             "back to GitHub, so it should be in the backups.",
        reads=[], writes=[], rel=["job_usage", "st_w", "github", "job_backup"]),
    "f_lit": dict(
        kind="Files — in git", run="data/literature/agn_properties.csv, references.csv, mass_conflicts.csv",
        when="rebuilt by hand",
        what="One row per AGN with its published properties and bibcodes; the input of tools/import_literature.py.",
        reads=[], writes=[], rel=["ext_lit", "od_lit", "github"]),
    "f_conf": dict(
        kind="Files — in git", run="config/ava_config.yaml, lcodb_config.yaml, targets.yaml; data/reference/",
        when="read by every job",
        what="Every path and setting (AVA_CONFIG / LCODB_CONFIG point to the VM's copies), SExtractor "
             "configuration, filter dictionary and curves.",
        reads=[], writes=[], rel=["github", "st_e"]),
    "f_backup": dict(
        kind="Files", run="data/backups/, <db dir>/backups/",
        when="before every curated write", what="Automatic copies of ava.db made by the tools/ scripts and by "
        "lcodb stats before they write.",
        reads=[], writes=[], rel=["db_ava", "job_lcodb", "od_lit", "od_add"]),
    "od_init": dict(
        kind="On demand — setup", run="scripts/run_pipeline.py -o -O", when="once per target (setup step 11)",
        what="-o creates the photometry folders and builds reference_stars.csv from Gaia DR3 GSPC; -O creates the "
             "FLOYDS folders and summarises the target's spectra from spectra.sqlite.",
        reads=["Gaia", "ava.db agn", "spectra.sqlite"], writes=["folders", "reference_stars.csv"],
        rel=["ext_gaia", "db_ava", "db_spec", "f_phot"]),
    "od_port": dict(
        kind="On demand — setup", run="tools/port_legacy.py [--write] [--link]", when="once, during the backfill",
        what="Copies the old pipeline's SExtractor catalogues and raw FLOYDS frames into the new layout, placing "
             "each file by its frame name through the lcodb databases. Dry run by default. Then -c calibrates the "
             "ported catalogues without images.",
        reads=["old pipeline folders", "photometry.sqlite", "spectra.sqlite"], writes=["catalogues", "raw FLOYDS"],
        rel=["legacy", "f_cat", "f_raw", "db_phot", "db_spec"]),
    "od_status": dict(
        kind="On demand — setup", run="tools/backfill_status.py [--target …] [--apertures N]", when="any time",
        what="Per target: frames still to download / extract / calibrate, spectra to download / reduce. Offline.",
        reads=["lcodb databases", "files on disk"], writes=[], rel=["db_phot", "db_spec", "f_cat", "f_raw"]),
    "od_backfill": dict(
        kind="On demand — setup", run="scripts/download.py … --live, then run_pipeline.py -e -c",
        when="once, in batches",
        what="Whole-history download for one target, in batches that fit the scratch volume (download → catalogue "
             "→ calibrate → delete). Skips frames that already have a catalogue.",
        reads=["LCO archive"], writes=["raw images"], rel=["ext_archive", "f_raw", "f_cat"]),
    "od_check": dict(
        kind="On demand — setup", run="scripts/check_install.py [--tests]", when="after install or upgrade",
        what="Checks package versions, config paths, LCO token, databases, the SExtractor binary and a test run, "
             "banzai-floyds and (--tests) the offline test suite.",
        reads=["config", "databases"], writes=[], rel=["f_conf", "db_ava", "db_phot", "db_spec"]),
    "od_add": dict(
        kind="On demand — targets", run="tools/add_ava_targets.py tools/new_targets/<date>.yaml [--write]",
        when="when new AGN join AVA",
        what="Resolves each new target (SIMBAD via Sesame, NED, Gaia DR3 nucleus, extinction, N_H) and inserts it "
             "into agn after a backup. Then: lcodb link, -o -O, literature.",
        reads=["SIMBAD, NED, IRSA, Gaia"], writes=["ava.db agn"],
        rel=["ext_resolvers", "ext_gaia", "db_ava", "f_backup"]),
    "od_xmatch": dict(
        kind="On demand — targets", run="tools/target_list_crossmatch.py", when="when a target list arrives",
        what="Cross-matches a supplied list against AVA by name and position; checks coordinates of new entries "
             "with Sesame and Gaia. Opens ava.db read-only.",
        reads=["ava.db", "Sesame", "Gaia"], writes=["report"], rel=["db_ava", "ext_resolvers", "ext_gaia"]),
    "od_lit": dict(
        kind="On demand — literature", run="tools/import_literature.py --apply-to-agn --write",
        when="after the literature CSV changes",
        what="Upserts data/literature/agn_properties.csv into agn_literature and copies z, log M_BH, log L5100 and "
             "type with their citations into the agn columns the website shows. Dry run by default.",
        reads=["data/literature/*.csv"], writes=["ava.db agn_literature, agn"],
        rel=["f_lit", "db_ava", "f_backup", "ext_lit"]),
    "od_derive": dict(
        kind="On demand — literature", run="tools/derive_agn_properties.py", when="after new AGN or new masses",
        what="k_bol, L_bol, Eddington ratio and thin-disc lags. The -w step runs the same code daily.",
        reads=["ava.db agn"], writes=["ava.db agn_derived"], rel=["db_ava", "st_w"]),
    "od_migrate": dict(
        kind="On demand — curation", run="tools/db_migrate_YYYYMMDD.py [--write]", when="one-off",
        what="Identity fixes (position, data_id rename). A rename also updates the lcodb links.",
        reads=[], writes=["ava.db", "lcodb target links"], rel=["db_ava", "db_phot", "db_spec"]),
    "od_release": dict(
        kind="On demand — releases", run="tools/register_release.py DR1 [--write] [--withhold …]",
        when="when a data release is prepared",
        what="Reads releases/<DR>/release.yaml and its files and writes data_releases, agn_releases and "
             "release_files. The site links them after release_date and the next -w.",
        reads=["releases/<DR>/"], writes=["ava.db release tables"], rel=["f_rel", "db_ava", "st_w"]),
    "od_publish": dict(
        kind="On demand — website", run="tools/publish_web.py [--dry-run] [--target …]", when="any time",
        what="The -w copy step by hand (from the web section of the config).",
        reads=["ava.db", "plots"], writes=["web.data_dir"], rel=["web_data", "db_ava", "f_plots"]),
    "od_usage_all": dict(
        kind="On demand — website", run="scripts/lco_usage.py --all", when="once after installing",
        what="Redraws the usage plot of every semester (no LCO request without --live-snapshot).",
        reads=["lcodb", "snapshots.csv"], writes=["usage plots", "web.data_dir/usage/"],
        rel=["f_usage", "web_data", "db_phot", "db_spec"]),
    "od_nh": dict(
        kind="On demand — curation", run="tools/import_nh.py --apply", when="one-off backfill",
        what="Galactic N_H (HI4PI, HEASARC) for AGN that have none.",
        reads=["HEASARC"], writes=["ava.db agn.nh"], rel=["ext_resolvers", "db_ava"]),
    "od_assets": dict(
        kind="On demand — website", run="tools/build_web_assets.py", when="when posters or logos change",
        what="Builds the site's static images (web/assets/) from files in the repository.",
        reads=["poster/, docs/figures/"], writes=["web/assets/"], rel=["web_php"]),
    "web_data": dict(
        kind="Website data (copy)", run="web.data_dir (AVA_WEB_DATA, AVA_WEB_DATA_URL)",
        when="rewritten by -w (daily) and by job 6 (usage/)",
        what="The website's own copy of everything it shows; it never reads pipeline paths. The .htaccess written "
             "by publish denies *.db, *.sqlite, filter_dict.txt and site.json and turns off directory listings: "
             "plots, manuals, filter curves, downloads and released files are public, the database is not. The "
             "web server only needs read access.",
        reads=[], writes=[], rel=["st_w", "job_usage", "web_php", "od_publish", "od_usage_all", "db_ava"]),
    "web_php": dict(
        kind="Website", run="web/*.php, web/includes/, web/assets/ (Apache 2.4 + PHP 8.1, pdo_sqlite)",
        when="on each request",
        what="Plain PHP pages: index, targets, target, data, science, publications, live (Live Updates: usage "
             "plots of the 2020B/2023B/2026B key projects and every semester), about (manuals). They read the "
             "ava.db snapshot server-side and link to the published plots and files.",
        reads=["web.data_dir"], writes=[], rel=["web_data", "web_public", "od_assets"]),
    "web_public": dict(
        kind="Public", run="Apache virtual host, DocumentRoot = web/", when="—",
        what="Visitors see the PHP pages, plots, manuals and released data; never the database file. Hosting, "
             "domain and HTTPS certificate are still to arrange (guide §8).",
        reads=[], writes=[], rel=["web_php"]),
    "legacy": dict(
        kind="Outside the VM", run="old pipeline folders (e.g. /data3/…/agn, /data2/…/agn)", when="read once",
        what="The old pipeline's catalogues (80–90 % of the photometry) and raw FLOYDS frames, ported so they need "
             "not be downloaded again.",
        reads=[], writes=[], rel=["od_port"]),
    "github": dict(
        kind="Outside the VM", run="git@github.com:Alymantara/AVA---AGN-Variability-Archive.git",
        when="clone at setup; pull to update (the VM never pushes)",
        what="Code, config, small reference data (data/reference/, data/literature/*.csv, data/ava/ava.csv, "
             "ava_link_overrides.csv), the manuals' PDFs, and data/lco_usage/snapshots.csv as a one-time seed for the first deployment. Not in git: ava.db (the "
             "pipeline writes it), data/lcodb/ (440 + 250 MB, above GitHub's limit) and the archive data.",
        reads=[], writes=[], rel=["f_usage", "f_lit", "f_conf"]),
    "mac": dict(
        kind="Outside the VM", run="/Users/juan/astro/AVA", when="development",
        what="Where the code is written and tested against data/test_archive, with dry-run defaults and no live "
             "LCO requests. The production ava.db and lcodb databases are copied from here once (sqlite3 .backup, "
             "then scp; linux_setup.md step 7). The manuals are written here (.tex) and their PDFs committed.",
        reads=[], writes=[], rel=["db_ava", "db_phot", "db_spec", "db_state", "github"]),
    "offvm": dict(
        kind="TO BUILD", run="(to choose)", when="weekly; databases daily",
        what="Off-VM copies of the databases, catalogues, measurements, reduced spectra and releases (~0.25 TB).",
        reads=[], writes=[], rel=["job_backup"]),
}


def title_of(i: str) -> str:
    kind, lines = NODES[i][0], NODES[i][5]
    return f"{lines[1][0]} ({lines[0][0]})" if kind == "step" else lines[0][0]


# --------------------------------------------------------------------------------------------------
# SVG
# --------------------------------------------------------------------------------------------------
def _attrs(mode: str, fill: str | None = None, stroke: str | None = None, extra: str = "") -> str:
    if mode == "static":
        return (f' fill="{fill}"' if fill else ' fill="none"') + (f' stroke="{stroke}"' if stroke else "") + extra
    s = []
    s.append(f"fill:{fill}" if fill else "fill:none")
    if stroke:
        s.append(f"stroke:{stroke}")
    return f' style="{";".join(s)}"' + extra


def text(mode, x, y, s, size=11, weight=400, color="fg", family=SANS, anchor="start", cls=""):
    c = T(mode, color)
    fill = f' fill="{c}"' if mode == "static" else f' style="fill:{c}"'
    k = f' class="{cls}"' if cls and mode != "static" else ""
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
            f'text-anchor="{anchor}"{fill}{k}>{escape(s)}</text>')


def region(mode, x, y, w, h, key, label, sub=""):
    fill, stroke = STATIC_TEXT[key] if mode == "static" else (f"var(--{key}-fill)", f"var(--{key}-stroke)")
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10"{_attrs(mode, fill, stroke)} stroke-width="1.5"/>',
           text(mode, x + 14, y + 20, label, 12, 700, "fg", SANS)]
    if sub:
        out.append(text(mode, x + w - 14, y + 20, sub, 10, 400, "sub", SANS, "end"))
    return out


def render_node(mode, i):
    kind, x, y, w, h, lines = NODES[i]
    fill, stroke, dash = C(mode, kind)
    d = f' stroke-dasharray="{dash}"' if dash else ""
    sw = "1.6" if kind in ("job", "tobuild") else "1.2"
    rx = 8 if kind not in ("db",) else 4
    g = [f'<g id="n-{i}" class="node k-{kind}" data-id="{i}" tabindex="0" role="button" '
         f'aria-label="{escape(title_of(i))}">' if mode != "static" else f'<g id="n-{i}">',
         f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"{_attrs(mode, fill, stroke)} stroke-width="{sw}"{d}/>']
    if kind == "db":   # cylinder cue: a second line under the top edge
        g.append(f'<path d="M{x} {y + 7} Q{x + w / 2} {y + 13} {x + w} {y + 7}"{_attrs(mode, None, stroke)} '
                 f'stroke-width="1"/>')
    chip = kind == "step"
    cx = x + (w / 2 if chip else 12)
    anchor = "middle" if chip else "start"
    yy = y + (16 if chip else (20 if kind != "db" else 23))
    for s, st in lines:
        if st == "f":
            g.append(text(mode, cx, yy, s, 11.5, 700, "fg", MONO, anchor))
            yy += 14
        elif st == "t":
            g.append(text(mode, cx, yy, s, 11.5 if chip else 12.5, 600, "fg", SANS, anchor))
            yy += 14 if chip else 15
        elif st == "m":
            g.append(text(mode, cx, yy, s, 9 if chip else (9.5 if kind == "ondemand" else 10), 400, "sub", MONO, anchor))
            yy += 13
        else:
            g.append(text(mode, cx, yy, s, 10.5, 400, "sub", SANS, anchor))
            yy += 13.5
    if i == "web_data":
        ry = y + 58
        for path, tag, note in DATA_ROWS:
            g.append(text(mode, x + 12, ry, path, 10, 400, "fg", MONO))
            g.append(text(mode, x + w - 12, ry, tag.upper(), 9, 700, tag, SANS, "end"))
            if note:
                g.append(text(mode, x + 12, ry + 12, note, 9.5, 400, "sub", SANS))
            ry += 30
    g.append("</g>")
    return g


def render_arrow(mode, pts, label, lxy, anchor, dashed, head=True):
    col = T(mode, "arrow")
    p = " ".join(f"{a},{b}" for a, b in pts)
    d = ' stroke-dasharray="4 3"' if dashed else ""
    st = f' stroke="{col}" fill="none"' if mode == "static" else f' style="stroke:{col};fill:none"'
    mk = ' marker-end="url(#ah)"' if head else ""
    out = [f'<polyline points="{p}"{st} stroke-width="1.4"{d}{mk}/>']
    if label:
        out.append(text(mode, lxy[0], lxy[1], label, 10, 500, "arrow", SANS, anchor))
    return out


def svg(mode: str) -> str:
    col = T(mode, "arrow")
    mfill = f'fill="{col}"' if mode == "static" else f'style="fill:{col}"'
    y0 = 0 if mode == "static" else 76
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 {y0} {W} {H - y0}" width="{W}" height="{H - y0}" '
         f'role="img" aria-label="AVA pipeline: external sources, scheduled jobs, on-demand tools, data stores, '
         f'deployment boundaries and the website" id="ava-diagram">',
         f'<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
         f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" {mfill}/></marker></defs>']
    if mode == "static":
        o.append(f'<rect width="{W}" height="{H}" fill="{STATIC_TEXT["bg"]}"/>')
        o.append(text(mode, 28, 38, "AVA pipeline — data flow and deployment", 20, 700))
        o.append(text(mode, 28, 60, f"AGN Variability Archive · times UTC · {DATE} · "
                      "generated by tools/make_pipeline_diagram.py", 11, 400, "sub"))
    o += region(mode, 16, 84, 244, 540, "r_ext", "External services", "HTTPS out")
    o += region(mode, 276, 84, 1060, 850, "r_vm", "Production Linux VM", "cron + Prefect · service user ava")
    o += region(mode, 1352, 84, 312, 616, "r_web", "Website", "same VM or rsync'd host")
    # section labels in the VM
    for y, s in ((444, "Data stores"),
                 (734, "On demand, by hand: setup and backfill · targets and literature · releases and website")):
        o.append(text(mode, 292, y, s, 10.5, 700, "sub", SANS).replace('font-weight="700"', 'font-weight="700" '
                                                                         'letter-spacing="0.6"'))
    o.append(text(mode, 448, 104, "scheduled jobs (cron, UTC) · data stores · on-demand tools", 10, 400, "sub"))
    o.append(text(mode, 500, 322, "per target, photometry then spectroscopy; targets in parallel (pipeline.n_cores); "
                  "-w once at the end", 10, 400, "sub"))
    o.append(text(mode, 838, 380, "usage plots also copied to web.data_dir/usage/ every 6 h", 10, 400, "sub"))
    o.append(text(mode, 28, 566, "reference stars, names and literature", 10, 400, "sub"))
    o.append(text(mode, 28, 580, "feed the on-demand tools ↘", 10, 400, "sub"))
    for i in NODES:
        o += render_node(mode, i)
    for a in ARROWS:
        o += render_arrow(mode, *a)
    o += legend(mode, 1352, 716)
    o.append("</svg>")
    return "\n".join(o)


def legend(mode, x, y):
    o = [text(mode, x + 4, y + 12, "Key", 10.5, 700, "sub")]
    items = [("job", "scheduled job"), ("step", "pipeline step (flag)"), ("ondemand", "on demand, by hand"),
             ("db", "SQLite database"), ("file", "files, kept"), ("temp", "files, temporary"),
             ("ext", "external service"), ("web", "website"), ("tobuild", "to build")]
    for k, (kind, lab) in enumerate(items):
        cx, cy = x + 4 + (k % 2) * 156, y + 24 + (k // 2) * 22
        fill, stroke, dash = C(mode, kind)
        d = f' stroke-dasharray="{dash}"' if dash else ""
        o.append(f'<rect x="{cx}" y="{cy}" width="22" height="14" rx="3"{_attrs(mode, fill, stroke)} '
                 f'stroke-width="1.2"{d}/>')
        o.append(text(mode, cx + 30, cy + 11, lab, 10, 400, "fg"))
    return o


# --------------------------------------------------------------------------------------------------
# HTML page
# --------------------------------------------------------------------------------------------------
def html() -> str:
    details = {i: {**d, "title": title_of(i)} for i, d in D.items()}
    missing = set(NODES) - set(D)
    assert not missing, f"no details for {missing}"
    tpl = (Path(__file__).with_name("pipeline_diagram_template.html")).read_text()
    return tpl.replace("%%SVG%%", svg("web")).replace("%%DETAILS%%", json.dumps(details, ensure_ascii=False)) \
              .replace("%%DATE%%", DATE)


if __name__ == "__main__":
    OUT_SVG.write_text(svg("static") + "\n")
    OUT_HTML.write_text(html())
    print(f"wrote {OUT_SVG.relative_to(ROOT)} and {OUT_HTML.relative_to(ROOT)}")
