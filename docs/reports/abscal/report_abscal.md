---
title: "AVA absolute photometric calibration: stars, AGN spectra and emission lines"
subtitle: "Accuracy of the Gaia-anchored zero points, and the SED corrections the AGN need"
date: "18 November 2026 (first pass: test archive, 3 targets with spectra)"
---

# 1. Summary

**Question.** AVA anchors every light curve to Gaia XP synthetic photometry (GSPC) of the field stars,
with a stellar colour term. How accurate is that for stars, and does it hold for an AGN, whose
spectrum is a power law plus host plus strong emission lines? If not, can we estimate the
correction from our own FLOYDS spectra?

**Answers.**

1. **For stars the calibration is accurate.** AVA reproduces GSPC to within 3 mmag, and agrees with
   SDSS DR16 and Pan-STARRS DR2 within 3 mmag in g, r, i and z (z: −7 against SDSS). u agrees with
   SDSS to −3 ± 8 mmag. There are no trends with magnitude, airmass, seeing, season or camera above
   about 5 mmag. The ZP settings (`absolute_clip`, `absolute_floor`, `absolute_max_rms_star`) move it
   by at most 5 mmag. B and V can't be checked better than about 20–25 mmag: no independent catalogue
   in the Landolt system is accurate enough.
2. **For the AGN it is not.** AVA treats the AGN as a star of the same g−i. Synthetic photometry of
   171 FLOYDS spectra gives, for the true reference-system magnitude minus AVA's:

| target (z) | B | g | V | r | i |
|---|---|---|---|---|---|
| Mrk 817 (0.031) | −26 ± 4 | −31 ± 11 | +47 ± 19 | **+138 ± 19** | +4 ± 4 |
| NGC 4151 (0.003) | −24 ± 2 | −45 ± 7 | **+78 ± 14** | **−48 ± 7** | 0 ± 1 |
| Fairall 9 (0.046) | −28 ± 2 | −25 ± 3 | +27 ± 7 | **+181 ± 9** | 0 ± 1 |

   Units are mmag. In flux these are factors of 0.85–1.05 (r) and 0.93–1.04 (B, g, V).
   - The largest terms come from the lines: Hα sits in a part of the passband that LCO r′ includes
     and SDSS r excludes (Mrk 817, Fairall 9); [O III] 5007 does the same between LCO V and
     Landolt V (NGC 4151).
   - The rest comes from the non-stellar continuum.
3. **Yes, the spectra give the correction.** Only the spectral *shape* within each band matters, so
   slit losses and the absolute flux calibration of the spectra cancel. Two checks support the
   method:
   - The corrections are stable from epoch to epoch (scatter 1–10 mmag over 28–47 nights). They
     depend on AGN state only weakly over the ranges covered.
   - On the one night with both a spectrum and photometry (Mrk 817), AVA's observed r−i and g−V
     match the prediction from the spectrum to 4 and 18 mmag. The true SDSS/Landolt colours are off by
     125 and 56 mmag.
4. **Recommendation.**
   - Publish the AGN photometry in the **LCO natural AB system**, plus the passbands.
   - Offer reference-system fluxes as a derived product, using these per-target, per-season spectral
     corrections.
   - Redo this study once all spectra are reduced: the scripts discover targets and epochs by
     themselves.
   - The numbers use the fringe-corrected per-order spectra. The merged FLOYDS `SPECTRUM` table is not
     fringe-corrected; using it changes B to i by ≤ 3 mmag but z by up to 34.

# 2. What AVA does, and what "system" means

A magnitude is defined by a passband. LCO r′ and SDSS r share a name, but their passbands differ
(figure 1). For the same object they give different numbers, and the difference depends on the
object's spectrum.

The ensemble (PyTICS) gives instrumental star means $m^*$. `ensemble.absolute_zp` then fits, over the
GSPC reference stars,

$$ m_\mathrm{ref} - m^* = ZP + C\,[(g-i) - c_0], $$

where $m_\mathrm{ref}$ is the GSPC magnitude in the *reference* system (SDSS u g r i z AB;
Johnson-Kron-Cousins B V, standardised on Landolt, converted to AB). The AGN light curve is

