"""Rerun ESO 511-30 PyTICS on scratch copies with the new QC gate (mirrors ava.pipeline.tasks.ensemble.ensemble,
without Prefect and without writing ava.db). Also renders the old (Turgon) merged light curve the same way."""
import importlib
import importlib.abc
import importlib.machinery
import logging
import shutil
import sys
import types
from pathlib import Path


class _Any(types.ModuleType):          # stand-in for prefect: decorators pass through, everything else is inert
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        if name in ("task", "flow"):
            def deco(*a, **k):
                if a and callable(a[0]) and not k:
                    return a[0]
                return lambda fn: fn
            return deco
        if name == "get_run_logger":
            return lambda: logging.getLogger("rerun")
        return _Any(f"{self.__name__}.{name}")

    def __call__(self, *a, **k):
        return self


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path, target=None):
        if name == "prefect" or name.startswith("prefect."):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)

    def create_module(self, spec):
        m = _Any(spec.name)
        m.__path__ = []
        return m

    def exec_module(self, module):
        pass


sys.meta_path.insert(0, _Finder())
sys.path.insert(0, "/Users/juan/astro/AVA")
logging.basicConfig(level=logging.INFO, format="%(message)s")

import numpy as np                     # noqa: E402
import pandas as pd                    # noqa: E402
import yaml                            # noqa: E402

from ava.config import cfg             # noqa: E402
from ava.photometry import ensemble as E   # noqa: E402
from ava.photometry.process import requalify   # noqa: E402
T = importlib.import_module("ava.pipeline.tasks.ensemble")
from ava.pipeline.tasks.webplot import spectroscopy_epochs   # noqa: E402
from ava.plots import webplots as wp   # noqa: E402

SRC, WORK, FIG = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
TARGET = "ESO_511-30"
phot = WORK / "photometry" / TARGET
if phot.exists():
    shutil.rmtree(phot)
phot.mkdir(parents=True)
for f in ("measurements.parquet", "reference_stars.csv", "reference_stars_meta.yaml", "target.yaml"):
    shutil.copy(SRC / f, phot / f)
db = WORK / "frame_qc.sqlite"
shutil.copy(SRC / "frame_qc_ESO_511-30.sqlite", db)
q = yaml.safe_load(open("/Users/juan/astro/AVA/config/ava_config.yaml"))["photometry"]["qc"]
fq = requalify(db, TARGET, q)
print("after requalify: qc_pass %.3f" % fq.qc_pass.mean())
print(fq.qc_flags.fillna("").str.split(",").explode().value_counts().to_string())

ec = cfg.ensemble
sct = ec.get("scope_colour_terms", "auto")
sct = list(sct) if isinstance(sct, (list, tuple)) else (sct if sct == "auto" else bool(sct))
report = E.run_target(
    phot, db, TARGET, list(ec.filters), mode="full",
    min_epochs=int(ec.min_epochs), absolute=bool(ec.absolute), colour_term=bool(ec.colour_term),
    scope_colour_terms=sct, colour_check_min_gain=float(ec.get("colour_check_min_gain", 0.05)),
    ref_cameras=tuple(ec.intercal_reference_cameras), intercal_max_gap=float(ec.intercal_max_gap_days),
    intercal_min_pairs=int(ec.get("intercal_min_pairs", 10)),
    colour_bands=tuple(ec.get("colour_bands", ["g", "i"]) or ["g", "i"]),
    auto_refit=bool(ec.auto_refit), log=print,
    ignore_qc_flags=tuple(ec.get("pytics_ignore_qc_flags", ["no_zp", "zp_scatter", "zp_offset"]) or ()),
    update_kw=dict(refit_fraction=float(ec.get("refit_fraction", 0.1)),
                   refit_rms_factor=float(ec.get("refit_rms_factor", 2.0)),
                   refit_rms_floor=float(ec.get("refit_rms_floor", 0.002)), bad_flags=int(ec.bad_flags)),
    zp_kw=dict(clip=float(ec.get("absolute_clip", 3.0)), floor=float(ec.get("absolute_floor", 0.01)),
               max_rms_star=float(ec.get("absolute_max_rms_star", 0.05))),
    anchor_kw=dict(min_coverage=float(ec.get("absolute_min_coverage", 0.9)),
                   max_scatter=float(ec.get("absolute_max_scatter", 0.2)),
                   trend_degree=int(ec.get("absolute_trend_degree", 2)), bad_flags=int(ec.bad_flags))
    if ec.get("absolute_all_stars", True) else None,
    apply_kw=dict(max_rms_t=float(ec.get("max_rms_t", 0.05)), min_stars=int(ec.get("min_stars", 5))),
    max_loops=int(ec.max_loops), safe=float(ec.safe), frac=float(ec.frac), tiny=float(ec.get("tiny", 1e-4)),
    star_lim=int(ec.star_lim), bad_ids=tuple(ec.get("bad_ids", []) or []), bad_flags=int(ec.bad_flags),
    rms_err_floor=float(ec.get("rms_err_floor", 1e-3)), atol=float(ec.get("atol", 1e-5)))
lc = T.intercal_lightcurve(phot, ec)
error_model = str(ec.get("error_model", "fitted"))
csv = phot / f"{TARGET}_LCO_merged_lightcurve.csv"
T.export_merged_csv(lc, csv, TARGET, error_model=error_model, qc_path=T.qc_path_for(csv), name="ESO 511-30")

fd = wp.load_filter_dict(cfg._resolve(cfg.plots.filter_dict))
spec, last = spectroscopy_epochs(TARGET)


def merged_of(lc):
    m = pd.DataFrame({"mjd_mid": lc["MJD"], "filter": lc["Filter"], "mag": lc["mag_ic"],
                      "mag_err": lc["mag_err_model" if error_model == "fitted" else "mag_ic_err"],
                      "qc_pass": lc["good"].astype(int)})
    return m[np.isfinite(m["mag"].to_numpy(float))]


FIG.mkdir(parents=True, exist_ok=True)
kw = dict(spec_mjd=spec, last_spec_mjd=last, label="Merged by PyTICS", formats=["png"])
new = merged_of(lc)
old = merged_of(pd.read_parquet(SRC / "agn_lightcurve_pytics.parquet"))
for tag, m in (("new", new), ("old", old)):
    wp.plot_lightcurves(m, fd, FIG / f"lco_latest_{TARGET}_merged_{tag}", **kw)
    wp.plot_lightcurves(m, fd, FIG / f"lco_latest_{TARGET}_merged_{tag}_season", last_season=True,
                        season_gap_days=float(cfg.plots.get("season_gap_days", 60.0)), **kw)
s = pd.DataFrame({"old_good": old[old.qc_pass == 1].groupby("filter").size(),
                  "new_good": new[new.qc_pass == 1].groupby("filter").size()})
print(s.to_string())
s.to_csv(FIG / "eso511_good_epochs_old_new.csv")
for f in sorted(new["filter"].unique()):
    a = new[(new["filter"] == f) & (new.qc_pass == 1)]
    b = old[(old["filter"] == f) & (old.qc_pass == 1)]
    print(f, "median err old %.4f new %.4f" % (b.mag_err.median(), a.mag_err.median()))
