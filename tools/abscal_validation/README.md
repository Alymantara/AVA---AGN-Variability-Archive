Scripts behind `docs/reports/abscal/report_abscal.md` (18 Nov 2026). Read-only on all data. Python: an env with
pandas + pyarrow + astropy + scipy + click (e.g. `stenv`; numba not needed). Paths come from
`config/ava_config.yaml` (`AVA_CONFIG`); the Pickles library and the Seyfert-1 template come from the synphot
tree (`PYSYN_CDBS`). Passbands: `data/reference/lco_filters`, `data/reference/ref_filters`.

AGN SED corrections (redo once all spectra are reduced; every target with reduced -1d spectra is picked up):

    export PYSYN_CDBS=/path/to/synphot/trds
    python tools/abscal_validation/agn_sed_corrections.py --out <work>          # per spectrum x band, systematics
    python tools/abscal_validation/sed_photometry_check.py --sed <work> --out <work>   # same-night photometry
    python tools/abscal_validation/report_figs.py --ext <work>/ext --sed <work> --out docs/reports/abscal/figures

Star-based checks (Mrk 817 test archive):

    python tools/abscal_validation/abscal_trends.py <work>/trends       # residual trends
    python tools/abscal_validation/abscal_sensitivity.py <work>/trends  # absolute_* settings
    python tools/abscal_validation/abscal_ps1_apass.py <work>/ext       # SDSS / PS1 / APASS (one ESA Gaia-archive query)

`synlib.py`: passbands, AB synthetic photometry, stellar transform, FLOYDS reader (fringe-corrected EXTRACTED
orders spliced at `spectroscopy.products.prepspec.red_min_wavelength`), continuum fit and model extensions.
The general star-based check remains `tools/check_absolute_calibration.py` (`docs/figures/abscal/`).
Report PDF (docs/reports/report_abscal.pdf, the repository convention for report PDFs): `pandoc report_abscal.md -o ../report_abscal.pdf --pdf-engine=xelatex` with an fvextra header, run in docs/reports/abscal.

Website (web/calibration.php): `python tools/abscal_validation/export_web.py --sed <work> --ext <work>/ext --trends <work>/trends` (per-star residuals from `abscal_trends.py`) writes
`web.calibration_src` (data/products/calibration/calibration.json); the -w publish step copies it to
`<web.data_dir>/calibration/calibration.json`.

Absolute ZP anchors per field (19 Nov 2026; every field under photometry_root, read-only):

    python tools/abscal_validation/field_inventory.py <work>/inventory.csv      # frames, anchors, ZP fit per band
    python tools/abscal_validation/anchor_stars.py <work>/a.csv fairall_9:Y ... # current vs all-star anchor variants
    python tools/abscal_validation/anchor_sweep.py <work>/sweep.csv             # current (A) vs all-star (D), all bands