$$ m_\mathrm{AVA} = m_\mathrm{inst} - \mathrm{DMAGT} - \mathrm{DMAGS} + ZP + C\,(c_\mathrm{AGN} - c_0), $$

with $c_\mathrm{AGN}$ the AGN's mean g−i (0.341 for Mrk 817). The term $C\,(g-i)$ converts LCO
natural magnitudes into reference-system magnitudes. For stars that conversion depends almost only
on colour, so it works to a few mmag (section 4). For the AGN it assumes a star of the AGN's colour,
which an AGN is not.

Write $\Delta \equiv m_\mathrm{ref} - m_\mathrm{LCO}$, the synthetic difference between the two
systems for a given spectrum. For stars, $\Delta = a + C_\mathrm{syn}(g-i)$. Then:

- **Reference-system correction.**
  $\delta_\mathrm{ref} = m_\mathrm{ref,true} - m_\mathrm{AVA} = \Delta_\mathrm{AGN} - (a + C\,c_\mathrm{AGN})$,
  so $F_\mathrm{ref,true}/F_\mathrm{AVA} = 10^{-0.4\,\delta_\mathrm{ref}}$. It needs the AGN spectrum.
- **Natural-system shift.**
  $\delta_\mathrm{nat} = m_\mathrm{LCO,nat} - m_\mathrm{AVA} = -(a + C\,c_\mathrm{AGN})$. It needs no
  spectrum, only the passbands. It is exact for any SED, because the magnitude is then just what
  the LCO filter saw.

Either way the zero point still comes from Gaia; what changes is which passband the number refers to.

# 3. Data and passbands

| target | z | spectra used (nights) | MJD range | PyTICS photometry |
|---|---|---|---|---|
| Mrk 817 | 0.0313 | 6 AVA + 5 archive BANZAI (3) | 61266–61299 | yes (2020–Aug 2026) |
| NGC 4151 | 0.0033 | 60 (28) | 60635–60877 | not yet |
| Fairall 9 | 0.0461 | 100 (47) | 61280–61355 | not yet |

- **Spectra.** FLOYDS `-1d`, 6″ slit, AVA's banzai-floyds fork (`<spectra_root>/<target>/reduced/`).
  The analysis uses the **fringe-corrected per-order fluxes** (`EXTRACTED` table: `flux_optimal`, harmonic
  fringe model, `L1FRGMET = harmonic`). Blue order below 5300 Å and red order above, the products' splice
  (`spectroscopy.products.prepspec.red_min_wavelength`). The merged `SPECTRUM` table is *not*
  fringe-corrected: 17–19 % small-scale scatter at 8000–9000 Å, against 3–7 % in the corrected red order.
  It also mixes both orders over the whole overlap.
- **The FLOYDS sandbox** (`~/astro/floyds/work`) holds the same two science targets (Fairall 9, NGC 4151)
  plus standards, so it adds no new AGN. The other targets will come with the full reduction.
  All spectra passed the QC in `hbeta_fits.parquet`; spectra flagged STDFAR (flux standard far in
  time) are kept and checked separately. Coverage is 3350–10130 Å (Fairall 9 from 3275 Å).
- **Passbands.**
  - LCO: `data/reference/lco_filters` (filter × Sinistro CCD × atmosphere at X = 1; mirrors not
    included).
  - Reference: `data/reference/ref_filters`. SDSS u g r i z are SVO "full transmission", identical to
    the STScI CDBS DR1 response curves. Landolt B V are from Maíz Apellániz (2006).
- **Stars.** The Pickles UVKLIB library (131 spectra), fitted over the g−i range of the GSPC stars
  actually used (0.0–2.7).

![LCO natural passbands (solid) vs the reference passbands of the GSPC anchors (dashed). Shading: LCO minus reference; coloured where LCO transmits more. Wherever an emission line sits on a shaded region, the AGN magnitude in one system differs from the other in a way no stellar colour term can capture.](figures/fig01_filters.pdf)

The differences that matter for AGN (figure 1):

