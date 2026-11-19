<?php
declare(strict_types=1);
require __DIR__ . '/includes/layout.php';
require __DIR__ . '/includes/calibration.php';

$cal = ava_cal_load();
$targets = $cal['targets'] ?? [];
$bands = $cal['bands'] ?? ['B', 'g', 'V', 'r', 'i'];
$report = AVA_DATA_DIR . '/manuals/report_abscal.pdf';
$reportUrl = is_file($report) ? AVA_DATA_URL . '/manuals/report_abscal.pdf?v=' . filemtime($report) : null;
$jsonUrl = $cal ? AVA_DATA_URL . '/calibration/calibration.json?v=' . filemtime(AVA_DATA_DIR . '/calibration/calibration.json') : null;
$nSpec = array_sum(array_map(fn($t) => (int) $t['n_spectra'], $targets));

ava_page_start('data', 'Photometric calibration',
    'How AVA sets the absolute flux scale of its LCO light curves, how accurate it is for stars, and how emission lines make AGN magnitudes depend on the filter system.');
?>
<link rel="stylesheet" href="<?= asset('assets/css/calibration.css') ?>">
<div class="container-xxl ava-page-head">
  <nav aria-label="Breadcrumb">
    <ol class="ava-crumbs">
      <li><a href="data.php">Data</a></li>
      <li aria-current="page">Photometric calibration</li>
    </ol>
  </nav>
  <h1>Photometric calibration</h1>
  <p class="ava-lead">How the light curves get their absolute flux scale, how accurate that is, and why an AGN's
    magnitude depends on exactly which filter it was measured through.</p>
  <nav class="ava-toc" aria-label="On this page">
    <a href="#summary">In short</a>
    <a href="#method">How the zero point is set</a>
    <a href="#filters">Two filter systems</a>
    <a href="#stars">Accuracy for stars</a>
    <a href="#errors">Error bars</a>
    <?php if ($cal): ?><a href="#agn">AGN and emission lines</a>
    <a href="#corrections">Per-target corrections</a>
    <a href="#redshift">Redshift dependence</a><?php endif; ?>
    <a href="#status">Status &amp; caveats</a>
  </nav>
</div>

<section class="pb-5" id="summary">
  <div class="container-xxl">
    <div class="row g-4 ava-cal-cards">
      <div class="col-md-4"><div class="ava-cal-card">
        <p class="ava-eyebrow">Stars</p>
        <p class="big">≈ 3 mmag</p>
        <p>The zero points reproduce Gaia synthetic photometry, SDSS and Pan-STARRS to a few millimagnitudes in
          <em>g r i z</em>, with no trend in brightness, airmass, seeing, season or camera above ≈ 5 mmag.</p>
      </div></div>
      <div class="col-md-4"><div class="ava-cal-card">
        <p class="ava-eyebrow">AGN</p>
        <p class="big">2–18 %</p>
        <p>An AGN is not a star: strong emission lines (Hα, [O III]) can sit where the LCO and SDSS/Landolt filters
          differ. Its magnitude in the SDSS/Landolt systems can then differ from AVA's by up to ≈ 0.2 mag,
          depending on band and redshift.</p>
      </div></div>
      <div class="col-md-4"><div class="ava-cal-card">
        <p class="ava-eyebrow">What it means</p>
        <p class="big">Use the filter curves</p>
        <p>Lags, light-curve shapes and fractional variability are unaffected. For absolute fluxes, SED fits or
          comparison with other surveys, fold models or spectra through the
          <a href="data.php#filters">LCO filter curves</a>.</p>
      </div></div>
    </div>
  </div>
</section>

