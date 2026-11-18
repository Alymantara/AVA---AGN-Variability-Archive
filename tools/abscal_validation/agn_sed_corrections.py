#!/usr/bin/env python
"""AGN SED corrections to AVA's absolute photometry, from the FLOYDS spectra of each target.

AVA calibrates the AGN as if it were a star of its own g−i:

    m_AVA = m_inst + ZP + C (c_AGN − c0)         (ensemble.absolute_zp, GSPC anchors)

For every reduced FLOYDS spectrum (only the spectral *shape* matters; slit losses cancel) this computes,
per band, through the LCO natural passbands and the reference (GSPC) passbands:

  delta_ref = m_ref,true − m_AVA = Δ_AGN − (a + C c_AGN),   Δ = m_ref − m_LCO (synthetic)
      → F_ref,true / F_AVA = 10^(−0.4 delta_ref): what turns AVA fluxes into true SDSS/Landolt-system fluxes
  delta_nat = m_LCO,nat − m_AVA = −(a + C c_AGN)
      → F_nat / F_AVA: what turns AVA fluxes into LCO natural-system AB fluxes (no spectrum needed)
  line part: delta_ref(spectrum) − delta_ref(continuum only)

with (a, C) the stellar transform from the Pickles library.  Systematics, each a separate column set:
  tuned   LCO curves shifted in wavelength so the synthetic C matches the empirical one (absolute_zp.json)
  step±   red order (≥ the splice) scaled by 1/ratio and ratio, ratio = red/blue order flux in 5300–5600 Å
          (measured per spectrum): the order-scaling uncertainty
  tilt±   spectrum multiplied by (λ/5500)^(±0.25) (≈ ±5 % per 1000 Å flux-calibration slope)
  colour  c_AGN from the spectrum instead of the photometry (when the photometry exists)

Spectra: the fringe-corrected per-order EXTRACTED fluxes, spliced at spectroscopy.products.prepspec.
red_min_wavelength (synlib.read_floyds); the merged SPECTRUM table is not fringe-corrected.
Targets: every <spectra_root>/<target>/reduced/*/*-1d.fits* (QC from hbeta_fits.parquet when present);
redshift from <spectra_root>/<target>/target.yaml; c_AGN from <photometry_root>/<target>/pytics/absolute_zp.json
if present, else the median synthetic g−i of the spectra.  Archive (BANZAI) -1d products, when present,
are run as a separate 'archive' reduction for comparison.

    PYSYN_CDBS=<synphot tree> python tools/abscal_validation/agn_sed_corrections.py --out <work> [--target T ...]

Outputs in --out: sed_corr_epochs.csv (one row per spectrum × variant), sed_corr_summary.csv,
sed_corr_transform.csv (a, C per band and variant, curve shifts), sed_corr_mean_spectra.npz (for figures).
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import click
import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import synlib as S  # noqa: E402
from ava.config import cfg  # noqa: E402

TILT = 0.25
SPLIT = float(cfg.spectroscopy.products.prepspec.red_min_wavelength)   # blue/red order splice (Å)


def empirical_C(phot_dir: Path) -> dict:
    p = phot_dir / "pytics/absolute_zp.json"
    if not p.exists():
        return {}
    return {d["band"]: d for d in json.loads(p.read_text()).values()}


def tune_shifts(lib, C_emp: dict, grid=np.arange(-200, 201, 10.0)):
    """Wavelength shift of each LCO curve that makes the synthetic stellar C equal the empirical one."""
    Cs = {b: [] for b in S.BANDS}
    for s in grid:
        tr, _, _ = S.stellar_transform(S.Filters({b: s for b in S.BANDS}), lib)
        for b in S.BANDS:
            Cs[b].append(tr[b][1])
    shifts = {}
    for b in S.BANDS:
        if b not in C_emp or b == "u":           # Pickles u is poor (59 mmag rms): no tuning
            continue
        c = np.array(Cs[b])
        target = C_emp[b]["C"]
        k = np.argmin(np.abs(c - target))
        # monotonic local interpolation around the closest grid point
        lo, hi = max(k - 1, 0), min(k + 2, len(grid))
        o = np.argsort(c[lo:hi])
        shifts[b] = float(np.interp(target, c[lo:hi][o], grid[lo:hi][o]))
        if abs(shifts[b]) >= grid.max():
            shifts[b] = np.nan
    return shifts, grid, Cs


def target_list(only):
    out = []
    for d in sorted(cfg.spec_root.iterdir()):
        if not d.is_dir() or d.name in ("raw_data", "banzai", "standards"):
            continue
        if only and d.name not in only:
            continue
        if glob.glob(str(d / "reduced/*/*-1d.fits*")):
            out.append(d.name)
    return out


def spectra_of(t: str):
    sd = cfg.spec_root / t
    files = sorted(glob.glob(str(sd / "reduced/*/*-1d.fits*")))
    qc = sd / "hbeta_fits.parquet"
    key = lambda n: Path(n).name.rsplit("-e", 1)[0]        # frame id without the -eNN level / suffix
    meta = pd.DataFrame({"path": files, "basename": [key(f) for f in files]})
    if qc.exists():
        h = pd.read_parquet(qc)[["basename", "MJD", "ok", "qc", "cont5100", "hb_broad", "oiii5007"]]
        h["basename"] = h["basename"].map(key)
        meta = meta.merge(h, on="basename", how="left")
    else:
        meta["ok"], meta["qc"] = True, ""
    meta["reduction"] = "ava"
    arch = sorted(glob.glob(str(sd / "archive/*/*-1d.fits*")))
    if arch:
        a = pd.DataFrame({"path": arch, "basename": [key(f) for f in arch], "reduction": "archive", "ok": True})
        a = a.merge(meta[["basename", "MJD", "qc", "cont5100", "oiii5007"]], on="basename", how="left")
        meta = pd.concat([meta, a], ignore_index=True)
    return meta


@click.command()
@click.option("--out", type=click.Path(file_okay=False, path_type=Path), required=True)
@click.option("--target", "targets", multiple=True, help="Target folder name(s); default all with spectra.")
@click.option("--tune-from", default="Mrk_817", show_default=True,
              help="Target whose empirical colour terms (absolute_zp.json) tune the LCO curves.")
def main(out, targets, tune_from):
    out.mkdir(parents=True, exist_ok=True)
    lib = S.pickles()
    C_emp_tune = empirical_C(cfg.phot_root / tune_from)
    shifts, grid, Cs = tune_shifts(lib, C_emp_tune)
    variants = {"nominal": S.Filters(), "tuned": S.Filters({b: v for b, v in shifts.items() if np.isfinite(v)})}
    trans = {}
    rows_t = []
    for vn, F in variants.items():
        tr, _, _ = S.stellar_transform(F, lib)
        trans[vn] = tr
        for b in S.BANDS:
            a, C, rms, n = tr[b]
            rows_t.append(dict(variant=vn, band=b, a=a, C=C, rms=rms, n=n, shift_A=F.shift[b],
                               C_emp=C_emp_tune.get(b, {}).get("C", np.nan), C_emp_err=C_emp_tune.get(b, {}).get("C_err", np.nan)))
    pd.DataFrame(rows_t).to_csv(out / "sed_corr_transform.csv", index=False)
    pd.DataFrame({"shift_A": grid, **{f"C_{b}": Cs[b] for b in S.BANDS}}).to_csv(out / "sed_corr_tuning_grid.csv", index=False)
    print("LCO curve shifts matching the empirical C (Å):", {b: round(v, 1) for b, v in shifts.items()})

    rows, means = [], {}
    for t in target_list(targets):
        ty = yaml.safe_load((cfg.spec_root / t / "target.yaml").read_text())
        z = float(ty["redshift"])
        Ce = empirical_C(cfg.phot_root / t)
        c_phot = next(iter(Ce.values()))["agn_colour"] if Ce else np.nan
        meta = spectra_of(t)
        use = meta[meta["ok"].fillna(False).astype(bool)]
        print(f"{t}: z={z:.4f}, {len(use)} spectra ({(use.reduction == 'ava').sum()} AVA, "
              f"{(use.reduction == 'archive').sum()} archive), photometric g−i = {c_phot:.3f}")
        stack = []
        per = []
        for _, s in use.iterrows():
            w, fl, oratio, isred = S.read_floyds(s["path"], SPLIT)
            cont = S.continuum(w, fl, z)
            W, Fx, meas = S.extend(w, fl, z)
            _, Cx, _ = S.extend(w, cont, z)
            red_ext = W >= SPLIT          # red order and its red extension
            # order step: red order rescaled onto the blue one (overlap ratio) vs as reduced; the ± pair
            # brackets the as-reduced spectrum symmetrically by the measured mismatch
            tilts = {"": 1.0, "tilt+": (W / 5500.0) ** TILT, "tilt-": (W / 5500.0) ** -TILT,
                     "step+": np.where(red_ext, 1 / oratio, 1.0), "step-": np.where(red_ext, oratio, 1.0)}
            rec = dict(target=t, z=z, basename=s["basename"], reduction=s["reduction"], MJD=s.get("MJD"), qc=s.get("qc"),
                       order_ratio=oratio, cont5100=s.get("cont5100"), oiii5007=s.get("oiii5007"), wmin=w.min(), wmax=w.max())
            for vn, Fl in variants.items():
                for tn, tw in tilts.items():
                    if tn and vn != "nominal":
                        continue
                    m = Fl.mags(W, Fx * tw)
                    mc = Fl.mags(W, Cx * tw)
                    key = vn + (f"_{tn}" if tn else "")
                    rec[f"gi_{key}"] = m["gi"]
                    for b in S.BANDS:
                        rec[f"Delta_{b}_{key}"] = m[f"ref_{b}"] - m[f"lco_{b}"]
                        rec[f"Deltac_{b}_{key}"] = mc[f"ref_{b}"] - mc[f"lco_{b}"]
                        rec[f"linefrac_{b}_{key}"] = 1 - 10 ** (-0.4 * (mc[f"ref_{b}"] - m[f"ref_{b}"]))
                        rec[f"linefrac_lco_{b}_{key}"] = 1 - 10 ** (-0.4 * (mc[f"lco_{b}"] - m[f"lco_{b}"]))
            for b in S.BANDS:
                rec[f"extrap_{b}"] = max(S.extrapolated_fraction(W, meas, variants["nominal"].lco[b]),
                                         S.extrapolated_fraction(W, meas, variants["nominal"].ref[b]))
            per.append(rec)
            if s["reduction"] == "ava":
                g = np.arange(3000, 11000, 2.0)
                n5 = np.median(fl[(w / (1 + z) > 5080) & (w / (1 + z) < 5130)])
                stack.append((np.interp(g, w, fl / n5, left=np.nan, right=np.nan), np.interp(g, w, cont / n5, left=np.nan, right=np.nan)))
        per = pd.DataFrame(per)
        # AGN colour used by AVA: photometric if available, else the median spectral g−i (AVA reduction)
        c_spec = per.loc[per.reduction == "ava", "gi_nominal"].median()
        per["c_phot"], per["c_spec"] = c_phot, c_spec
        for vn in variants:
            for key in [k for k in ["", "_tilt+", "_tilt-", "_step+", "_step-"] if not (k and vn != "nominal")]:
                kk = vn + key
                for cname, cval in [("", c_phot if np.isfinite(c_phot) else c_spec), ("_cspec", c_spec)]:
                    if cname and key:
                        continue
                    for b in S.BANDS:
                        a, C, _, _ = trans[vn][b]
                        per[f"dref_{b}_{kk}{cname}"] = per[f"Delta_{b}_{kk}"] - (a + C * cval)
                        per[f"dline_{b}_{kk}{cname}"] = per[f"Delta_{b}_{kk}"] - per[f"Deltac_{b}_{kk}"]
                        per[f"dnat_{b}_{kk}{cname}"] = -(a + C * cval)
        rows.append(per)
        if stack:
            g = np.arange(3000, 11000, 2.0)
            means[t] = dict(wave=g, flux=np.nanmedian([s[0] for s in stack], axis=0),
                            cont=np.nanmedian([s[1] for s in stack], axis=0),
                            p16=np.nanpercentile([s[0] for s in stack], 16, axis=0),
                            p84=np.nanpercentile([s[0] for s in stack], 84, axis=0), z=z)
    ep = pd.concat(rows, ignore_index=True)
    ep.to_csv(out / "sed_corr_epochs.csv", index=False)
    np.savez(out / "sed_corr_mean_spectra.npz", **{f"{t}__{k}": v for t, d in means.items() for k, v in d.items()})

    # ---------------- summary ----------------
    summ = []
    for t, g in ep.groupby("target"):
        A = g[g.reduction == "ava"]
        R = g[g.reduction == "archive"]
        for b in S.BANDS:
            d = A[f"dref_{b}_nominal"]
            r = dict(target=t, band=b, n=len(d), z=A["z"].iloc[0],
                     extrap=A[f"extrap_{b}"].median(),
                     dref=d.median(), dref_sd=d.std(), dref_min=d.min(), dref_max=d.max(),
                     dline=A[f"dline_{b}_nominal"].median(),
                     linefrac_ref=A[f"linefrac_{b}_nominal"].median(), linefrac_lco=A[f"linefrac_lco_{b}_nominal"].median(),
                     dnat=A[f"dnat_{b}_nominal"].median(),
                     sys_tuned=(A[f"dref_{b}_tuned"] - d).median(),
                     sys_tilt=((A[f"dref_{b}_nominal_tilt+"] - A[f"dref_{b}_nominal_tilt-"]) / 2).abs().median(),
                     sys_step=((A[f"dref_{b}_nominal_step+"] - A[f"dref_{b}_nominal_step-"]) / 2).abs().median(),
                     sys_colour=(A[f"dref_{b}_nominal_cspec"] - d).median(),
                     dnat_tuned=A[f"dnat_{b}_tuned"].median(),
                     sys_reduction=(R.set_index("basename")[f"dref_{b}_nominal"]
                                    - A.set_index("basename")[f"dref_{b}_nominal"]).median() if len(R) else np.nan)
            if (A["cont5100"] / A["oiii5007"]).notna().sum() > 5:
                # AGN state: 5100 Å continuum relative to [O III] (slit losses cancel)
                ratio = A["cont5100"] / A["oiii5007"]
                k = ratio.notna() & (ratio > 0) & d.notna()
                x = np.log10(ratio[k])
                r["slope_per_dex_cont"] = np.polyfit(x, d[k], 1)[0] if np.ptp(x) > 0.05 else np.nan
                r["cont5100_range_dex"] = np.ptp(x)
            summ.append(r)
    summ = pd.DataFrame(summ)
    summ["sys_total"] = np.sqrt(summ["sys_step"] ** 2 + summ["sys_tilt"] ** 2 + summ["sys_colour"].fillna(0) ** 2
                                + summ["sys_reduction"].fillna(0) ** 2)
    summ["flux_corr_ref"] = 10 ** (-0.4 * summ["dref"])
    summ["flux_corr_nat"] = 10 ** (-0.4 * summ["dnat"])
    summ.to_csv(out / "sed_corr_summary.csv", index=False)
    pd.set_option("display.width", 250)
    cols = ["target", "band", "n", "extrap", "dref", "dref_sd", "dline", "linefrac_ref", "linefrac_lco", "dnat",
            "sys_tuned", "sys_tilt", "sys_step", "sys_colour", "sys_reduction", "sys_total", "slope_per_dex_cont", "flux_corr_ref"]
    show = summ[cols].copy()
    for c in ["dref", "dref_sd", "dline", "dnat", "sys_tuned", "sys_tilt", "sys_step", "sys_total", "sys_colour", "sys_reduction", "slope_per_dex_cont"]:
        show[c] = (show[c] * 1e3).round(1)
    print(show.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