- **r.** LCO r′ transmits to 6925 Å, SDSS r only to 6730 Å (half power). Hα falls in that gap for
  0.026 < z < 0.055.
- **V.** LCO V starts at 4912 Å, Landolt V at 5050 Å. [O III] 5007 and Hβ at low z fall in that gap.
- **g.** LCO g′ extends to 5490 Å, SDSS g to 5330 Å. [O III] and Hβ fall there for z ≥ about 0.07–0.09.
- **i.** The blue edges agree within 40 Å, but Hα reaches them at z ≈ 0.05.
- **u.** LCO u′ cuts off sharply at 3842 Å, while SDSS u has a long red wing. The LCO u curve also
  has a 0.1–0.3 % red tail out to 9600 Å (a leak, or the floor of the measurement), worth about
  1.7 % of the band's photons for a flat spectrum.
- **z.** LCO z_s (8180–9170 Å) and SDSS z (8305–9255 Å, with a long red tail to about 11000 Å) differ
  substantially.

# 4. Stars: zero point, scatter and trends (Mrk 817 field)

Offset at the AGN colour, with the linear colour term free (mmag):

| filter | AVA − SDSS DR16 | AVA − PS1 − (GSPC − PS1) | GSPC − SDSS | star scatter vs SDSS |
|---|---|---|---|---|
| u | −3 ± 8 | – | −6 | 34 |
| B | +23 ± 6 (SDSS→B, Jordi et al. 2006) | – | +20 | 39 |
| g | 0 ± 3 | −3 ± 2 | +7 | 23 |
| V | +19 ± 4 (SDSS→V, Jordi) | – | +27 | 25 |
| r | +2 ± 4 | −3 ± 2 | +3 | 21 |
| i | −2 ± 3 | −2 ± 2 | 0 | 16 |
| z | −7 ± 3 | 0 ± 4 | −7 | 9 |

![AVA star zero points at the AGN colour against SDSS DR16 and against PS1 DR2. The PS1 column is corrected for the PS1 − GSPC system difference measured on the same stars.](figures/fig06_stars.pdf)

- **B and V.** AVA follows GSPC; the +20 mmag is GSPC against the Jordi transforms, not an AVA error.
  APASS DR9 (ESA Gaia-archive copy, 6–16 stars) is off by B +170, V +122, g +33, r +50 and
  i +67 mmag, for AVA and GSPC alike. APASS is not a precise anchor, so the `apass_model` fallback
  should be flagged when it is used.
- **Trends** (`abscal_trends.py`):

| trend | size |
|---|---|
| with magnitude | 1–6 mmag per mag (over 3–4 mag) |
| colour curvature at the AGN colour | +2 to +10 mmag (largest in i) |
| per-frame colour slope against airmass, at the AGN colour | ≤ 5 mmag per airmass |
| with seeing | ≤ 2 mmag per arcsec |
| between seasons | 1–3 mmag |
| between cameras | 1.4–3 mmag (z: 7) |

- **Sensitivity** (`abscal_sensitivity.py`). Over `absolute_clip` 2–∞, `absolute_floor` 0.003–0.03 and
  `absolute_max_rms_star` 0.01–∞, the AGN zero point moves by at most 3.5 mmag (5 at
  `absolute_floor` 0.03). Switching off `colour_term` moves it by 5–25 mmag. Keep the defaults.
- **Blue end.** Only 4 GSPC stars are bluer than the AGN in g−i, so the colour term is extrapolated
  slightly at the AGN.

# 5. Method for the AGN (`agn_sed_corrections.py`)

1. **Stellar transform.** Fit $\Delta = a + C\,(g-i)$ on the Pickles stars, per band.
2. **Each spectrum.**
   - Extend the spectrum: below its blue end with the NGC 5548 Seyfert-1 template moved to the
     target's z (affects u: 7–17 % of the band); above 10000 Å with a power law (affects z: 3–7 %).
   - Fit a continuum: a spline through 17 rest-frame line-free windows.
   - Compute $\Delta_\mathrm{AGN}$ for the full spectrum and for the continuum alone, then
     $\delta_\mathrm{ref}$, its line part (full minus continuum), and the line fraction of the band
     flux in both systems.
