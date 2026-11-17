# Supplied LCO target list vs the AVA catalogue (17 Nov 2026)

* **Input:** `tools/new_targets/lco_epoch_list_2026-11-16.tsv` (207 entries: name, ra, dec, type, z, approximate
  epochs).
* **Corrections:** `tools/new_targets/lco_epoch_list_2026-11-16_fixes.yaml`.
* **Command:** `python tools/target_list_crossmatch.py tools/new_targets/lco_epoch_list_2026-11-16.tsv --count-frames`
* **Full table:** `tools/new_targets/lco_epoch_list_2026-11-16_xmatch.csv`. It has best positions (`ra_best`,
  `dec_best`, `pos_source`), Gaia DR3 ids and LCO frame counts.

The tool reads `data/ava.db` and the lcodb mirror read-only and makes no LCO archive requests.

* **Positions:** the Gaia DR3 nucleus comes from the ESA Gaia archive (TAP). The CfA VizieR mirror missed sources
  0.2–1.6″ from the cone centre, so it is used only as a fallback.
* **Names:** names were resolved with NED in the cross-match, because CDS (Sesame) was down on 17 Nov. The
  additions used the CfA Sesame mirror. Re-run with `--refresh` once
  CDS is back to get SIMBAD object types.

| category | n | meaning |
|---|---|---|
| in_ava | 75 | already in `agn` |
| candidate | 100 | AGN not in AVA, with a Gaia DR3 counterpart (≤5″) |
| duplicate | 9 | another spelling, or a bad/offset position, of a list entry (see fixes YAML) |
| sdss_rm | 11 | SDSS-RM field: set aside |
| non_agn | 11 | calibrators, SN hosts and transients, NGC 2419, XTE J1550, "test" |
| no_counterpart | 1 | SDSS2350m09 (z = 1.50, 2 epochs): no Gaia source within 60″, position unverified |

## Added to `ava.db` (17 Nov 2026)

* **Added:** 18 nearby AGN (ids 82–99), from `tools/new_targets/2026-11-17.yaml` with
  `tools/add_ava_targets.py --write`. The database was backed up first to
  `data/backups/ava_20261117T071145_before_add_targets.db`.
* **Sources:** positions are the Gaia DR3 nucleus (≤ 0.2″), and z comes from SIMBAD through the CfA Sesame mirror,
  or from NED where SIMBAD has no redshift.
* **Linking:** after insertion, `python -m ava.lcodb link` and `python tools/ava_crossmatch.py` linked the LCO
  frames.
* **Not added:** Mrk 668, Mrk 374, Fairall 1139 and CBS 74 have no frames in AVA's proposals.
* **SDSS-RM:** these objects are not part of the project. The SDSS-RM201/562 rows were left as they are.

LCO numbers in `agn_lco` after linking (images = imaging frames; FLOYDS = epochs / frames):

