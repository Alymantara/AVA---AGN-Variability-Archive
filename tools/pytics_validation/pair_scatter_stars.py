#!/usr/bin/env python
"""Control for pair_scatter_all.py: back-to-back pairs of the PyTICS comparison stars (constant sources).

For every stored solution (<photometry_root>/<target>/pytics/<filter>/), each comparison star's ensemble-
calibrated magnitude per epoch is m = mag_inst − DMAGT − DMAGS (as for the AGN; per-scope colour terms are a
constant per star and cancel in a same-scope pair).  Consecutive epochs of one scope < --max-dt minutes apart:
    z_phot = Δm / √(σ₁² + σ₂²)                     σ = SExtractor error
    z_rand = Δm / √(σ₁² + rms_t₁² + σ₂² + rms_t₂²)  as the AGN's PyTICS random error
Stars are not variable (comparison stars passed PyTICS's selection), so z tests the error model directly
and, star by star, its dependence on brightness.  Read-only.

    python tools/pytics_validation/pair_scatter_stars.py --out <work> [--targets ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import click
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ava.config import cfg  # noqa: E402

BAND = {"up": "u", "B": "B", "gp": "g", "V": "V", "rp": "r", "ip": "i", "zs": "z", "Y": "Y"}


@click.command()
@click.option("--out", type=click.Path(file_okay=False, path_type=Path), required=True)
@click.option("--targets", multiple=True)
@click.option("--max-dt", default=60.0, show_default=True, help="minutes")
@click.option("--bad-flags", default=28, show_default=True)
def main(out, targets, max_dt, bad_flags):
    out.mkdir(parents=True, exist_ok=True)
    names = targets or sorted(p.parent.parent.name for p in cfg.phot_root.glob("*/pytics/absolute_zp.json"))
    res = []
    for t in names:
        ph = cfg.phot_dir(t)
        if not (ph / "measurements.parquet").exists():
            continue
        meas = pd.read_parquet(ph / "measurements.parquet",
                               columns=["frame", "star_id", "is_agn", "mag_inst", "magerr", "sex_flags"])
        meas = meas[~meas["is_agn"] & ((meas["sex_flags"].fillna(0).astype(int) & bad_flags) == 0)]
        for f in BAND:
            d = ph / "pytics" / f
            if not (d / "epochs.parquet").exists():
                continue
            ep = pd.read_parquet(d / "epochs.parquet")[["frame", "MJD", "scope", "DMAGT", "rms_t"]]
            sc = pd.read_parquet(d / "scopes.parquet").set_index("scope")["DMAGS"]
            st = pd.read_parquet(d / "stars.parquet")[["star_id", "m_star"]]
            m = meas[meas["star_id"].isin(st["star_id"])].merge(ep, on="frame")
            if m.empty:
                continue
            m["mc"] = m["mag_inst"] - m["DMAGT"] - m["scope"].map(sc)
            m = m.sort_values(["star_id", "scope", "MJD"])
            same = (m["star_id"].to_numpy()[1:] == m["star_id"].to_numpy()[:-1]) & \
                   (m["scope"].to_numpy()[1:] == m["scope"].to_numpy()[:-1])
            dt = np.diff(m["MJD"].to_numpy()) * 1440
            k = np.where(same & (dt < max_dt))[0]
            if not len(k):
                continue
            a, c = m.iloc[k], m.iloc[k + 1]
            dm = c["mc"].to_numpy() - a["mc"].to_numpy()
            ep_ = np.hypot(a["magerr"].to_numpy(), c["magerr"].to_numpy())
            er = np.sqrt(a["magerr"].to_numpy() ** 2 + a["rms_t"].to_numpy() ** 2 + c["magerr"].to_numpy() ** 2
                         + c["rms_t"].to_numpy() ** 2)
            res.append(pd.DataFrame({"target": t, "band": BAND[f], "star_id": a["star_id"].to_numpy(),
                                     "MJD": a["MJD"].to_numpy(), "scope": a["scope"].to_numpy(), "frame": a["frame"].to_numpy(),
                                     "fam": a["scope"].str.split("-").str[1].str.extract(r"^([A-Za-z]+)")[0].to_numpy(),
                                     "mag_inst": a["mag_inst"].to_numpy(), "e_phot": ep_, "e_rand": er,
                                     "rms_t": np.hypot(a["rms_t"].to_numpy(), c["rms_t"].to_numpy()) / np.sqrt(2),
                                     "z_phot": dm / ep_, "z_rand": dm / er}))
        print(t, sum(len(r) for r in res if r["target"].iloc[0] == t))
    P = pd.concat(res, ignore_index=True)
    P.to_parquet(out / "pairs_stars.parquet", index=False)
    print("star pairs:", len(P))


if __name__ == "__main__":
    main()
