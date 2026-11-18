# Absolute calibration accuracy — pointer (18 Nov 2026)

The full study is `docs/reports/abscal/report_abscal.md` (PDF next to it), with the spectra and passband
figures. Scripts: `tools/abscal_validation/` (README there).

- **Stars:**
  - AVA = GSPC to ≲ 3 mmag; g r i z agree with SDSS DR16 / PS1 DR2 to ≲ 3 mmag (z −7 vs SDSS); u −3 ± 8.
  - B/V can only be checked to ~20–25 mmag.
  - No trends above ~5 mmag; the `absolute_*` settings are robust.
  - APASS DR9 is off by 0.03–0.17 mag.
- **AGN:** applying stellar colour terms at the AGN colour mis-states its SDSS/Landolt magnitude, by
  −24…−45 mmag (B, g), +27…+78 (V), −48…+181 (r) and ~0 (i), from 166 fringe-corrected FLOYDS spectra of
  Mrk 817, NGC 4151 and Fairall 9.
  - The causes are emission lines at filter edges (Hα vs the LCO r′ / SDSS r red edges, [O III] vs LCO V /
    Landolt V) and the non-stellar continuum.
  - The spectra give the correction (shape only; slit losses cancel). It is stable to 1–10 mmag from epoch
    to epoch.
  - Same-night photometry confirms it in r−i.
- **Recommendation:** publish natural-system (LCO) AB magnitudes plus passbands. Offer reference-system
  fluxes as a derived product with per-target spectral corrections. Redo the study once all spectra are
  reduced.
