---
title: "PyTICS error bars: point-to-point tests on every AGN"
subtitle: "Section for the PyTICS update report (markdown; the LaTeX report is the user's)"
date: "19 November 2026"
---

# Point-to-point scatter: are the error bars right, and Gaussian?

## Summary

- **Test.** Two epochs taken minutes apart on the same camera should differ only by noise. We used 89,168
  such AGN pairs from 36 AGN and, as a control, 8.1 million comparison-star pairs.
- **Sinistro works, with a ~1 mmag floor that follows the conditions** (figures 9–10).
  - **Error size:** the observed scatter is 7 % above SExtractor's error down to ~3 mmag, then flattens at a
    floor of $s_0$ ≈ 1.1 mmag. AGN and stars give the same curve.
  - **Shape:** with the fitted error model, Sinistro pairs below the bright regime have width 1.00 (AGN) and
    0.98 (stars), with a Gaussian core and 0.8–1.3 % beyond 3σ.
  - **Conditions:** the floor rises from ~0.9 to ~1.7 mmag for short exposures, high airmass and poor seeing,
    and varies by 0.4 mmag from night to night. Scintillation is the likely cause.
- **The PyTICS random error √(σ_phot² + rms_t²) has the right average width (0.95) but the wrong shape.**
  - It lacks the floor and the 7 % on σ_phot.
  - It counts all of `rms_t`, of which only ~11 % applies.
  - So it is too small for bright, quiet epochs and up to 7× too large when `rms_t` is large. The fitted
    model `ava.photometry.errors` (k 1.07, β 0.11, $s_0$ 1.1 mmag) corrects this and holds when tested on
    nights it was not fitted to.
- **The tails** (1.7 % beyond 3σ against 0.27 % for a Gaussian):
  - **28 %** from bright epochs (floor plus outliers; not non-linearity on Sinistro);
  - **12 %** from MuSCAT, SBIG and Spectral;
  - **the rest** from isolated single-frame events (~1 % of pairs).
- **NGC 4151 on MuSCAT was saturated** (2024–25, after the 2-m mirror was realuminised) and nothing caught it.
  Fixed: MuSCAT saturation level and a new AGN peak check (`agn_saturated`).
- **Between cameras** the total error is right within 30 min, except B and z (camera term ~45 % too small).
  Over hours the AGN's own variability shows.
- **For lags:** use the model errors, drop saturated epochs, and treat the ~1 % outliers robustly.
- **Now in the pipeline (19 Nov 2026).** The products use the fitted model by default
  (`ensemble.error_model: fitted`), and the floor is always part of it:
  - fallbacks use a default model with the floor (k 1.07, β 0.11, $s_0$ 1.1 mmag), not the PyTICS form;
  - $s_0$ is never below 1 mmag (`error_model_min_floor`).

## Question

A reverberation lag, or any variability measure, is only as good as the error bars. We test them directly.
Two epochs of the same AGN taken minutes apart, with the same telescope and camera, should differ only by
noise: the AGN does not vary in a few minutes, and the camera offset cancels. So the normalised difference

$$ z = \frac{m_2 - m_1}{\sqrt{\sigma_1^2 + \sigma_2^2}} $$

must follow N(0, 1) if the errors σ are right and Gaussian. The test runs on every AGN with a PyTICS light curve
(36 in the test archive), with the comparison stars as a control.

## Data and method

- **AGN pairs ("back to back").** Consecutive good epochs of one band on one telescope + camera, less than
  1 h apart: **89,168 pairs** from 36 AGN, 2014–2026. 75 % are less than 2 min apart.
- **Comparison-star pairs (control).** The same pairs for every PyTICS comparison star, on the ensemble scale
  (m = mag_inst − DMAGT − DMAGS): **8.1 million pairs**. These stars are constant by selection.
- **Same-night cross-camera pairs.** Epochs of *different* cameras less than 6 h apart, on the
  intercalibrated magnitudes: 11,858 pairs. They test the camera-to-camera term of the total error.
