# PyTICS in AVA: algorithm and changes from the published code

*Material for the photometry manual (Nov 2026). Code: `ava/photometry/ensemble.py`, `ava/photometry/intercal.py`.
Diagram: `docs/figures/pytics/pytics_workflow.pdf` (TikZ source `.tex`; PNG preview). Validation and quality figures:
`docs/figures/pytics/`.*

Reference implementation: Vieliute et al. 2025 (RASTI, doi:10.1093/rasti/rzaf021); github.com/Astroberta/PyTICS,
commit 003bcbd, `Filter.Corr` and `Filter.AGN_LC`.

## 1. The published model (kept unchanged)

For one filter, every comparison-star measurement of star *s* at epoch *t* on scope *k* (telescope + camera) is

    m_obs = m*_s + DMAGT_t + DMAGS_k
    σ_tot² = σ_phot² + rms*_s² + rms_t² + rms_sc,k²

It is solved iteratively; one loop consists of:

1. **Epochs.**
   - Inverse-variance star means are taken per scope.
   - For every epoch, `arx` of (m − scope mean) gives dmagt and rms_t.
   - dmagt is damped by `safe` after the first loop.
   - DMAGT is made zero-mean within each scope (row-weighted).
2. **Scopes.**
   - `arx` per scope of (m − dmagt − provisional m*) gives dmags and rms_sc.
   - DMAGS is made zero-mean over all data.
3. **Stars.**
   - `arx` per star of (m − dmagt − dmags) gives m* and rms* (damped).
   - The data are shifted by dmagt + dmags.
4. **Reference.** The brightest star's mean is set to 0, and the shift is accumulated.
5. **Stop.** The loop stops when every traced parameter changes by less than 10⁻⁴ of its error.

`arx` is K. Horne's extra-variance optimal average (avgrmsx). AVA uses the identical algorithm, compiled with numba and run for all groups at once.

Comparison stars come from `Brightest_Reduced`:

- stars with more than *frac* × the maximum number of points;
- the brightest `Star_Lim` of those.

AGN calibration (`AGN_LC`):

    m_AGN = m_obs − DMAGT − DMAGS
    σ² = σ_phot² + rms_sc² + rms_t²

**Fidelity.** With `rms_err_floor=0, atol=0, colours=None` and the AGN rows removed, the AVA port reproduces `Filter.Corr` to float precision on Mrk 817 g:

- AGN differences < 10⁻¹⁰ mmag;
- the same number of loops: 38 for the 2023 subset and 67 for all data;
- 40–70× faster.

## 2. Changes to the algorithm

| # | Change | Why | Parameter (default) | Recover PyTICS |
|---|---|---|---|---|
| 1 | AGN never a comparison star | `Corr` / `CorrUpdate_New` call `Brightest_Reduced` without `AGN_ID`; the AGN is among the brightest sources | always | pass the AGN in `bad_IDs` (same result) |
| 2 | Comparison rows with SExtractor FLAGS 4 / 8 / 16 dropped (AGN rows kept) | one MuSCAT edge star 2.6 mag off made `arx` bistable (rms_t 0 ↔ 0.6 mag) and u/B/g never converged | `bad_flags=28` | `bad_flags=0` |
| 3 | Per-scope colour term CK_k (step 2b), **decided per target and filter from the data** (§2.2) | cameras differ in colour response by up to 40 mmag per mag of g−i; the AGN is bluer than the stars | `colours=` star g−i; config `scope_colour_terms: auto` | `scope_colour_terms: false` |
| 4 | Stopping test: errors of rms_t, rms_sc, rms* floored | an rms at 0 has an error of ~10⁻⁹ and flips 0 ↔ 0.7 mmag forever | `rms_err_floor=1e-3` mag | `0` |
| 5 | Second stopping rule: stationary, gauge-free solution | a whole scope's DMAGT can trade with its DMAGS (±0.7 mmag) with identical predictions | `atol=1e-5` mag, 3 loops | `0` |
| 6 | Epochs keyed by frame, scopes by telescope + camera | MJD keys can collide; a camera change on one telescope is a new instrument | always | — |
| 7 | Star × scope offsets stored after the fit | needed by the incremental update (§3) | always (output only) | — |