<section class="ava-section ava-section--alt" id="method">
  <div class="container-xxl">
    <div class="row g-4 g-lg-5">
      <div class="col-lg-7 ava-prose">
        <p class="ava-eyebrow">Method</p>
        <h2>How the zero point is set</h2>
        <p>The PyTICS ensemble (Vieliute et al. 2025) puts every frame, telescope and camera on a common relative scale
          using hundreds of comparison stars. The absolute scale comes from <strong>Gaia DR3 XP synthetic photometry</strong>
          (the GSPC) of the same stars: SDSS <em>u g r i z</em> and Johnson–Cousins <em>B V</em> (standardised on
          Landolt), converted to AB. One fit per filter, over all stars and epochs, gives the zero point and a colour term
          in <em>g − i</em>, because the LCO filters are not identical to the SDSS/Landolt ones.</p>
        <p>The colour term converts LCO magnitudes into the SDSS/Landolt systems. For stars this works to a few mmag,
          because a star's spectrum is smooth and its colour says how it looks through either filter. For the AGN the
          pipeline applies the same conversion at the AGN's colour, as if it were a star of that colour.</p>
      </div>
      <div class="col-lg-5">
        <div class="ava-callout ava-callout--info">
          <p class="mb-2"><strong>Two ways to state an AGN magnitude</strong></p>
          <p class="mb-2 small"><strong>Reference system</strong> (SDSS/Landolt): what an SDSS or Landolt filter would
            have measured. Needs the stellar conversion, which an emission-line spectrum breaks.</p>
          <p class="mb-0 small"><strong>LCO natural system</strong>: what the LCO filter measured, on the same Gaia-based
            AB scale. Exact for any spectrum, provided the filter curve is known.</p>
        </div>
      </div>
    </div>
  </div>
</section>

<?php if ($cal): ?>
<section class="ava-section" id="filters">
  <div class="container-xxl">
    <p class="ava-eyebrow">Filters</p>
    <h2 class="mb-2">Two filter systems</h2>
    <p class="text-secondary mb-4" style="max-width:80ch">LCO filters (solid; filter × Sinistro CCD × atmosphere at
      airmass 1) against the passbands that define the Gaia anchors' magnitudes (dashed), each normalised to its peak.
      Shaded: where the LCO filter transmits. An emission line on the edge where only one of them transmits changes the
      AGN's magnitude in one system and not the other. <em>Y</em> is anchored to Pan-STARRS <em>y</em>, which is
      ≈ 300 Å bluer than LCO <em>Y</em>: there the colour term carries more of the conversion, even for stars.</p>
    <div class="ava-cal-grid">
      <?php foreach ($cal['passbands'] as $b => $pb): ?>
        <figure class="ava-chart-wrap m-0"><?= ava_cal_passband_svg((string) $b, $pb) ?>
          <figcaption class="ava-figcap">Half power: LCO <?= number_format($pb['lco_half'][0]) ?>–<?= number_format($pb['lco_half'][1]) ?> Å;
            <?= h($pb['ref_name']) ?> <?= number_format($pb['ref_half'][0]) ?>–<?= number_format($pb['ref_half'][1]) ?> Å</figcaption>
        </figure>
      <?php endforeach; ?>
    </div>
  </div>
</section>
<?php endif; ?>