- **Errors tested** (the columns of the products):

| name | definition | where |
|---|---|---|
| phot | SExtractor photometric error σ_phot | QC file `magerr_phot` |
| rand | PyTICS random error √(σ_phot² + rms_t²) | QC file `mag_AB_err_random` |
| total | PyTICS total error √(σ_phot² + rms_t² + rms_sc²) | merged CSV `mag_AB_err` |
| model | fitted error model, random part (below) | `ensemble.error_model: fitted` |

- **Statistics.** Robust width σ_rob = 1.4826 × median(|z − median z|), the median absolute deviation
  scaled so that for a Gaussian it equals the standard deviation. It measures the width of the *core* of the
  distribution: a few outliers barely move it, whereas they inflate the ordinary standard deviation. If the
  error bars are right, σ_rob = 1; 1.2 means the real scatter is 20 % larger than the errors say. The tails
  are measured separately. The fraction of pairs with |z| > 3
  (Gaussian: 0.27 %) and > 5 (5.7 × $10^{-5}$ %). Excess kurtosis of z/σ_rob. All split by band, camera, AGN,
  quoted error, `rms_t`, seeing, airmass, time separation and brightness on the detector.
- **Scripts.** `tools/pytics_validation/pair_scatter_all.py` (AGN pairs and tables),
  `pair_scatter_stars.py` (stars), `pair_scatter_figs.py` (figures in `docs/figures/pytics_errors/`).

## The error model (`ava.photometry.errors`)

PyTICS quotes a random error σ² = σ_phot² + rms_t², where `rms_t` is the scatter of the comparison stars about
the ensemble in that epoch. The error model replaces it with

$$ \sigma_\mathrm{rand}^2 = (k\,\sigma_\mathrm{phot})^2 + (\beta\,\mathrm{rms}_t)^2 + s_0^2 , \qquad
   \sigma_\mathrm{tot}^2 = \sigma_\mathrm{rand}^2 + s_\mathrm{cam}^2 $$

- **k** scales the SExtractor error.
- **β** is the fraction of the comparison-star scatter that really applies to the AGN.
- **$s_0$ is the floor:** a per-epoch error that remains however bright the source is (flat-field residuals,
  aperture centring, scintillation).
- **s_cam** is the camera-to-camera / night-to-night calibration error. Same-camera pairs cannot see it.

**How it is fitted.** Per target, band and camera family (Sinistro `fa`, MuSCAT `ep`, …), on that target's
same-camera pairs less than 1 h apart:
1. Maximise a Student-t likelihood (ν = 4) of the pair differences with variance $\sigma_1^2$ + $\sigma_2^2$. The Student-t
   keeps the tails from driving the fit.
2. Rescale k, β and $s_0$ by one common factor so that the robust width of z is exactly 1. The t scale is not
   a Gaussian σ.
3. Fit s_cam per band so that same-night cross-camera pairs also have unit width.
4. Groups with too few pairs use the band's pooled fit, then the PyTICS form (k = β = 1, $s_0$ = 0).

**What the fit finds.** Pooled over all Sinistro pairs (figure 7): **k = 1.07, β = 0.11, $s_0$ = 1.1 mmag**.
Per target and band (held-out fits): k = 0.93–1.18, β = 0.09–0.15, $s_0$ = 0.4–1.8 mmag.
- **SExtractor's error is about 7 % too small.** Stars show the same: σ_rob of z_phot is 1.06–1.16.
- **Only about 11 % of `rms_t` applies to the AGN, not 100 %.** `rms_t` mostly measures the noisiest
  comparison stars, not a common error.
- **The floor is small, about 1 mmag.** It matters only for the brightest epochs (σ_phot < 2–3 mmag), where
  it is comparable to σ_phot.