3. **AGN colour.** $c_\mathrm{AGN}$ is AVA's photometric value where it exists (Mrk 817); otherwise
   the median synthetic g−i of the spectra.
4. **Systematics,** each computed separately (table in section 8):

| name | what is varied |
|---|---|
| tilt | spectrum × (λ/5500)^±0.25, about ±5 % per 1000 Å of flux-calibration slope |
| step | red order (≥ 5300 Å) rescaled by the measured red/blue flux ratio in 5300–5600 Å (per spectrum: Mrk 817 0.98–1.00, NGC 4151 0.88–1.09, Fairall 9 0.95–1.07), and by its inverse |
| colour | $c_\mathrm{AGN}$ from the spectrum instead of the photometry |
| reduction | archive BANZAI `-1d` instead of AVA's reduction (Mrk 817) |
| tuned curves | LCO curves shifted in λ until the synthetic C equals the empirical one (section 7.1); reported as a pessimistic bound, not added in |

5. **AGN state.** Each correction is regressed on log F(5100 Å)/F([O III]), where slit losses cancel.

# 6. Results per target

## 6.1 Mrk 817 (z = 0.0313)

![Mrk 817: median FLOYDS spectrum (6 spectra) with the LCO (solid) and reference (dashed) passbands. Numbers above the passbands: true − AVA in mmag.](figures/fig_Mrk_817_overview.pdf)

![Mrk 817 band by band: spectrum, continuum fit, LCO and reference passbands, and where they differ. Hα (6769 Å) lies in the strip that LCO r′ transmits and SDSS r does not.](figures/fig_Mrk_817_bands.pdf)

![Mrk 817 per-spectrum corrections against time and against AGN state. Only 3 nights, so the state slope is poorly constrained.](figures/fig_Mrk_817_epochs.pdf)

## 6.2 NGC 4151 (z = 0.0033)

![NGC 4151 median spectrum (60 spectra). [O III] 5007 is very strong.](figures/fig_NGC_4151_overview.pdf)

![NGC 4151 band by band. [O III] 5007 at 5024 Å is fully inside LCO V (blue edge 4912 Å) but on the edge of Landolt V (5050 Å): +86 mmag of line term. Hα (6585 Å) is inside both r passbands, but the narrower SDSS r gives it more weight: −59 mmag.](figures/fig_NGC_4151_bands.pdf)

![NGC 4151 per-spectrum corrections (28 nights).](figures/fig_NGC_4151_epochs.pdf)

## 6.3 Fairall 9 (z = 0.0461)

![Fairall 9 median spectrum (100 spectra).](figures/fig_fairall_9_overview.pdf)

![Fairall 9 band by band. Hα at 6866 Å is at 70 % transmission in LCO r′ but 6 % in SDSS r: 20 % of the LCO r′ flux is Hα, but only 6 % of the SDSS r flux, giving +175 mmag.](figures/fig_fairall_9_bands.pdf)

![Fairall 9 per-spectrum corrections (47 nights). r scatters by 7 mmag and changes by −83 mmag per dex of continuum/[O III].](figures/fig_fairall_9_epochs.pdf)

## 6.4 All targets

Line fractions are the share of the band's flux from emission lines, LCO / reference. Systematics
and epoch scatter are added in quadrature.

| target | band | true − AVA (mmag) | lines only | line fraction (%) | F_true/F_AVA | natural − AVA |
|---|---|---|---|---|---|---|
| Mrk 817 | B | −26 ± 4 | −8 | 6 / 7 | 1.024 | −23 |
| | g | −31 ± 11 | −9 | 11 / 11 | 1.029 | −15 |
| | V | +47 ± 19 | +22 | 14 / 12 | 0.957 | +21 |
| | r | +138 ± 19 | +129 | 27 / 18 | 0.880 | −2 |
| | i | +4 ± 4 | +1 | 5 / 5 | 0.997 | 0 |
| NGC 4151 | B | −24 ± 2 | −2 | 13 / 13 | 1.023 | −19 |
| | g | −45 ± 7 | −42 | 21 / 24 | 1.042 | −5 |
| | V | +78 ± 14 | +86 | 22 / 16 | 0.931 | +9 |
| | r | −48 ± 7 | −59 | 32 / 36 | 1.045 | +1 |
| | i | 0 ± 1 | −3 | 0 / 0 | 1.000 | +1 |
| Fairall 9 | B | −28 ± 2 | −5 | 6 / 6 | 1.026 | −21 |
| | g | −25 ± 3 | −14 | 11 / 12 | 1.024 | −10 |
| | V | +27 ± 7 | +16 | 14 / 13 | 0.976 | +15 |
| | r | +181 ± 9 | +175 | 20 / 6 | 0.846 | −1 |
| | i | 0 ± 1 | −2 | 13 / 13 | 1.000 | +1 |