| id | name | z | LCO names | images | visits | span | cadence (d) | FLOYDS |
|---|---|---|---|---|---|---|---|---|
| 83 | RBS 1303 | 0.0418 | RBS1303, k2f6-01 | 601 | 170 | 2015-07 → 2017-05 | 1.6 | 10 / 10 |
| 86 | RBS 1917 | 0.0659 | RBS1917 | 361 | 183 | 2016-04 → 2017-01 | 1.0 | 0 |
| 87 | PG 2209+184 | 0.0696 | PG2209+184 | 346 | 174 | 2016-04 → 2017-01 | 1.0 | 0 |
| 82 | RX J2044.0+2833 | 0.0493 | RXSJ20440+28 | 335 | 169 | 2016-03 → 2016-12 | 1.0 | 26 / 26 |
| 85 | PG 2214+139 | 0.0654 | PG2214+139 | 310 | 156 | 2016-05 → 2016-12 | 1.0 | 0 |
| 84 | NGC 4748 | 0.0141 | NGC4748 | 307 | 156 | 2016-12 → 2017-08 | 1.0 | 0 |
| 88 | Mrk 315 | 0.0395 | Mrk315 | 274 | 138 | 2016-05 → 2017-01 | 1.0 | 0 |
| 92 | SBS 1518+593 | 0.0781 | SBS1518+593 | 255 | 133 | 2016-02 → 2017-04 | 1.8 | 2 / 2 |
| 90 | Mrk 684 | 0.0460 | Mrk684 | 254 | 130 | 2016-02 → 2017-05 | 2.2 | 2 / 2 |
| 99 | NGC 5273 | 0.0036 | NGC5273, NGC 5273 | 243 | 13 | 2017-06 (3 nights) | – | 1 / 2 |
| 89 | NPM1G +27.0587 | 0.0619 | NPM1G+27.058 | 233 | 121 | 2016-02 → 2016-12 | 2.0 | 3 / 3 |
| 91 | Mrk 1392 | 0.0360 | Mrk1392 | 231 | 117 | 2016-02 → 2017-05 | 3.0 | 1 / 1 |
| 93 | Mrk 662 | 0.0552 | Mrk662 | 131 | 68 | 2016-02 → 2016-08 | 2.8 | 6 / 6 |
| 94 | Mrk 1501 | 0.0894 | Mrk1501 | 125 | 63 | 2016-12 → 2018-02 | 4.7 | 0 |
| 95 | NGC 3516 | 0.0087 | NGC3516 | 51 | 26 | 2017-02 → 2017-06 | 5.0 | 0 |
| 96 | Mrk 352 | 0.0146 | Mrk352 | 46 | 23 | 2014-08 → 2014-09 | 1.1 | 21 / 21 |
| 97 | Pox 52 | 0.0218 | POX052, Pox 52 | 37 | 21 | 2016-11 → 2025-02 | 3.6 | 0 |
| 98 | 3C 445 | 0.0561 | 3c445 | 24 | 12 | 2016-04 → 2016-05 | 3.0 | 0 |

SIMBAD types differ for some of these:

* PG 2209+184 is listed as BL Lac and Mrk 1501 as a blazar.
* Pox 52 is listed as Sy2.
* All the others are Sy1.

Still to do for these targets: AGN_type and literature values (logM, L5100), and Vmag from the merged g band, as for
the 16 Nov additions.

## Coordinate corrections

Offsets of a few arcsec from Gaia are accepted, and the CSV gives the Gaia position in `ra_best`/`dec_best`.

**List entries:** corrected in the fixes YAML; the original values are kept in `orig_ra`/`orig_dec`.

* **Duplicates:**
  * k2f601 is k2f6-01 with the Dec sign flipped, and k2f604/k2f605 are k2f6-04/05 at wrong positions (same LCO
    frame counts).
  * k2f6-01 is RBS1303.
  * HS0817+1215 is HS0817+1315.
  * J08152+1855 is a name typo for SDSS J08512+1855.
  * 2MASSJ09218+1758 and SDSSJ09090+1330 are 39′ and 44′ off (old or offset pointings) from 2MASS J09218+1758 and
    SDSS J09090+1330.
  * Q2237+0305_offs is an offset pointing of Q2237+0305.
* **Lensed quasars listed at offset pointings, moved to the Gaia nucleus or brightest image:**
  * HE 0047-1756 (1.4′)
  * Q 0142-100 = UM 673 (125″)
  * RX J1131-1231 (2.1′)
  * WFI J2033-4723 (1.8′)
  * HE 0435-1223 (2.1′)
* **List position kept:** for NPM1G+27.058, 1224+04 and 1346+09, NED resolves the name to a different object
  (85°, 51′ and 43′ away), but the list position matches a Gaia source.

**SDSS-RM201/562 in `ava.db`:** these rows have no decimal coordinates, and their sexagesimal positions are about
1° from where LCO observed them. They are left unchanged because SDSS-RM is not part of the project.

## LCO frame counts (lcodb mirror, synced 16 Nov 2026; AVA's 6 proposals only)

How the counts were made:

* An entry's LCO OBJECT names are those within 3′ (in `target_link`).
* Imaging counts distinct exposures at rlevel 91, falling back to rlevel 90: frames from before mid-2016 exist only
  at rlevel 90. A frame counts if its footprint centre is within 12′.