![The error model. Left: observed per-epoch scatter against the SExtractor error, for epochs with rms_t < 1 mmag. The model (green) follows k σ_phot and flattens at the floor $s_0$ = 1.1 mmag (dotted). PyTICS (orange dashed) is σ_phot alone. Right: at fixed σ_phot ≈ 5 mmag, the observed scatter hardly grows with rms_t; PyTICS adds all of it, the model 11 %.](../../figures/pytics_errors/pair_07_error_model.pdf)

## Results

### 1. Error bars in the core

| band | phot | rand (PyTICS) | total | model | \|z\|>3, rand | \|z\|>3, model |
|---|---|---|---|---|---|---|
| u | 1.14 | 0.85 | 0.58 | 1.00 | 1.2 % | 1.1 % |
| B | 1.17 | 0.98 | 0.60 | 1.00 | 1.2 % | 0.6 % |
| g | 1.28 | 1.03 | 0.51 | 1.01 | 2.6 % | 1.1 % |
| V | 1.20 | 0.96 | 0.59 | 1.00 | 1.5 % | 0.7 % |
| r | 1.30 | 0.95 | 0.62 | 1.01 | 2.3 % | 1.2 % |
| i | 1.22 | 0.93 | 0.65 | 1.01 | 1.5 % | 0.8 % |
| z | 1.12 | 0.91 | 0.66 | 1.01 | 1.4 % | 0.9 % |
| Y | 1.01 | 0.91 | 0.67 | 1.00 | 1.1 % | 1.1 % |
| **all** | **1.21** | **0.95** | **0.60** | **1.01** | **1.7 %** | **0.9 %** |

The table gives the robust width of z for each error, then the tail fractions (Gaussian: 0.27 %).

- **The PyTICS random error gets the core width about right** (0.95). This is an average of two opposite
  errors (section 2), not a correct shape.
- **The total error is too large for back-to-back pairs** (0.60). That is expected: its camera term rms_sc
  cancels within one camera. Use it for comparisons across cameras and nights, which is what the merged
  light curve needs.
- **The model's core width is 1.00 by construction.** The held-out test below shows that is not circular.

![Distributions of z for back-to-back pairs, AGN (left) and comparison stars (right), log scale, against N(0, 1).](../../figures/pytics_errors/pair_01_distributions.pdf)

![Q–Q plots per band. Inside ±2σ every band follows the Gaussian; the tails bend away (heavy tails).](../../figures/pytics_errors/pair_02_qq.pdf)

### 2. The shape of the error is wrong in PyTICS, right in the model

Robust width of z against the quoted error (figure 3, left):
- **Small quoted errors** (< 4 mmag): z is 12–30 % too wide.
- **Large quoted errors:** the PyTICS random error is up to 7× too large.

The cause is `rms_t` (figure 3, right). The larger the comparison stars' scatter in an epoch, the more the
error overstates the AGN's real scatter, and the stars' own scatter too. The model removes both trends.
SExtractor's error alone (stars, dotted) is too small by a nearly constant 4–20 %.

![Left: robust width of z against the quoted per-epoch error. Right: against rms_t.](../../figures/pytics_errors/pair_03_shape.pdf)

**Held-out validation.** 162 tests (13 AGN, every band and camera family with ≥ 300 pairs). The model is fitted
on even nights and tested on odd nights, and vice versa.
- **Model:** median width 1.00, 5–95 %: 0.82–1.20.
- **PyTICS random:** 0.95 (0.79–1.27).
- **Tails:** the model reduces them in every band (median |z| > 3: B 0.8 → 0.3 %, g 1.9 → 0.8 %).

So the model is not fitting noise: it transfers between nights.

### 3. The tails: where they come from

1.7 % of AGN pairs have |z| > 3 with the PyTICS random error. That is 1,524 pairs, where a Gaussian gives 241.
Attributing them in turn:

