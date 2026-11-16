"""Offline tests for ava.plots.webplots light-curve plots."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ava.plots import webplots as wp

ROOT = Path(__file__).resolve().parents[1]


def test_last_season_start():
    t = np.r_[np.arange(59000, 59100, 2.0), np.arange(59300, 59400, 3.0), np.arange(59600, 59650, 1.0)]
    assert wp.last_season_start(t, 60.0) == 59600.0
    assert wp.last_season_start(np.arange(10.0), 60.0) == 0.0          # one season: from the start
    assert np.isnan(wp.last_season_start([], 60.0))


def test_year_conversion_roundtrip():
    mjd = np.array([51544.5, 59580.0, 61000.25])
    assert wp._mjd_to_year(51544.5) == pytest.approx(2000.0)
    np.testing.assert_allclose(wp._year_to_mjd(wp._mjd_to_year(mjd)), mjd)


def _lc():
    rng = np.random.default_rng(0)
    t = np.r_[np.arange(59000, 59200, 1.5), np.arange(59400, 59600, 1.5)]
    rows = [dict(mjd_mid=x, filter=f, mag=15.0 + 0.1 * np.sin(x / 30) + rng.normal(0, 0.01), mag_err=0.01, qc_pass=1)
            for f in ("gp", "rp") for x in t]
    return pd.DataFrame(rows)


@pytest.mark.parametrize("kw", [{}, {"recent_days": 60}, {"last_season": True}])
def test_plot_lightcurves_options(tmp_path, kw):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fd = wp.load_filter_dict(ROOT / "data/reference/filter_dict.txt")
    shown = {}
    orig = plt.close

    def keep(fig=None):                      # inspect the figure before it is closed
        if fig is not None and hasattr(fig, "axes"):
            shown["fig"] = fig
        return orig(fig)

    plt.close = keep
    try:
        out = wp.plot_lightcurves(_lc(), fd, tmp_path / "lc", spec_mjd=[59570.0, 59590.0], last_spec_mjd=59590.0,
                                  label="Merged by PyTICS", formats=["png"], **kw)
    finally:
        plt.close = orig
    assert Path(out[0]).exists()
    fig = shown["fig"]
    first = fig.axes[0]
    assert first.get_title().startswith("Merged by PyTICS | Flux in mJy")
    if kw.get("last_season"):
        assert "Last season: " in first.get_title()
        assert first.get_xlim()[0] == pytest.approx(59400.0 - 5.0)
    # spectroscopy ticks: red vertical lines on the first panel inside the window
    red = [ln for ln in first.lines if ln.get_color() == "r"]
    assert len(red) == 2
    # calendar axis on top of the first panel
    assert any(type(c).__name__ == "SecondaryAxis" for c in first.child_axes)


def test_plots_from_parallel_threads(tmp_path):
    """The pipeline draws targets in a thread pool: concurrent figures (with mathtext labels) must all succeed,
    and one figure's style changes must not leak out (``wp.serialized``)."""
    from concurrent.futures import ThreadPoolExecutor

    import matplotlib.pyplot as plt

    fd = wp.load_filter_dict(ROOT / "data/reference/filter_dict.txt")
    size = plt.rcParams["font.size"]
    with ThreadPoolExecutor(6) as ex:
        outs = list(ex.map(lambda i: wp.plot_lightcurves(_lc(), fd, tmp_path / f"lc{i}", formats=["png"]), range(12)))
    assert all(Path(o[0]).exists() for o in outs)
    assert plt.rcParams["font.size"] == size


def test_webplot_skips_target_without_photometry(tmp_path, monkeypatch):
    """A spectroscopy-only target (no agn_lightcurve.parquet) is skipped, not failed."""
    import importlib
    import logging

    task_mod = importlib.import_module("ava.pipeline.tasks.webplot")     # the package re-exports the task by name
    monkeypatch.setattr(task_mod.cfg, "phot_dir", lambda t: tmp_path / t)
    monkeypatch.setattr(task_mod, "get_run_logger", lambda: logging.getLogger("test"))
    out = task_mod.webplot.fn("spec_only")
    assert out == {"target": "spec_only", "plots": [], "skipped": "no photometry"}