### 2.1 Per-scope colour term (step 2b, inside every loop)

With c_s = GSPC (g−i) of star *s* and c0 = the median colour of the comparison stars, the model gains one term:

    m_obs = m*_s + DMAGT_t + DMAGS_k + CK_k (c_s − c0)

After step 2:

- **Fit.** The residual r = y − dmagt − dmags − m* is regressed per scope on δc = c_s − c0. Each scope gets a weighted slope with a free intercept, using weights 1/(σ² + rms_sc²).
- **Damping and constraint.** The slope is damped by `safe` after the first loop. It is then made zero-mean over the data (weighted by Σwδc²), because a slope common to all scopes is absorbed by m* and later by the absolute colour term C.
- **Accumulation.** CK += ck, and y −= ck_k δc.
- **Missing colours.** Stars without a GSPC colour have δc = 0 (no term).
- **Convergence.** CK is traced like the other parameters.
- **AGN.** It is evaluated at its own colour: m_AGN gets −CK_k (c_AGN − c0) (column `CKterm`).

Effect on Mrk 817 (`docs/figures/pytics/pytics_15_colour_terms_effect.png`):

- Sinistro camera-to-camera AGN offsets drop by 30–45 % in B, g and V.
- Same-night agreement between two Sinistro cameras improves by 8–12 % in u, g and V.
- In r, i and z the slopes are ≲ 2 mmag per mag, nothing improves, and the term is off there.

### 2.2 Automatic check: is the colour term needed? (`colour_term_check`)

Whether the term helps depends on the cameras, the field stars and the AGN colour, so it is tested per target and filter on every full fit (`scope_colour_terms: auto`):

1. **Two fits.** Fit without the colour terms (plain PyTICS, plus changes 1, 2, 4 and 5). Get the zero points and the AGN colour from that fit. Then refit with the colour terms.
2. **Two AGN light curves.** Build one from each fit (absolute, good epochs).
3. **Score each on the reference cameras** (`intercal_reference_cameras`, Sinistro):
   - (a) the rms of each camera's additive AGN offset against the others: flux-flux, a ≡ 1, in % of flux;
   - (b) the robust σ of the flux ratio on nights seen by two cameras less than 0.4 d apart.
4. **Decide.** Keep the colour terms if the mean relative improvement of (a) and (b) is ≥ `colour_check_min_gain` (5 %).
   - Fewer than two reference cameras, or no usable metric: off (plain PyTICS).
   - The decision and both scores are stored in `meta.colour_check`; daily updates reuse the decision until the next full fit.
   - `true`, `false` or a list of filters forces the choice.

Mrk 817 result (identical to the hand-picked choice):

| Filter | Gain | Offsets | Same-night σ | Decision |
|---|---|---|---|---|
| u | +9 % | 0.80 → 0.75 % | 1.37 → 1.20 % | on |
| B | +15 % | 1.00 → 0.70 % | 1.74 → 1.74 % | on |
| g | +26 % | 0.47 → 0.26 % | 0.89 → 0.82 % | on |
| V | +23 % | 1.00 → 0.62 % | 0.98 → 0.90 % | on |
| r | −9 % | 0.74 → 0.83 % | 0.78 → 0.82 % | off |
| i | −22 % | 0.16 → 0.24 % | 0.77 → 0.69 % | off |
| z | −4 % | 1.06 → 1.12 % | 1.91 → 1.94 % | off |
| Y | n/a | not enough data | not enough data | off |

The cost is one extra fit per filter, about 3 s.

### 2.3 Stopping rule

The fit stops at the first of:

