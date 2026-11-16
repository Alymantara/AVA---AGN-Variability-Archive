"""
Spectroscopy reduce task — run the improved banzai-floyds on a target's downloaded nights.

See :mod:`ava.spectroscopy.reduce`.  Settings: ``spectroscopy.reduction`` (environment, sky flats,
workers).  Nights: those given (re-reduced), else only the nights with raw science frames that have no reduced
-1d yet — so the daily ``-D -R -P`` processes new spectra only.

Outputs:
  <spec_root>/<target>/reduced/<YYYYMMDD>/*-e91-1d/-2d   our science products
  <spec_root>/<work>/processed/...                        shared calibrations + standards
  <spec_root>/<work>/floyds.db                            banzai-floyds calibration DB
  <spec_root>/<work>/logs/<target>.log                    the reduction log
  lcodb spectra DB, table spec_qc                          QC keywords, one row per raw spectrum
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from prefect import get_run_logger, task

from ava.config import cfg


def reduction_settings() -> dict:
    r = cfg._raw.get("spectroscopy", {}).get("reduction", {}) or {}
    work = Path(r.get("work_dir", "banzai"))
    return dict(python=r.get("python"), package=r.get("package"), skyflats_dir=r.get("skyflats_dir"),
                work=work if work.is_absolute() else cfg.spec_root / work, workers=int(r.get("workers", 4)),
                window_days=float(r.get("window_days", 60)), keep_2d=bool(r.get("keep_2d", True)),
                cleanup=dict(r.get("cleanup") or {}))


def pending_nights(target_raw: Path, reduced: Path) -> list[str]:
    """Nights (YYYYMMDD) with at least one raw science frame (e00) without its reduced -1d in ``reduced``."""
    out = []
    for d in sorted(target_raw.glob("20??????")):
        for f in d.glob("*-e00.fits*"):
            stem = f.name.split(".fits")[0].replace("-e00", "-e91-1d")
            if not any((reduced / d.name).glob(f"{stem}.fits*")):
                out.append(d.name)
                break
    return out


@task(name="spec-reduce", tags=["spectroscopy", "reduction", "banzai-floyds"])
def spec_reduce(target: str, nights: list[str] | None = None) -> dict:
    """Reduce ``target``'s downloaded FLOYDS nights with the improved banzai-floyds; QC → spectra DB."""
    from ava.pipeline.tasks.download import lcodb_path
    from ava.spectroscopy import reduce as R

    logger = get_run_logger()
    s = reduction_settings()
    if not s["python"] or not Path(s["python"]).exists():
        raise RuntimeError(f"spectroscopy.reduction.python not found: {s['python']!r}")
    entry = cfg.target_by_data_id(target)
    if entry is None:
        raise ValueError(f"{target!r} is not a known data_id")
    target_raw, std_raw = cfg.spec_raw(target), cfg.spec_raw(target).parent / "standards"
    if not nights:   # incremental: only nights with raw science frames that have no reduced -1d yet
        nights = pending_nights(target_raw, cfg.spec_dir(target) / "reduced")
    nights = [n.replace("-", "") for n in nights]
    if not nights:
        logger.info("%s: nothing to reduce (every downloaded science frame in %s has a -1d)", target, target_raw)
        return {"target": target, "nights": [], "reduced": 0}
    work, db = s["work"], s["work"] / "floyds.db"
    processed, log = work / "processed", work / "logs" / f"{target}.log"
    version = R.pipeline_version(s["package"])
    if R.ensure_calibration_db(s["python"], db, Path(s["skyflats_dir"]), processed, work / "logs" / "setup.log"):
        logger.info("created calibration DB %s (sites, standards, sky flats from %s)", db, s["skyflats_dir"])
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    staged = R.stage(nights, target_raw, std_raw, work / "input" / f"{target}_{run_id}")
    logger.info("%s: %d night(s) %s, %d raw frames staged; banzai-floyds %s", target, len(nights), nights,
                len(staged), version)
    n0 = len(log.read_text().splitlines()) if log.exists() else 0
    rc = R.offline(s["python"], ["chain", "--db-address", f"sqlite:///{db}", "--raw-dir", str(staged[0].parent),
                                 "--processed-dir", str(processed), "--workers", str(s["workers"]),
                                 "--window-days", str(s["window_days"])], log)
    status = R.parse_chain_log(log, n0)
    errors = {k: v for k, v in status.items() if v != "ok"}
    for k, v in list(errors.items())[:10]:
        logger.warning("  %s: %s", k, v)

    # file the products and collect QC
    spec_db = lcodb_path("spec")
    with closing(sqlite3.connect(f"file:{spec_db}?mode=ro", uri=True)) as con:
        ids = dict(con.execute("SELECT basename, id FROM frames WHERE rlevel=0 AND basename IN (%s)" % ",".join(
            "?" * len(staged)), [p.name.split(".fits")[0] for p in staged]).fetchall())
        is_std = dict(con.execute("SELECT basename, COALESCE(is_standard,0) FROM frames WHERE rlevel=0 AND basename "
                                  "IN (%s)" % ",".join("?" * len(staged)), [p.name.split(".fits")[0] for p in staged]))
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows, moved, missing = [], 0, []
    for p in staged:
        if "-e00" not in p.name:
            continue
        base = p.name.split(".fits")[0]
        prod = R.products_of(processed, p.name)
        if prod["1d"] is None:
            missing.append(base)
            continue
        role = "standard" if is_std.get(base) else "science"
        night = base.split("-")[2]
        if role == "science":           # science → the target's folder; standards stay with the calibrations
            dest = cfg.spec_dir(target) / "reduced" / night
            dest.mkdir(parents=True, exist_ok=True)
            for k in ("1d", "2d"):
                if prod[k] is not None:
                    if k == "2d" and not s["keep_2d"]:
                        prod[k].unlink()
                        prod[k] = None
                        continue
                    new = dest / prod[k].name
                    prod[k].replace(new)
                    prod[k] = new
                    moved += 1
        qc = R.read_qc(prod["1d"])
        rows.append(dict(frame_id=ids.get(base), basename=base, data_id=target if role == "science" else "standards",
                         role=role, day_obs=f"{night[:4]}-{night[4:6]}-{night[6:]}", path_1d=str(prod["1d"]),
                         path_2d=str(prod["2d"]) if prod["2d"] else None, reduced_utc=now,
                         pipeline="banzai-floyds", pipeline_version=version, **qc))
    # validation: every product must be usable before anything is cleaned
    invalid = {}
    for r in rows:
        why = R.validate_product(Path(r["path_1d"]), min_good=float(s["cleanup"].get("min_good_fraction", 0.8)))
        if why:
            invalid[r["basename"]] = why
        r["valid"] = why is None
    for k, v in invalid.items():
        logger.warning("  invalid product %s: %s", k, v)
    n_qc = R.write_qc(spec_db, [r for r in rows if r["frame_id"] is not None])

    # cleanup of secondary products, only after a complete and validated run
    cl = s["cleanup"]
    cleaned = None
    if cl.get("enabled", True) and rc == 0 and not errors and not missing and not invalid:
        calib = []
        for p in staged:
            if "-a00" in p.name or "-w00" in p.name:
                stem = p.name.split(".fits")[0].replace("-a00", "-a91").replace("-w00", "-w91")
                site, cam, night = stem[:3], stem.split("-")[1], stem.split("-")[2]
                calib += sorted((processed / site / cam / night / "processed").glob(f"{stem}.fits*"))
        cleaned = R.clean_secondary(
            [r for r in rows if r["valid"]], calib, [staged[0].parent, processed / "input"],
            drop_binned=bool(cl.get("drop_binned", True)),
            keep_binned_examples=int(cl.get("keep_binned_examples", 2)),
            example_roots=[cfg.spec_dir(target) / "reduced", processed])
        logger.info("%s: cleaned secondary products: %d files rewritten, %.0f MB freed", target,
                    cleaned["files"], cleaned["bytes"] / 1e6)
    elif cl.get("enabled", True):
        logger.warning("%s: secondary products kept (run not complete or not validated)", target)
    flagged = [(r["basename"], r["L1QFLAGS"]) for r in rows if r.get("L1QFLAGS") not in (None, "OK")]
    logger.info("%s: chain exit %d; %d frames ok, %d failed; %d science/standard products, %d files filed; "
                "%d QC rows → spec_qc; flags: %s", target, rc, sum(v == "ok" for v in status.values()), len(errors),
                len(rows), moved, n_qc, flagged or "none")
    if missing:
        logger.warning("%s: no -1d for %s", target, missing)
    out = {"target": target, "nights": nights, "pipeline_version": version, "exit_code": rc,
           "frames_ok": sum(v == "ok" for v in status.values()), "frames_failed": len(errors),
           "products": len(rows), "qc_rows": n_qc, "invalid": invalid, "cleaned": cleaned, "flagged": flagged, "missing": missing, "log": str(log)}
    if rc or errors or missing or invalid:
        raise RuntimeError(f"{target}: reduction incomplete (exit {rc}, {len(errors)} failed, "
                           f"{len(missing)} without products, {len(invalid)} invalid; see {log})")
    return out