<section class="ava-section ava-section--alt" id="stars">
  <div class="container-xxl">
    <div class="row g-4 g-lg-5">
      <div class="col-lg-6 ava-prose">
        <p class="ava-eyebrow">Stars</p>
        <h2>Accuracy for stars</h2>
        <p>Test field: Mrk 817. The calibrated comparison stars against catalogues AVA never uses, evaluated at the AGN's
          colour:</p>
        <ul>
          <li>No trend with magnitude (1–6 mmag per mag), airmass (≤ 5 mmag), seeing (≤ 2 mmag per arcsec),
            season (1–3 mmag) or camera (1–3 mmag; <em>z</em> 7).</li>
          <li>The fit settings (sigma clip, error floor, star variability cut) move the zero point by ≤ 5 mmag.</li>
          <li>Each merged light curve states its band's zero-point uncertainty in the column <code>zp_err_mag</code>
            (typically 1–10 mmag). It is shared by every epoch of the band, so it is <em>not</em> part of the per-epoch
            errors: it does not affect lags or variability, only absolute fluxes. Since 19 November 2026 the zero point
            uses every star in the frames, not only the ensemble's comparison stars, which fixes fields where the
            brightest stars are too bright for Gaia's SDSS/PS1 photometry and the shallow <em>Y</em> band.</li>
          <li><em>B</em> and <em>V</em> agree with GSPC by construction, but no independent catalogue on the Landolt
            system is good enough to check them below ≈ 20–25 mmag. APASS DR9 is off by 0.03–0.17 mag in this field.</li>
        </ul>
      </div>
      <div class="col-lg-6">
        <?php if (!empty($cal['stars'])): ?>
        <div class="ava-table-wrap" style="max-height:none">
          <table class="table ava-table mb-0">
            <caption class="px-3 small text-secondary">Offset of AVA star zero points at the AGN colour (mmag).
              PS1 column corrected for the PS1 − Gaia system difference measured on the same stars.</caption>
            <thead><tr><th>Band</th><th class="num">AVA − SDSS DR16</th><th class="num">AVA − Pan-STARRS DR2</th></tr></thead>
            <tbody>
              <?php foreach ($cal['stars'] as $b => $row): ?>
                <tr>
                  <th scope="row" style="--c: var(<?= ava_filter_var((string) $b) ?>)"><span class="ava-filter-dot"></span><?= h(ava_cal_band_label((string) $b)) ?></th>
                  <?php foreach (['sdss', 'ps1'] as $c): ?>
                    <td class="num"><?= isset($row[$c]) ? ava_mmag($row[$c][0]) . ' ± ' . (int) round(1000 * $row[$c][1]) : '–' ?></td>
                  <?php endforeach; ?>
                </tr>
              <?php endforeach; ?>
            </tbody>
          </table>
        </div>
        <?php endif; ?>
      </div>
    </div>
    <?php $sr = $cal['star_residuals'] ?? null; if ($sr): ?>
    <h3 class="h6 mt-5 mb-2">Star by star</h3>
    <p class="text-secondary small mb-3" style="max-width:80ch">Vertical axis: Gaia − AVA in mmag, for each comparison star in the <?= h(str_replace('_', ' ', (string) ($sr['target'] ?? ''))) ?>
      field (Gaia synthetic magnitude minus AVA's mean calibrated magnitude). Open circles were rejected by the
      zero-point fit's clipping; the line joins the medians in 1-mag bins. These are the stars the zero point is fitted
      to, so the median sits near zero by construction: the test is that it stays there from bright to faint stars.
      It does, within ≈ 5 mmag, except the faintest bin in <em>B</em> and <em>V</em> (10–15 mmag high, few stars and
      the noisiest Gaia magnitudes; the trend is in the technical report).
      The per-star scatter (σ, robust), about 10 mmag (<em>u</em> ≈ 30), is mostly the uncertainty of the Gaia
      synthetic magnitudes themselves. The independent check is the table above. Points beyond ±50 mmag are drawn at
      the edge.</p>
    <div class="ava-cal-grid ava-cal-grid--z">
      <?php foreach (['u', 'B', 'g', 'V', 'r', 'i', 'z'] as $b): if (empty($sr[$b])) continue; ?>
        <div class="ava-chart-wrap m-0"><?= ava_cal_stars_svg($b, $sr[$b]) ?></div>
      <?php endforeach; ?>
    </div>
    <?php endif; ?>
  </div>
</section>

<section class="ava-section" id="errors">
  <div class="container-xxl">
    <div class="row g-4 g-lg-5">
      <div class="col-lg-6 ava-prose">
        <p class="ava-eyebrow">Per-epoch errors</p>
        <h2>How good are the error bars?</h2>
        <p>Two exposures of the same AGN taken minutes apart with the same camera should differ only by noise. AVA uses
          <?= number_format(89168) ?> such back-to-back pairs of 29 AGN, and 8.1 million pairs of comparison stars as a
          control, to test the per-epoch errors and to fit them:</p>
        <p class="text-center">σ² = (k σ<sub>phot</sub>)² + (β rms<sub>t</sub>)² + s<sub>0</sub>² + s<sub>cam</sub>²</p>
        <ul>
          <li><strong>k ≈ 1.07</strong>: SExtractor's photometric error is slightly underestimated.</li>
          <li><strong>β ≈ 0.11</strong>: only a small part of the ensemble's epoch scatter (rms<sub>t</sub>) is noise
            on the AGN; most of it is already in the photometric error.</li>
          <li><strong>s<sub>0</sub> ≈ 1.1 mmag</strong>: a floor. Bright sources never scatter less than this, however
            many photons are collected (left panel). It matters for the brightest AGN, whose photometric errors are
            below 1 mmag.</li>
          <li><strong>s<sub>cam</sub></strong>: a per-filter term for points from different cameras, fitted on pairs
            taken by two cameras close in time.</li>
        </ul>
        <p>With these errors the normalised differences are Gaussian with width 1.00, for the AGN and for the stars
          (right panel), and the fit holds on nights not used to fit it. About 1 % of pairs lie beyond 3σ against
          0.3 % for a Gaussian. These tails come mostly from isolated events (cosmic rays, satellites, guiding),
          then from very bright epochs and from the MuSCAT, SBIG and Spectral cameras.</p>
      </div>
      <div class="col-lg-6">
        <figure class="ava-chart-wrap m-0">
          <img src="<?= asset('assets/img/calibration/error_floor.png') ?>" class="img-fluid rounded bg-white p-2"
               width="1283" height="573" loading="lazy"
               alt="Left: observed scatter per epoch against photometric error for Sinistro, levelling off at about 1 mmag. Right: distribution of normalised pair differences for AGN and comparison stars, matching a unit Gaussian in the core.">
          <figcaption class="small text-secondary mt-2">Sinistro cameras. Left: observed scatter per epoch against the
            photometric error; the model (green) levels off at the floor (dotted). Right: pair differences divided by
            the model errors, against a unit Gaussian (dashed).</figcaption>
        </figure>
        <h3 class="h6 mt-4 mb-2">The floor depends on the observation</h3>
        <div class="ava-table-wrap" style="max-height:none">
          <table class="table ava-table mb-0">
            <thead><tr><th>Condition</th><th>Floor s<sub>0</sub></th></tr></thead>
            <tbody>
              <tr><td>exposure ≤ 30 s / ≥ 60 s</td><td>1.5 / 0.95 mmag</td></tr>
              <tr><td>airmass 1.2 → 1.5–1.8</td><td>1.1 → 1.7 mmag</td></tr>
              <tr><td>seeing ≤ 1.5″ → 3–4″</td><td>1.0 → 1.7 mmag</td></tr>
              <tr><td>night to night (same camera)</td><td>± 0.4 mmag</td></tr>
            </tbody>
          </table>
        </div>
        <p class="small text-secondary mt-2">Short exposures and high airmass point to atmospheric scintillation. The
          light curves use the average floor; a per-epoch floor is under study.</p>
      </div>
    </div>
  </div>
</section>

<?php if ($cal): ?>
<section class="ava-section ava-section--alt" id="agn">
  <div class="container-xxl">
    <p class="ava-eyebrow">AGN spectra</p>
    <h2 class="mb-2">AGN and emission lines</h2>
    <p class="text-secondary mb-2" style="max-width:80ch">We fold <?= number_format($nSpec) ?> FLOYDS spectra through
      both sets of filters. Only the shape of the spectrum within each band matters, so slit losses cancel. Each
      chart shows a target's median spectrum (solid), its continuum fit (dotted) and, below, the LCO (solid) and reference
      (dashed) passbands. The numbers are the correction in mmag: the true SDSS/Landolt magnitude minus AVA's.</p>
    <p class="text-secondary mb-4 small" style="max-width:80ch">Spectra: 6″ slit, fringe-corrected, blue and red orders
      joined at 5300 Å. Hover over a band for details.</p>
    <?php foreach ($targets as $t): ?>
      <figure class="ava-chart-wrap" id="spec-<?= h($t['data_id']) ?>">
        <figcaption class="ava-cal-head">
          <strong><?= $t['ava_id'] ? '<a href="target.php?id=' . (int) $t['ava_id'] . '">' . h($t['name']) . '</a>' : h($t['name']) ?></strong>
          <span>z = <?= number_format((float) $t['z'], 4) ?> · <?= (int) $t['n_spectra'] ?> spectra, <?= (int) $t['n_nights'] ?> nights</span>
        </figcaption>
        <div class="ava-cal-specbox"><?= ava_cal_spectrum_svg($t, $cal['spectra'][$t['data_id']], $cal['passbands'], $bands) ?></div>
      </figure>
    <?php endforeach; ?>
    <div class="ava-prose mt-4">
      <p><strong>Reading the charts.</strong> In Mrk 817 (z = 0.031) and Fairall 9 (z = 0.046), Hα falls between the red
        edges of SDSS <em>r</em> (6730 Å) and LCO <em>r′</em> (6925 Å). LCO counts it fully; SDSS mostly does not, so the
        true SDSS <em>r</em> magnitude is 0.14–0.18 mag fainter. In NGC 4151 (z = 0.003), [O III] 5007 sits inside LCO
        <em>V</em> but on the edge of Landolt <em>V</em>: +0.08 mag. On a night with both a spectrum and photometry
        (Mrk 817), AVA's <em>r − i</em> matches the LCO-based prediction from the spectrum to 4 mmag, and differs from the
        true SDSS colour by 0.13 mag.</p>
    </div>
  </div>
</section>

<section class="ava-section" id="corrections">
  <div class="container-xxl">
    <p class="ava-eyebrow">Numbers</p>
    <h2 class="mb-2">Per-target corrections</h2>
    <p class="text-secondary mb-4" style="max-width:80ch">True reference-system (SDSS/Landolt) magnitude minus AVA's, in
      mmag, ± systematics and night-to-night scatter combined. Positive: AVA is too bright in that system. To convert AVA
      fluxes: F<sub>ref</sub> = F<sub>AVA</sub> × 10<sup>−0.4 δ</sup> (hover over a value for the factor). Corrections
      larger than 20 mmag are highlighted.</p>
    <div class="ava-table-wrap" style="max-height:none">
      <table class="table ava-table mb-0 ava-cal-table">
        <thead><tr><th>Target</th><th class="num">z</th><th class="num">Spectra</th>
          <?php foreach ($bands as $b): ?>
            <th class="num" style="--c: var(<?= ava_filter_var((string) $b) ?>)"><span class="ava-filter-dot"></span><?= h(ava_cal_band_label((string) $b)) ?></th>
          <?php endforeach; ?></tr></thead>
        <tbody>
          <?php foreach ($targets as $t): ?>
            <tr>
              <th scope="row"><?= $t['ava_id'] ? '<a href="target.php?id=' . (int) $t['ava_id'] . '">' . h($t['name']) . '</a>' : h($t['name']) ?></th>
              <td class="num"><?= number_format((float) $t['z'], 4) ?></td>
              <td class="num"><?= (int) $t['n_spectra'] ?></td>
              <?php foreach ($bands as $b): $v = $t['bands'][$b] ?? null; ?>
                <?php if ($v): $big = abs((float) $v['dref']) >= 0.02; ?>
                  <td class="num<?= $big ? ' big' : '' ?>" title="<?= h(sprintf('F_ref / F_AVA = %.3f; lines %d %% of the LCO band flux; LCO natural − AVA %s mmag',
                      $v['flux_factor'], (int) round(100 * $v['linefrac_lco']), ava_mmag($v['dnat']))) ?>">
                    <?= ava_mmag($v['dref']) ?> <span class="err">± <?= (int) round(1000 * $v['err']) ?></span></td>
                <?php else: ?><td class="num">–</td><?php endif; ?>
              <?php endforeach; ?>
            </tr>
          <?php endforeach; ?>
        </tbody>
      </table>
    </div>
    <p class="small text-secondary mt-3 mb-0"><em>u</em> and <em>z</em> are not shown: the synthetic stellar
      conversion fails in <em>u</em>, and the spectra do not cover the whole SDSS <em>z</em> band.
      <?php if ($jsonUrl): ?>Numbers behind this page: <a href="<?= h($jsonUrl) ?>" download>calibration.json</a>.<?php endif; ?></p>
  </div>