- **(a) PyTICS:** max |Δp|/σ_p < 10⁻⁴, with σ floored at `rms_err_floor` for rms_t, rms_sc and rms*;
- **(b) stationary:** for 3 consecutive loops, all of the following move by less than `atol`:
  - the per-epoch total DMAGT_t + DMAGS_k(t);
  - the star means;

  each with the median change removed (a common shift is a gauge freedom), and CK.

Which rule fired is stored in `meta.stop`. On Mrk 817 every filter now stops in 26–47 loops; the AGN changes by ≤ 0.02 mmag compared with running to rule (a) alone.

## 3. New: incremental update (`update`)

**Kept from the stored solution:**

- m*, rms*, m*_err;
- DMAGS, rms_sc, CK;
- the star × scope offsets o_{s,k}, the residual star means per camera. These are what PyTICS step 1 measures epochs against.

**Each new epoch:**

    x = m_obs − m*_s − DMAGS_k − CK_k δc_s − o_{s,k}
    σ_x² = σ_phot² + rms*_s² + rms_sc,k² + σ_o²
    arx(x, σ_x) → DMAGT_t, rms_t

**A scope not seen before:**

- DMAGS = the weighted mean of its new DMAGT, then subtracted so that DMAGT stays zero-mean;
- CK = 0.

**`needs_refit` fires on any of:**

- a new scope;
- more than 10 % of epochs added by updates;
- the median rms_t of updated epochs > 2 × that of the full fit + 2 mmag.

With `auto_refit` (the default) the full fit runs immediately.

**Accuracy against a full refit:**

| Case | Agreement (rms) | Time |
|---|---|---|
| Last 60 nights, no colour terms | 0.05–0.6 mmag | 16–40 ms per filter per night |
| Last 60 nights, colour terms on | 0.3–1.0 mmag | 16–40 ms per filter per night |

Both are far below the 4–9 mmag AGN errors. A refit also shifts the whole history by a constant 0–3 mmag; the absolute zero point, refitted with it, cancels this shift.

## 4. New: absolute zero point (`absolute_zp`, `agn_zero_points`)

The fit runs over the comparison stars with GSPC `quality_ok` and rms* < 50 mmag:

    m_GSPC − m* = ZP + C [(g−i) − c0]

- **Weights:** 1/(σ_m*² + σ_ref² + rms*² + 0.01²).
- **Clipping:** iterated at 3σ (MAD-based).
- **Errors:** scaled by √χ²_ν when χ²_ν > 1.
- **The AGN colour** c_AGN (g−i) comes from its own calibrated mean magnitudes, iterated 3 times.
- **AGN zero point:** ZP_AGN = ZP + C (c_AGN − c0).

Updates reuse the stored ZP, because the star means do not change in an update.

Final AGN magnitude:

    m_AGN = m_obs − DMAGT_t − DMAGS_k − CK_k (c_AGN − c0) + ZP_AGN

Mrk 817: ZP errors are ±2 mmag in B g V r i. The colour terms C, per mag of g−i, are:

| Band | C |
|---|---|
| g | +0.045 |
| i | +0.027 |
| r | +0.016 |
| V | −0.010 |
| B | −0.032 |
| z | −0.035 |

## 5. New: epoch quality flag and random error

`good` = rms_t < 50 mmag and n_stars ≥ 5 (`apply(max_rms_t, min_stars)`). This flags 1–4 % of epochs: thin cloud, gradients, scattered light. The flagged epochs stay in the product but are excluded from the plots and from the intercalibration.

**Random error.** `mag_err_rand` = √(σ_phot² + rms_t²). The PyTICS `mag_err` also contains rms_sc, which is a per-camera systematic, the same for every epoch of a camera.

AGN pairs < 1 h apart on the same camera scatter as follows:

| Error used | σ of normalised differences | Meaning |
|---|---|---|
| `mag_err` | 0.53–0.79 | errors 1.3–1.9× too large |
| `mag_err_rand` | 0.86–0.98 (u 0.63) | about right |