* FLOYDS counts raw SPECTRUM frames whose pointing is within 6′.
* Nights = distinct DAY-OBS.

**Recommended nearby Seyferts:**

| object | phot exposures / nights | phot span | filter | FLOYDS frames / nights | G |
|---|---|---|---|---|---|
| RXSJ20440+28 | 335 / 158 | 2016-03 → 2016-12 | V | 26 / 18 | 15.6 |
| RBS1303 (+k2f6-01) | 580 / 155 | 2015-07 → 2017-05 | V, griz | 8 / 8 | 15.3 |
| NGC4748 | 307 / 133 | 2016-12 → 2017-08 | V | 0 | 15.2 |
| PG2214+139 (Mrk 304) | 310 / 132 | 2016-05 → 2016-12 | V | 0 | 14.6 |
| RBS1917 | 361 / 132 | 2016-04 → 2017-01 | V | 0 | 16.1 |
| PG2209+184 (II Zw 171) | 346 / 131 | 2016-04 → 2017-01 | V | 0 | 17.0 |
| Mrk315 | 274 / 119 | 2016-05 → 2017-01 | V | 0 | 16.8 |
| NPM1G+27.058 | 233 / 117 | 2016-02 → 2016-12 | V | 3 / 3 | 15.8 |
| Mrk684 | 254 / 117 | 2016-02 → 2017-05 | V | 2 / 2 | 15.2 |
| Mrk1392 | 231 / 114 | 2016-02 → 2017-05 | V | 1 / 1 | 15.8 |
| SBS1518+593 | 255 / 111 | 2016-02 → 2017-04 | V | 2 / 2 | 15.9 |
| Mrk662 | 131 / 64 | 2016-02 → 2016-08 | V | 6 / 6 | 16.3 |
| Mrk1501 | 125 / 45 | 2016-12 → 2018-02 | V | 0 | 16.1 |
| NGC3516 | 51 / 25 | 2017-02 → 2017-06 | V | 0 | 15.4 |
| Mrk352 | 46 / 21 | 2014-08 → 2014-09 | V | 21 / 21 | 16.2 |
| POX052 | 37 / 16 | 2016-11 → 2025-02 | V, ugriz | 0 | 17.6 |
| 3C 445 | 24 / 12 | 2016-04 → 2016-05 | V | 0 | 16.1 |
| NGC 5273 | 243 / 3 | 2017-06 | g | 2 / 1 | 16.3 |
| Mrk668, Mrk374, Fairall 1139, CBS 74 | 0 | – | – | 0 | 15.5–16.7 |

* The V-band LAMP-style campaigns (2016–17, about daily cadence) are the main value, and the photometry is V only.
  These targets have almost no FLOYDS spectra, except RXSJ20440+28 (18 nights) and Mrk352 (21 nights).
* Mrk668, Mrk374, Fairall 1139 and CBS 74 have no LCO OBJECT name near them in the mirror. They were observed (if
  at all) under proposals outside the mirror, which would need a live archive query.

**Other groups:**

* **z ≈ 0.3 quasars** (same programme as 1438+02):
  * 1435+02 has 598 exposures over 108 nights and 28 spectra over 21 nights.
  * The others have 12–32 g exposures over 6–17 nights and 4–28 spectra over 4–21 nights, from 2014–16.
* **K2 C16 field** (2017-11 → 2018-02, gri, about daily): SDSS J08512+1855 (100 nights), 2MASS J09218+1758 (80),
  SDSS J08410+1552 (66), SDSS J09090+1330 (61, G = 20.3), SDSS J09039+1829 (34), RXS J08383+2410 (28),
  SDSS J08431+2326 (26), HS 0843+2533 (25). There are no spectra.
* **K2 C3, C5, C6, C7 and C8 fields** (2014–16): 7–41 nights each over about 2-month campaigns, with 0–5 spectra.
* **High-z SDSS quasars (z ≈ 1.5):** 0–1 imaging nights in the mirror, and 1 spectrum each (SDSS1623p19 has 13).
  **Lensed quasars:** 0–1 frames in the mirror.