![Left: the reference-system correction per target and band (error bars: systematics and epoch scatter in quadrature; grey band: ±5 mmag, the stellar accuracy). Right: the shift to the LCO natural system.](figures/fig02_summary.pdf)

**u and z are not reliable yet.**

- **u.** The synthetic stellar transform fails: the Pickles scatter is 59 mmag, and the synthetic
  C = 0.17 against an empirical 0.057 ± 0.034. The spectra also need a template below 3350 Å. The u
  values (+37 to +78 mmag) are indicative only.
- **z.** SDSS z extends beyond FLOYDS coverage, the red end of the spectra is noisy even after the
  fringe correction, and the continuum fit is unstable there. The values are −90, −33 and −25 mmag,
  with 33–46 mmag scatter from epoch to epoch.

# 7. Validation

## 7.1 Do the synthetic passbands reproduce the stellar colour terms?

| | u | B | g | V | r | i | z |
|---|---|---|---|---|---|---|---|
| C synthetic (Pickles) | +0.170 | +0.015 | +0.038 | −0.046 | +0.014 | +0.004 | −0.036 |
| C empirical (Mrk 817 field) | +0.057 ± 0.034 | −0.032 ± 0.007 | +0.045 ± 0.004 | −0.010 ± 0.004 | +0.016 ± 0.003 | +0.027 ± 0.003 | −0.035 ± 0.007 |
| LCO shift needed (Å) | – | −67 | +13 | +90 | +7 | +85 | +4 |

![Synthetic stellar colour term against a wavelength shift of the LCO passband, with the empirical value.](figures/fig04_tuning.pdf)

- **g, r and z agree,** with shifts of 4–13 Å. The r result, the largest correction, rests on curves
  the stars validate.
- **B, V and i do not.** Shifts of 70–90 Å are implausible for the real filters. The likely causes:
  - GSPC's "standardised" JKC and SDSS systems are not exactly the nominal Landolt/SDSS curves;
  - the LCO curves lack the mirrors;
  - the empirical C averages over 13 cameras, some with per-camera colour terms.
- **Effect on the results.** Shifting the curves changes the B and V corrections by 30–100 mmag and
  i by −18 to −71 mmag. The i case is Fairall 9, where Hα sits on the i blue edge. These are bounds
  on how wrong the B/V/i passbands could be, not best estimates. The *line parts* depend only on
  where the edges are.

## 7.2 Same-night photometry against the spectrum (Mrk 817, 13 Aug 2026)

Two spectra, with Sinistro photometry within 0.6 d. A grey slit loss cancels in colours; host light
in the 10.5″ aperture against the slit extraction does not.

| colour | AVA observed | AVA predicted from spectrum | true reference colour | observed − predicted | observed − true |
|---|---|---|---|---|---|
| g−V | 0.039 | 0.057 | −0.017 | −18 | +56 |
| r−i | 0.011 | 0.015 | 0.137 | −4 | **−125** |
| i−z | 0.168 | 0.158 | 0.266 | +10 | −98 |
| V−r | 0.317 | 0.193 | 0.113 | +124 | +204 |
| g−r | 0.356 | 0.250 | 0.096 | +106 | +260 |

