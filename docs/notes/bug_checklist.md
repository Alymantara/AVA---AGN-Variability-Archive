# AVA bug checklist

This is the single list of every known bug, in the order to work through them. Tick an item by changing `[ ]` to `[x]`
and adding the commit hash. Details, evidence and failure scenarios for B01–B18 and the C items are in
[bug_sweep_2026-11-18.md](bug_sweep_2026-11-18.md). The QC items are described in
[future_improvements.md](future_improvements.md).

**Owner:** *main* = this session (pipeline bug sweep); *QC* = the "Fix frame QC bugs" session.
**Done means:** an offline test reproduces the bug, the fix makes it pass, the full suite passes, and there is a
line in `future_improvements.md`.

## 1. High: fix first

- [x] **B01** (main, lcodb; fixed in `797debc`; also: headers reduced to the slit width, stored headers purged on the Mac): a repeated HTTP 500 is retried 7×, and the header step never stops. This could exceed
  the 5000 requests/day limit. `ava/lcodb/api.py:96`, `ava/lcodb/headers.py:43`.
- [x] **B02** (main, ensemble; fixed 19 Nov, see the B02 commit; = B3ₚ of the PyTICS test-archive run): the ensemble task crashes when no camera gets an intercalibration fit (single camera,
  fewer than 10 overlap nights, MuSCAT only). `ava/pipeline/tasks/ensemble.py:46`.

## 2. Medium

- [x] **B03** (main, spectroscopy; fixed 19 Nov, see the B03 commit; earlier reductions not redone): standards from another night are downloaded but never staged (39 % of spectra).
  `spectroscopy/download.py:117`, `reduce.py:109`.
- [ ] **B04** (QC): the `zp_offset` check uses the median ZP per camera *family*, not per camera, and drops all
  173 fa08 B frames. Needs a decision on fa08. `photometry/process.py:141`.
- [x] **B05** (main, ensemble; fixed 19 Nov, see the B05 commit): a run with no new frames re-runs the colour check against itself and writes a stale
  record. `photometry/ensemble.py:472`, `:699`.
- [ ] **B06** (main, spectroscopy): `spec_products` crashes when 5100 Å is not covered (z ≈ 0.095–0.114).
  `spectroscopy/products.py:126`.
- [ ] **B07** (main, spectroscopy): the latest-Hβ web plot crashes for z > 0.19 (6 targets). `spectroscopy/webplots.py:157`.
- [ ] **B08** (main, spectroscopy): Hβ is always fitted in the blue arm, so there is no Hβ for Mrk 876, 3C 273 or
  PDS 456 (z ≳ 0.11). `spectroscopy/lines.py:79`, `products.py:84`.
- [x] **B09** (main, lcodb; fixed in `797debc` with B01): a run of short 429s makes `Client.get` return `None`. `lcodb/api.py:85`.
- [ ] **B10** (main, lcodb): `sync --proposal A B` silently drops B when discovery doesn't list it. `lcodb/ingest.py:196`.
- [ ] **B11** (QC): `MAG_APER = 99` rows go into `measurements.parquet` and PyTICS. `photometry/catalogs.py:228`,
  `process.py:91`.

## 3. Low

- [x] **B12** (main, ensemble; fixed 19 Nov with B4ₚ, same commit as B02): a failed g or i absolute ZP makes the ZP of every filter NaN.
  `photometry/ensemble.py:845`.
- [ ] **B13** (main, lcodb): `sync --proposal ID` skips an inactive proposal that was already crawled. `lcodb/ingest.py:215`.
- [ ] **B14** (main, photometry): a GSPC star within 2″ can be relabelled as the AGN. `photometry/reference.py`
  (`assign_star_ids`).
- [ ] **B15** (main, photometry): R/I frames with an APASS-fallback catalogue raise `KeyError 'lco_R'`.
  `photometry/calibration.py:41`.
- [ ] **B16** (QC): a NaN `saturate`/`naxis` rejects every standard, so the frame silently gets `no_zp`.
  `photometry/calibration.py:76`.
- [ ] **B17** (QC): frames that raised an exception are never retried. `photometry/process.py:227`.
- [ ] **B18** (main, photometry): "newest first" in SExtractor sorts by site, not by date. `pipeline/tasks/sextract.py:56`.

## 4. QC items already opened by the QC session

- [ ] **QC-0001** (QC): sparse fields fail `min_matched: 30` (PG 2304+043: 0 % pass); fields with few GSPC u
  stars get no u zero point (MR 2251-178).
- [x] **QC-0002** (QC): reference positions rounded to 6 significant figures. Fixed in `0d3024f`; turgon
  follow-up `a1f6fed`.
- [ ] **QC-0003** (QC): model u for GSPC stars without a validated u. **On hold (user, 18 Nov)**: the commit was
  undone on purpose and the changes are uncommitted in the working tree. Waits for updated model atmospheres.
- [ ] **QC test** (QC): frame QC on the PyTICS input, running in its own session (Test frame QC on PyTICS input).

## 5. To confirm (decision or unverified; tick when decided)

- [ ] **C01**: `nightly_steps` has no `pytics`, so the scheduled run never updates the ensemble light curves.
  Intended? `config/ava_config.yaml:578`.
- [ ] **C02**: `merge` (`-m`/`-s`) raises `NotImplementedError`. Remove the flags or port the step?
- [ ] **C03**: AVA ignores `LCODB_CONFIG` (`ava/config.py:248`). Matters on the host if only that variable is set.
- [ ] **C04**: cleanup can delete a standard that an unreduced night elsewhere still needs (`archive/cleanup.py:291`).
  Fix together with B03.
- [ ] **C05**: signed S3 URLs (valid 48 h) appear in download error logs.
- [ ] **C06**: the spectra download filter has no instrument check (a SOAR spectrum with the same target name would be kept).
- [ ] **C07**: `arm_offsets` keeps stale offsets after the `align_*` settings change.
- [x] **C08** (fixed with B12: capped at 0.5 mag): `errors.fit_s_cam` (`brentq` up to 0.5 mag) can raise.
- [ ] **C09**: `colour_term_check` ignores `intercal_min_pairs`; `run_target` hard-codes `g − i`.
- [ ] **C10**: fa08 `up` gets no zero point (0 of 172 frames). Hardware or a U/up label? (Look at it together with B04.)
- [ ] **C11**: stars with NaN RUWE pass `quality_ok`.
- [ ] **C12**: the website's `ava_stats()` sums over all targets, without the target filter.

## Already fixed elsewhere (for reference)

- [x] PyTICS crashes from the first host run: empty pyarrow filter, missing `pytics/` folder, a target without
  photometry (`f1adb46`).
- [x] Stale `meta.colour_check` on Mrk 817, refreshed by a full refit (18 Nov). B05 is the cause and is still open.