| source | share of pairs | tail rate | share of the tail |
|---|---|---|---|
| AGN bright on the detector (instrumental mag < −11) | 4.7 % | 10.2 % | 28 % |
| MuSCAT, SBIG, Spectral (remaining pairs) | 4.3 % | 4.8 % | 12 % |
| NGC 4151 (remaining) | 0.6 % | 4.2 % | 2 % |
| everything else (faint, Sinistro) | 90.4 % | 1.1 % | 58 % |

- **Brightness on the detector is the strongest effect** (figure 4).
  - **Fainter than instrumental magnitude −10:** width 0.9–1.0, tails 0.7–1.2 %.
  - **Brighter than −12:** width 1.3–3.3, tails 10–40 %.
  - **Stars do exactly the same.** None of these pairs had a flagged AGN detection: flagged frames are
    already excluded.
  - **Peak counts sort out the cause.** For 2.2 million Mrk 817 star measurements, the legacy SExtractor
    catalogues give the peak counts (FLUX_MAX + BACKGROUND), so the pair test can be binned by peak /
    saturation (figure 8).
    - **On Sinistro there is no non-linearity threshold.** With the fitted model the width is 1.06–1.25 from
      5 % of saturation upward, flat to 100 %.
    - **The excess is a constant floor.** The floor needed to explain it is 1.0–1.5 mmag at every peak level.
      In quiet frames it is 1.0–1.2 mmag (section 5), the $s_0$ = 1.1 mmag fitted on the AGN. It shows only
      for bright sources, whose σ_phot is $\lesssim$ 2 mmag.
    - **What remains is non-Gaussian outliers.** About 6 % beyond 3σ for bright stars with the model.
    - **MuSCAT shows no excess** on Mrk 817 at any peak level.
  - **So genuine saturation is a separate, rarer problem: the MuSCAT frames of NGC 4151.**
- **MuSCAT on NGC 4151 is saturated.**
  - MuSCAT pairs of NGC 4151 have width 2.6–4.2 and 35–61 % tails, every quarter from 2024Q4 to 2025Q3, at
    instrumental magnitude ≈ −13. This follows the realuminisation of the 2-m mirror.
  - MuSCAT had no saturation level in `photometry.calibration.camera_defaults`, and the AGN had no peak check
    at all (only the standards did). Fixed: see Recommendations.
  - On the same AGN, Sinistro gives 0.7–1.6.
- **The remaining 58 % are isolated events.** 889 tail pairs fall on 880 different target-band-nights:
  single frames (cosmic rays or bad pixels in the aperture, satellites, guiding jumps), not bad nights.
  - **Where the quoted error is smallest** (2.0 % tail rate below 4 mmag, against 0.15 % above 20 mmag): the
    missing floor and the too-small SExtractor error matter most there. The model halves the tail.
  - **At 20–60 min separations** (5.2 % against 1.0 % below 2 min): the start of real AGN variability.

![Brightness on the detector: robust width (left) and tail fraction (right) against instrumental magnitude, AGN and comparison stars.](../../figures/pytics_errors/pair_04_brightness.pdf)

![Comparison-star pairs of Mrk 817 binned by peak counts / saturation level, PyTICS random error and fitted model. Sinistro (solid) shows a flat excess above ~5 % of saturation (a floor, not non-linearity); MuSCAT (dotted) none. Dashed: the AGN cut at 0.8.](../../figures/pytics_errors/pair_08_peak.pdf)

![Robust width per AGN, PyTICS random error and fitted model (AGN with ≥ 100 pairs).](../../figures/pytics_errors/pair_05_per_agn.pdf)

### 4. Per AGN and per camera

- **Per AGN** (29 with ≥ 100 pairs, figure 5). PyTICS random widths run from 0.76 (Mrk 110) to 1.31
  (NGC 4151), median 0.95. The model brings 22 of them to 1.00 ± 0.03.
  - **Too few pairs for their own fit:** MR 2251-178 1.27, Mrk 110 0.76, NGC 4395 1.18, PKS 2004 1.07,
    RX J1438 1.05. The model falls back to the PyTICS form, so their widths do not change. A pooled
    per-band fit across AGN would serve them better.
  - **Mrk 1048:** 1.07.
  - **NGC 4151:** 1.04 after its own fit, but saturation remains (section 3).