</section>

<section class="ava-section ava-section--alt" id="redshift">
  <div class="container-xxl">
    <p class="ava-eyebrow">Redshift</p>
    <h2 class="mb-2">Redshift dependence</h2>
    <p class="text-secondary mb-3" style="max-width:80ch">Each spectrum moved from z = 0 to 0.2: the correction depends on
      where the lines fall against the filter edges, not on the AGN itself. Dots mark each target's own redshift. Most
      AVA targets are at z &lt; 0.1. Hover over a panel to read values.</p>
    <div class="ava-chart-legend mb-3">
      <?php foreach (array_values($targets) as $k => $t): if ($k >= count(AVA_CAL_TARGET_VARS)) break; ?>
        <span><span class="sw" style="background: var(<?= AVA_CAL_TARGET_VARS[$k] ?>)"></span><?= h($t['name']) ?></span>
      <?php endforeach; ?>
    </div>
    <div class="ava-cal-grid ava-cal-grid--z">
      <?php foreach ($bands as $b): ?>
        <div class="ava-chart-wrap m-0"><?= ava_cal_zscan_svg((string) $b, $cal['redshift_scan'], $targets) ?></div>
      <?php endforeach; ?>
    </div>
  </div>
</section>
<?php endif; ?>

<section class="ava-section" id="status">
  <div class="container-xxl">
    <div class="row g-4 g-lg-5">
      <div class="col-lg-7 ava-prose">
        <p class="ava-eyebrow">Status</p>
        <h2>Status &amp; caveats</h2>
        <div class="ava-callout mb-3">
          <p class="mb-0"><strong>Current light curves</strong> use the stellar conversion at the AGN's colour, so their
            magnitudes are labelled as the SDSS/Landolt systems. <strong>Under review:</strong> publishing them in the LCO
            natural AB system, with the corrections on this page offered as a derived product.</p>
        </div>
        <ul>
          <li>First pass: three AGN with reduced spectra (<?= h(substr((string) ($cal['generated_utc'] ?? ''), 0, 10)) ?>).
            The table grows as the remaining FLOYDS spectra are reduced.</li>
          <li><em>B</em>, <em>V</em> and <em>i</em>: the filter curves do not yet reproduce the stellar colour terms
            measured from the data, so the continuum part of these corrections is uncertain by ≈ 20 mmag. The line part
            is not affected.</li>
          <li>MuSCAT, SBIG and Spectral cameras have their own filters. Their AGN offsets are absorbed by the
            intercalibration onto Sinistro, so the numbers here refer to Sinistro.</li>
          <li>The 6″ slit and the 10.5″ photometric aperture contain different amounts of host-galaxy light; not yet
            included.</li>
          <li>Errors: in <em>B</em> and <em>z</em> the cross-camera term s<sub>cam</sub> is still slightly too small,
            so points from different cameras scatter a little more than their error bars say.</li>
          <li>Saturation: since November 2026 frames in which the AGN's peak reaches 80 % of the camera's saturation
            level are dropped. This removes, for example, NGC 4151 on MuSCAT after its mirror was realuminised.</li>
        </ul>
      </div>
      <div class="col-lg-5">
        <h3 class="h6 mb-3">More detail</h3>
        <ul class="list-unstyled ava-cal-links">
          <?php if ($reportUrl): ?><li><a href="<?= h($reportUrl) ?>">Technical report (PDF)</a> — method, validation,
            error budget and all figures</li><?php endif; ?>
          <li><a href="data.php#filters">LCO filter curves</a> — download the transmission curves</li>
          <li><a href="data.php#format">File formats</a> — columns of the merged light curves</li>
          <li><a href="about.php#cite">How to cite</a> — AVA and PyTICS</li>
        </ul>
      </div>
    </div>
  </div>
</section>

<?php ava_page_end(['assets/js/calibration.js']); ?>