![Colour differences: AVA's prediction from the spectrum (blue) and the true reference-system colour (orange), each minus the observed AVA colour. Shaded: colours pairing the blue part of the spectrum (g, V) with the red part (r).](figures/fig05_photometry_check.pdf)

- **Colours within the blue part (g−V) or within the red part (r−i, i−z)** match AVA's prediction to
  4–18 mmag. They do not match the true SDSS/Landolt colours (off by 56–125 mmag). This confirms the Hα
  term in r with real data. Using the fringe-corrected orders matters here: with the merged, fringed
  spectrum i−z was off by 52 mmag, now 10.
- **Colours that pair g or V with r** are off by 0.11–0.12 mag: the spectrum is bluer than the
  photometry. It is not an order-splice step (the measured red/blue ratio for these spectra is
  0.98–1.00). It is not host light alone either: extra host in the 10.5″ aperture would redden r−i too,
  and r−i matches.
  - The pattern, g and V together against r and i together, fits a flux-scale error in the red order
    over about 5300–7000 Å. The FLOYDS sandbox notes list candidates: the lamp-flat slit-profile factor
    (±10 % at 5000–7000 Å, finding 43) and flat-field structure in the fringe map applied from about
    5000 Å (finding 40).
  - The corrections in this report depend only on the shape *within* each band, so a grey offset
    between the orders matters only for bands that straddle 5300 Å (g, V). Scaling the red order by 0.9
    changes them by about 5 mmag (g) and 10–13 mmag (V).
  - **To do with the full reduction:** repeat this comparison on every night that has both a spectrum
    and photometry. It is a free check of the spectral flux calibration.

## 7.3 Reduction, flux-calibration slope and STDFAR

- **Reduction.** Archive BANZAI against AVA's reduction (Mrk 817, 5 spectra): B −3, g −9, V +16,
  r +15 and i −4 mmag.
- **Fringe correction.** Fringe-corrected orders against the merged, fringed `SPECTRUM`: B to i change
  by ≤ 3 mmag; z by 9–34 mmag.
- **Slope.** A ±5 % per 1000 Å tilt changes the corrections by ≤ 7 mmag (r ≤ 6, V ≤ 7).
- **STDFAR.** STDFAR spectra agree with the others within 1–9 mmag (Fairall 9 r: 187 against
  179 mmag).

# 8. Error budget (mmag, median over spectra)

| | B | g | V | r | i |
|---|---|---|---|---|---|
| epoch scatter (1σ) | 1–2 | 2–5 | 3–9 | 7–11 | 1 |
| flux-calibration tilt ±5 %/1000 Å | 1 | 2 | 5–7 | 1–6 | 0 |
| order ratio (measured, per spectrum) | 0 | 1–4 | 1–7 | 0 | 0 |
| red-order scale −10 % (section 7.2, not included) | 1 | 5 | 10–13 | 0 | 0 |
| reduction (Mrk 817: archive against AVA) | 3 | 9 | 16 | 15 | 4 |
| AGN colour, photometric or spectral (Mrk 817) | 2 | 6 | 7 | 2 | 1 |
| fringe-corrected against merged spectrum | 0 | 0–1 | 0–2 | 0–2 | 1–3 |
| *passband tuning (bound, not included)* | *30–58* | *3–6* | *27–103* | *2–7* | *18–71* |

- **Not included:** the host fraction in the slit against the photometric aperture (it dilutes the line
  contrast differently in the slit and in the aperture; not quantified), and the MuSCAT,
  SBIG and Spectral passbands. Their curves are not on disk, and their line terms differ from
  Sinistro's.

# 9. Dependence on redshift and AGN state

![Each target's spectrum moved in redshift from 0 to 0.2: the correction depends on where the lines fall relative to the filter edges. The r term peaks at +180 to +270 mmag for z = 0.04–0.05 (Hα at the SDSS r edge); g reaches +80 mmag at z ≈ 0.09 for NGC 4151's [O III]; i swings ±40 mmag for z = 0.05–0.10.](figures/fig03_redshift.pdf)

Of the 98 AVA targets with a redshift in `ava.db`, 52 have z < 0.05 and 28 have 0.05–0.1, so most
have Hα or [O III] near an edge somewhere.

| target | band | correction change per dex of F(5100 Å)/F([O III]) | range covered (dex) |
|---|---|---|---|
| Mrk 817 (3 nights) | r | −228 mmag | 0.12 |
| Mrk 817 (3 nights) | V | −91 mmag | 0.12 |
| NGC 4151 | V | −185 mmag | 0.21 |
| NGC 4151 | g | +102 mmag | 0.21 |
| NGC 4151 | r | +59 mmag | 0.21 |
| Fairall 9 | r | −83 mmag | 0.19 |
| Fairall 9 | V | −27 mmag | 0.19 |

Over these campaigns that amounts to 5–40 mmag (NGC 4151 V the largest). A season-level correction is adequate; an
outburst of a factor of several would need per-epoch corrections.

# 10. What to do

1. **Publish the AGN photometry in the LCO natural AB system** (primary product).
   - The zero point comes from GSPC as now. The AGN magnitude is shifted by
     $\delta_\mathrm{nat} = -(a + C\,c_\mathrm{AGN})$: B −19 to −23, g −5 to −15, V +9 to +21,
     r −2 to +1, i 0 to +1 mmag here.
   - That shift needs the absolute offset $a$ from the passbands, which is reliable now in g, r and z.
     B, V, i and u need better curves first: mirrors, and per-camera curves for MuSCAT, SBIG and
     Spectral.
   - Publish the passbands with the data (already on the website, `ava_lco_filters.zip`).
2. **Reference-system fluxes as a derived product,** for SED work and survey comparison:
   $F_\mathrm{ref} = F_\mathrm{AVA}\cdot 10^{-0.4\,\delta_\mathrm{ref}}$, using the per-target, per-season
   median of the spectral corrections (table in section 6.4).
   - Where the AGN varies strongly, interpolate the per-epoch correction in time.
   - For targets without spectra, flag the reference-system values as uncorrected. The redshift
     curves (figure in section 9) show the size of the error.
3. **Pipeline integration (proposal, after the full spectral reduction):**
   - a step after the spectroscopy products that runs `agn_sed_corrections.py` per target and writes
     a table (target, band, season, $\delta_\mathrm{ref}$, $\delta_\mathrm{nat}$, systematics);
   - the merged light-curve export then gains natural-system columns, and optionally
     reference-system columns.
4. **Before relying on B, V, i and u at the 1 % level:**
   - get passbands per camera family, including mirrors;
   - resolve the colour-term mismatch (section 7.1), for example with GSPC's own standardisation
     relations;
   - add a UV extension for u.
5. **Spectral pipeline:**
   - investigate the 0.11 mag blue-against-red flux scale found against same-night photometry
     (section 7.2);
   - use the fringe-corrected `EXTRACTED` orders, never the merged `SPECTRUM`, for anything photometric.
6. **Stars:** keep the GSPC anchor and the current settings. Flag targets that fall back to APASS.

# 11. Reproducing and re-running (all reduced spectra)

The scripts are in `tools/abscal_validation/`. Python: the `stenv` environment (pandas, pyarrow,
astropy, scipy, click). Paths come from `config/ava_config.yaml` (`AVA_CONFIG`). The Pickles library
and the AGN template come from the synphot tree (`PYSYN_CDBS`).

```bash
export PYSYN_CDBS=/path/to/synphot/trds
python tools/abscal_validation/agn_sed_corrections.py --out <work>
python tools/abscal_validation/sed_photometry_check.py --sed <work> --out <work>
python tools/abscal_validation/abscal_ps1_apass.py <work>/ext
python tools/abscal_validation/report_figs.py --ext <work>/ext --sed <work> --out docs/reports/abscal/figures
```

- `agn_sed_corrections.py` picks up every target with reduced `-1d` spectra under `spectra_root`
  (`--target` restricts the list). The figures script makes one overview, one band and one epoch
  figure per target.
- The star-based checks are `abscal_trends.py`, `abscal_sensitivity.py`, `abscal_ps1_apass.py` and
  `tools/check_absolute_calibration.py`.
- Numbers behind this report: `sed_corr_summary.csv`, `sed_corr_transform.csv` and
  `sed_photometry_check.csv` in this folder.