- **Per camera** (figure 6, left).

| camera | width | \|z\|>3 |
|---|---|---|
| Sinistro (`fa`) | 0.92 | 1.3 % |
| Sinistro (`fl`) | 1.02 | 2 % |
| SBIG | 1.19 | 3.7 % |
| Spectral | 1.26 | 7.1 % |
| MuSCAT | 1.34 | 8.7 % (NGC 4151 dominates) |

The model fits each camera family separately, so this is absorbed. Saturation is not.

### 5. Sinistro: the floor, and the model works

Figure 9 isolates Sinistro, where most of the data are.
- **Left: the floor.** For epochs with quiet comparison stars (`rms_t` < 1.5 mmag), the observed per-epoch
  scatter of stars and AGN follows k·σ_phot (k = 1.07) down to σ_phot ≈ 3 mmag, then flattens.
  - From σ_phot 0.6 to 2 mmag the observed scatter stays at 1.3–2.1 mmag. That needs a floor of
    1.0–1.2 mmag, matching the $s_0$ = 1.1 mmag fitted on the AGN.
  - The very brightest stars (σ_phot < 0.5 mmag) need up to 1.5 mmag.
  - The floor is small, but it is what the bright epochs lacked.
- **Right: Sinistro is consistent.** With the model errors, Sinistro pairs fainter than instrumental
  magnitude −11 have:
  - **width** 1.00 (AGN) and 0.98 (stars);
  - **a Gaussian core** down to $10^{-3}$ of the peak;
  - **tails** of 0.8 % (AGN) and 1.3 % (stars) beyond 3σ, the isolated single-frame events.

![Sinistro. Left: observed per-epoch scatter against the photometric error for stars and AGN in quiet epochs; dashed, the photometric error alone; green, the model with k = 1.07 and the floor $s_0$ = 1.1 mmag (dotted). Right: z with the model errors for Sinistro pairs below the bright regime, against N(0, 1).](../../figures/pytics_errors/pair_09_sinistro_floor.pdf)

### 6. Is the floor constant? No: it follows the conditions

From 823,543 bright Sinistro star pairs (σ_phot < 2 mmag) in quiet frames (`rms_t` < 1.5 mmag), we solve per
group for the $s_0$ that gives unit width (figure 10). The overall value is **$s_0$ = 1.09 mmag**, the
model's constant. It varies with:

| condition | $s_0$ (mmag) |
|---|---|
| exposure ≤ 30 s → 60–300 s | 1.53 → 0.94–1.00 |
| airmass 1.15–1.3 → 1.5–1.8 | 1.11 → 1.70 |
| seeing < 1.5″ → 3–4″ | 1.03 → 1.71 |
| band | z, u, Y 0.6–0.9; B, V, g 1.2–1.3 |
| camera | 0.92 (fa06) → 1.52 (fa08) |
| year | 0.80 (2019–20) → 1.22–1.31 (2023–25) |

- **Night to night:** 94 camera-nights with ≥ 400 bright pairs. The median is 0.73 mmag, with an intrinsic
  spread of 0.43 mmag after removing the sampling error (0.17).
- **The likely cause is scintillation,** which is stronger for short exposures, at high airmass and in the
  blue. Young's formula gives ≈ 0.6 mmag for a 1-m telescope at 30 s and airmass 1.2.
- **A seeing term (aperture losses, centring) adds to it.**
- **So the floor is epoch dependent.** The constant 1.1 mmag is right on average and is what the model now
  uses. A floor computed per epoch from exposure time, airmass and seeing (for example, Young's
  scintillation term plus a seeing term) would follow each epoch. This is the next model change (checklist).

![The floor $s_0$ for bright Sinistro stars in quiet frames against exposure time, airmass, seeing and year. Dotted: the constant $s_0$ of the model.](../../figures/pytics_errors/pair_10_floor_conditions.pdf)