Use `mag_err` for absolute or cross-camera comparisons, and `mag_err_rand` for epoch-to-epoch variability within a camera (figure `pytics_16`).

## 6. New: flux-flux intercalibration (`intercal.py`)

PyTICS makes the comparison *stars* agree between cameras. An extended AGN can still differ additively: a smaller aperture in arcsec captures less host light.

**The fit, per filter and camera:**

- Nightly inverse-variance mean fluxes (mJy) are compared with the reference cameras (`intercal_reference_cameras: [fa]`, excluding the camera under test).
- The reference is interpolated linearly to the camera's nights when the gap is < 3 d (or within 0.3 d).
- Fit: F_k = a·F_ref + b, with effective-variance weights and 4σ clipping. A second fit fixes a ≡ 1 (b1), and a third is a pure Δmag fit, for comparison.

**The correction:**

- F′ = F − b1 for the cameras in `intercal_correct_cameras: [ep]` (MuSCAT, 8.9″ vs 10.5″).
- Output columns: `F_ic`, `mag_ic`, `ic_a`, `ic_b`.
- Every camera's fit is written to `pytics/intercal.csv`.

**Mrk 817 MuSCAT:**

- b1 = −0.47 (g), −0.81 (r), −0.98 (i), −1.04 (z) mJy, i.e. 6–10 % of the flux.
- a = 1.00–1.08, consistent with 1.

## 7. Products and where they appear

| Product | Path | Written by |
|---|---|---|
| Solution | `<phot>/pytics/<filter>/{stars,scopes,epochs,star_scope}.parquet`, `meta.json` | `run_target` |
| AGN light curve (merged, absolute) | `<phot>/agn_lightcurve_pytics.parquet` / `.csv` | `run_target` + `intercal_lightcurve` |
| Intercalibration table | `<phot>/pytics/intercal.csv` | `intercal_lightcurve` |
| ZP star table | `<phot>/pytics/absolute_zp_stars.parquet` | `run_target` |
| Web plots | `cfg.plots_dir/lco_latest_<obj>_merged[_last6].png/.pdf` | Prefect task `ensemble` |
| **Shareable merged light curve** | `<phot>/<target>_LCO_merged_lightcurve.csv` (copied to `cfg.plots_dir`) | `export_merged_csv` |

Commands: `run_pipeline.py -t` (daily, incremental) and `--pytics-full` (on demand).

Config: `ensemble:` in `config/ava_config.yaml`. **Every PyTICS and AVA parameter is in this section:**

| Group | Parameters |
|---|---|
| Fit | `max_loops`, `safe`, `tiny`, `frac`, `star_lim`, `bad_ids`, `bad_flags`, `rms_err_floor`, `atol` |
| Colour terms | `scope_colour_terms`, `colour_check_min_gain` |
| Update | `auto_refit`, `refit_fraction`, `refit_rms_factor` |
| AGN light curve | `max_rms_t`, `min_stars` |
| Absolute zero point | `absolute`, `colour_term` |
| Intercalibration | `intercal_reference_cameras`, `intercal_correct_cameras`, `intercal_max_gap_days`, `intercal_min_pairs` |
| Export | `export_csv` |

**Shareable CSV.** Good epochs only, intercalibrated, one row per frame. Columns:

| Columns | Content |
|---|---|
| `target`, `MJD`, `filter` (u B g V r i z Y), `telescope`, `camera` | identification |
| `flux_mJy`, `flux_err_mJy` | flux with the total PyTICS error |
| `flux_err_random_mJy` | the random part of the error only |
| `mag_AB`, `mag_AB_err`, `mag_AB_err_random` | AB magnitude and errors |
| `frame` | archive frame name |

1 mJy = AB 16.4. Mrk 817: 17,162 rows.

**Note:** the separate web-plot stage (`-p`) still draws `lco_latest_<obj>` from the per-frame calibration. The PyTICS merged plots come only from the `ensemble` stage.

## 8. Quality checks (figures `pytics_16`–`pytics_18`, `tools/pytics_validation/quality_figs.py`)