### 7. Between cameras: the total error

Same-night pairs from different cameras (figure 6, right):
- **Less than 30 min apart:** width 1.09 with the total error, so its camera term is about right.
- **The width grows with the separation** (1.27 at 1 h, 1.52 at 5 h): real AGN variability over hours, not
  an error.
- **Within 1 h, B and z are 1.43–1.45:** their camera-to-camera term is underestimated. In g, V, r, i it is
  0.92–1.15.

![Left: back-to-back width and tail fraction per camera. Right: width of same-night cross-camera pairs (total error) against their separation, with same-camera pairs for comparison.](../../figures/pytics_errors/pair_06_cameras.pdf)

## Conclusions

1. **The core of the error distribution is Gaussian.** Inside ±2σ every band and camera follows N(0, 1).
   The PyTICS random error has about the right average width (0.95), but the wrong shape:
   - too small when it is small (no floor, SExtractor ~7 % low);
   - too large when `rms_t` is large (only ~11 % of `rms_t` applies to the AGN).
2. **The fitted error model** (k ≈ 1.07, β ≈ 0.11, $s_0$ ≈ 1 mmag) gives unit width in every band and camera,
   held out across nights, and for 22 of 29 AGN. The rest are AGN with too few pairs for their own fit. It
   halves the tail.
3. **The tails are mostly instrumental and identifiable.**
   - Bright epochs: 28 % of the tail from 5 % of the data. On Sinistro this is the ~1.1 mmag floor
     (PyTICS has none) plus non-Gaussian outliers, not non-linearity.
   - MuSCAT on NGC 4151 after the mirror realuminisation.
   - The rest are isolated single-frame events at about 1 % (4× Gaussian), which a Student-t or a 4–5σ
     clip in the lag analysis absorbs.
4. **Between cameras the total error is right within 30 min**, except B and z, where the camera term is
   ~45 % too small.
5. **For lags:**
   - Use the model errors (`ensemble.error_model: fitted`).
   - Drop near-saturated epochs.
   - Treat the remaining 1 % outliers robustly.
   - The zero-point uncertainty (`zp_err_mag`) plays no part.

## Recommendations (status)

- **Done (19 Nov 2026): MuSCAT saturation.**
  - `camera_defaults.ep: saturate 118000, 2048 × 2048`. MuSCAT peaks pile up at 119k (ep03) to 134k (ep05)
    ADU in the legacy catalogues; the lowest is used.
  - New AGN peak check: `frame_qc.agn_peak` (FLUX_MAX + BACKGROUND of the AGN) and QC flag `agn_saturated`
    when it exceeds `photometry.qc.max_agn_peak_frac: 0.8` × SATURATE. That is the fraction the zero-point
    standards already use; figure 8 shows no reason for a lower one.
  - Needs a recalibration (`-c`) on turgon, then `--pytics-full`. Existing `frame_qc` rows have no
    `agn_peak` and are never flagged.
- **To decide:** fit the floor on star pairs as well. They give the same 1.0–1.2 mmag in quiet frames, up to
  1.5 mmag for the very brightest stars.
- **Done (19 Nov 2026): the floor is part of the error model, and the model is the products' default.**
  - `ensemble.error_model: fitted`.
  - Groups with too few pairs, missing bands or camera families, and the one-factor "scale" fit (MuSCAT) use
    `ensemble.error_model_default` (k 1.07, β 0.11, $s_0$ 1.1 mmag) instead of the PyTICS form, which has no
    floor.
  - `ensemble.error_model_min_floor: 0.001` keeps $s_0$ ≥ 1 mmag in every fit.
  - Tests: `tests/test_errors.py`.
- **To decide:** raise s_cam in B and z, or refit it per camera family.
- **To decide:** apply the same peak cut to the comparison stars. The bright tail is the same for stars;
  `measurements.parquet` would need the peak.