- **`pytics_16_error_model`: the error model.**
  - Comparison-star residuals divided by σ_tot follow N(0,1) to |z| ≈ 3.5, with σ_z = 0.96–1.01 in every filter and flat with brightness (±5 %).
  - 0.06–0.12 % of comparison-star measurements lie beyond 5σ.
  - AGN errors: see §5. The total is conservative; the random part is about right.
- **`pytics_17_residual_systematics`: trends in the comparison-star residuals.**
  - Airmass and seeing: ≤ 1 mmag, so extinction and PSF are absorbed by DMAGT.
  - Time: ±1 mmag.
  - Star colour: ≤ 2 mmag, except z up to ±4 mmag (no colour terms in z).
  - Detector position: up to −4 mmag at the y edges in u and z (flat field or vignetting). A future position term could absorb it.
- **`pytics_18_epoch_quality`: epoch quality over time.**
  - rms_t: median ~0 (u 2 mmag); 90th percentile 6–15 mmag.
  - Good epochs: 96–99 %, with drops in a few months, mostly in u.
  - Comparison stars per epoch: ~97 on Sinistro (u ~65). MuSCAT has only 6–12; z MuSCAT sits near the `min_stars` = 5 limit.

## 9. Under verification: empirical AGN error model (`ava/photometry/errors.py`)

**Status:** fitted and written on every run, but **not used** for the products
(`ensemble.error_model: "pytics"`). Set it to `"fitted"` only after it has been verified on more targets.

**Why.** On AGN pairs less than 1 h apart on the same camera (`pytics_21`), the PyTICS random error
σ_phot ⊕ rms_t has the wrong shape:
- the best epochs are under-estimated by 1.2–1.6×;
- the noisiest epochs are over-estimated by 2–3×.

**Model.** One fit per filter × camera family (fa = Sinistro, ep = MuSCAT):

    σ_rand² = (k σ_phot)² + (β rms_t)² + s0²      same-camera AGN pairs < 1 h
    σ_tot²  = σ_rand² + s_cam²                    different-camera AGN pairs < 6 h (per filter)

- k, β and s0 come from a Student-t (ν = 4) likelihood of the pair differences. All three are then multiplied by one factor so that the robust σ_z = 1.
- k, β and s0 are partly degenerate. On synthetic data with 800 pairs, β is only good to about ±0.2, but the total σ is good to ±20 % in every error quartile.
- If the quoted errors span less than `error_model_min_error_range` (p90/p10 = 2.5), only a scale factor is fitted. This is the case for MuSCAT i and z, whose errors are all 1.5–3 mmag.
- With fewer than `error_model_min_pairs` pairs, the fit is pooled over the filter, and below that the PyTICS model is used.

**Mrk 817 (Sinistro).** k ≈ 1.0–1.1, β ≈ 0.1–0.2 and s0 ≈ 0–2 mmag:
- the photometric error is right;
- only ~15 % of rms_t applies to the AGN;
- there is a floor of 1–2 mmag.

s_cam is 6–8 mmag in g, V, r, i and u, 11 mmag in B and 15 mmag in z. In B and z it is the leftover camera offsets (z: the MuSCAT step between seasons, see `pytics_22`).

**Verification** (`tools/pytics_validation/verify_error_model.py`, `pytics_23`). The model is fitted on half the data and tested on the other half (even/odd nights; before/after MJD 59900).
- **Sinistro, same camera:** held-out σ_z goes from 0.55–0.99 to 0.83–1.20. The spread across error sextiles halves (0.76 → 0.33).
- **MuSCAT:** smaller gain (spread 0.75 → 0.53).
- **Different cameras:** this is mostly a calibration problem, not an error problem. σ_z is 0.65–1.9 depending on the split, because the camera offsets change with time.

Products: `pytics/error_model.csv`, and the columns `mag_err_model[_rand]` and `Ferr_model[_rand]` in `agn_lightcurve_pytics.parquet`.
