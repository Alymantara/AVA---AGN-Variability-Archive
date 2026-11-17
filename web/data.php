<?php
declare(strict_types=1);
require __DIR__ . '/includes/layout.php';
require __DIR__ . '/includes/cite.php';
require __DIR__ . '/includes/charts.php';

$targets = ava_targets();
usort($targets, fn($a, $b) => (int) $b['db_lco_images'] <=> (int) $a['db_lco_images']);
$s = ava_stats();
$filters = ava_filters_published();
const AVA_FILTER_NAMES = ['u' => 'SDSS u′', 'B' => 'Bessell B', 'g' => 'SDSS g′', 'V' => 'Bessell V',
    'r' => 'SDSS r′', 'i' => 'SDSS i′', 'z' => 'Pan-STARRS zₛ', 'Y' => 'Pan-STARRS Y'];

ava_page_start('data', 'Data', 'AVA observing summary, download policy, file formats, LCO filter curves, how to cite and contact.');
?>
<div class="container-xxl ava-page-head">
  <h1>Data</h1>
  <p class="ava-lead">LCO imaging and FLOYDS spectroscopy for every AVA target, straight from the archive database:
    <?= number_format($s['images']) ?> photometric frames and <?= number_format($s['spectra']) ?> spectral epochs.</p>
  <nav class="ava-toc" aria-label="On this page">
    <a href="#summary">Observing summary</a>
    <a href="#access">Download policy</a>
    <a href="#format">File formats</a>
    <a href="#filters">LCO filters</a>
    <a href="#cite">How to cite</a>
    <a href="#contact">Contact</a>
  </nav>
</div>

<section class="pb-5" id="summary">
<div class="container-xxl">
  <h2 class="ava-h mt-0 mb-3">Observing summary</h2>
  <div class="ava-table-wrap">
    <table class="table table-hover ava-table" id="obs">
      <thead>
        <tr>
          <th scope="col" data-sort="text">AGN</th>
          <th scope="col" data-sort="text">Status</th>
          <th scope="col" class="num" data-sort="num">z</th>
          <th scope="col" class="num" data-sort="num">Phot. frames</th>
          <th scope="col" class="num" data-sort="num">Visits</th>
          <th scope="col" class="num" data-sort="num">Cadence (d)</th>
          <th scope="col" data-sort="text">Imaging span</th>
          <th scope="col" class="num" data-sort="num">Spectral epochs</th>
          <th scope="col" data-sort="text">Spectra span</th>
        </tr>
      </thead>
      <tbody>
        <?php foreach ($targets as $t): $st = ava_status($t); ?>
          <tr>
            <th scope="row"><a href="target.php?id=<?= (int) $t['id'] ?>"><?= h($t['name']) ?></a></th>
            <td><span class="ava-badge static ava-badge--<?= $st['key'] ?>"><?= $st['label'] ?></span></td>
            <td class="num"><?= fmt_num($t['redshift'], 4) ?></td>
            <td class="num"><?= fmt_int($t['db_lco_images']) ?></td>
            <td class="num"><?= fmt_int($t['db_lco_visits']) ?></td>
            <td class="num"><?= fmt_num($t['db_lco_cadence'], 2) ?></td>
            <td data-v="<?= h($t['db_lco_start']) ?>"><?= $t['db_lco_start'] ? h(substr($t['db_lco_start'], 0, 7) . ' → ' . substr((string) $t['db_lco_end'], 0, 7)) : '—' ?></td>
            <td class="num"><?= fmt_int($t['db_floyds_epochs']) ?></td>
            <td data-v="<?= h($t['db_floyds_start']) ?>"><?= $t['db_floyds_start'] ? h(substr($t['db_floyds_start'], 0, 7) . ' → ' . substr((string) $t['db_floyds_end'], 0, 7)) : '—' ?></td>
          </tr>
        <?php endforeach; ?>
      </tbody>
    </table>
  </div>
</div>
</section>

<section class="ava-section ava-section--alt" id="access">
  <div class="container-xxl ava-prose">
    <p class="ava-eyebrow">Download policy</p>
    <h2>Access to data products</h2>
    <p>Raw LCO frames are public through the <a href="https://archive.lco.global/">LCO Science Archive</a> once their
      proprietary period ends. Reduced AVA products — merged light curves and spectra — are currently available to
      members of the LCO Key Projects that obtained them, and will be released with the AVA data paper
      (Hernández Santisteban et al., in prep.).</p>
    <p>Released products are distributed under the
      <a rel="license" href="https://creativecommons.org/licenses/by-sa/4.0/">Creative Commons Attribution-ShareAlike 4.0</a> licence.</p>
    <div class="ava-callout ava-callout--info mt-3">
      Key Project members and collaborators can request access <a href="#contact">by email</a>.
    </div>
  </div>
</section>

<section class="ava-section" id="format">
  <div class="container-xxl">
    <p class="ava-eyebrow">File formats</p>
    <h2 class="mb-4">What you get</h2>
    <div class="row g-5">
      <div class="col-lg-6 ava-prose">
        <h3 class="h5">Photometry — merged light curves</h3>
        <p>One CSV file per AGN, <code>&lt;target&gt;_LCO_merged_lightcurve.csv</code>. All telescopes and cameras of
          the network are put on a common, absolute (AB) scale by the PyTICS ensemble calibration
          (Vieliute et al. 2025, <a href="https://doi.org/10.1093/rasti/rzaf021">RASTI, rzaf021</a>), so no further
          intercalibration is needed. Only epochs that pass quality control are included. Please
          <a href="#cite">cite PyTICS</a> together with AVA.</p>
        <table class="table ava-info">
          <thead><tr><th>Column</th><th>Content</th></tr></thead>
          <tbody>
            <tr><th>target</th><td>AVA identifier (data_id)</td></tr>
            <tr><th>MJD</th><td>Modified Julian Date, mid-exposure (days)</td></tr>
            <tr><th>filter</th><td>band: u, B, g, V, r, i, z, Y (see <a href="#filters">LCO filters</a>)</td></tr>
            <tr><th>telescope, camera</th><td>LCO telescope and camera codes of the frame</td></tr>
            <tr><th>flux_mJy, flux_err_mJy</th><td>calibrated flux density and total error (mJy; 1 mJy = AB 16.4):
              photometric ⊕ epoch zero-point ⊕ per-camera systematic</td></tr>
            <tr><th>flux_err_random_mJy</th><td>epoch-to-epoch (random) part of the error only</td></tr>
            <tr><th>mag_AB, mag_AB_err, mag_AB_err_random</th><td>the same in AB magnitudes</td></tr>
            <tr><th>frame</th><td>LCO frame name, to trace any point back to the archive</td></tr>
          </tbody>
        </table>
      </div>

      <div class="col-lg-6 ava-prose">
        <h3 class="h5">Spectroscopy</h3>
        <p>Spectra are delivered as one bundle per AGN containing:</p>
        <ul>
          <li><strong>Reduced 1-d spectra</strong> — every FLOYDS spectrum as a FITS file, blue and red arms.
            <span class="ava-tbd">Format to be finalised.</span></li>
          <li><strong>PrepSpec input</strong> — one three-column text file (wavelength in Å, F<sub>λ</sub>, error) per
            spectrum and arm, plus <code>&lt;target&gt;_blue.hjd</code> and <code>&lt;target&gt;_red.hjd</code> listing each
            file and its mid-exposure MJD. The red arm starts at 5300 Å, where it no longer overlaps the blue.</li>
        </ul>
        <h3 class="h5 mt-4">Spectroscopy — H&beta; light curve</h3>
        <p><code>&lt;target&gt;_FLOYDS_Hbeta_lightcurve.csv</code>: nightly means of the broad H&beta; flux and the 5100 Å
          continuum.</p>
        <table class="table ava-info">
          <thead><tr><th>Column</th><th>Content</th></tr></thead>
          <tbody>
            <tr><th>target, MJD, night</th><td>AVA identifier, mean MJD and night (YYYYMMDD)</td></tr>
            <tr><th>n_exp</th><td>spectra averaged that night</td></tr>
            <tr><th>hbeta_flux, hbeta_flux_err</th><td>broad H&beta; flux (erg s⁻¹ cm⁻²)</td></tr>
            <tr><th>cont5100, cont5100_err</th><td>5100 Å continuum (erg s⁻¹ cm⁻² Å⁻¹)</td></tr>
            <tr><th>oiii_calibrated</th><td>whether the night was scaled to a constant [O III] flux</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</section>

<?php if ($filters): ?>
<section class="ava-section ava-section--alt" id="filters">
  <div class="container-xxl">
    <p class="ava-eyebrow">LCO filters</p>
    <h2 class="mb-2">Filter transmission curves</h2>
    <p class="text-secondary mb-4" style="max-width:80ch">Transmission of each LCO filter including the
      <strong>Sinistro CCD response</strong> (the only instrument component — no telescope mirrors or other optics) and
      the <strong>atmosphere at airmass = 1</strong>, hence the telluric O<sub>2</sub> bands in r and i. These are the curves used for the absolute calibration of the merged light curves
      (<a href="#cite">PyTICS; Vieliute et al. 2025</a>). Each file has two columns: wavelength (Å) and transmission.</p>
    <div class="ava-chart-wrap mt-0"><?= ava_transmission_svg($filters) ?></div>
    <div class="ava-table-wrap mt-4" style="max-height:none">
      <table class="table ava-table">
        <thead><tr><th>Band</th><th>Filter</th><th class="num">λ<sub>pivot</sub> (Å)</th><th class="num">λ<sub>mean</sub> (Å)</th>
          <th class="num">FWHM (Å)</th><th class="num">Half-max range (Å)</th><th class="num">Peak T</th><th>File</th></tr></thead>
        <tbody>
          <?php foreach ($filters as $band => $f): ?>
            <tr>
              <th scope="row" style="--c: var(<?= ava_filter_var((string) $band) ?>)"><span class="ava-filter-dot"></span><?= h((string) $band) ?></th>
              <td><?= h(AVA_FILTER_NAMES[$band] ?? (string) $band) ?></td>
              <td class="num"><?= number_format($f['pivot_A']) ?></td>
              <td class="num"><?= number_format($f['mean_A']) ?></td>
              <td class="num"><?= number_format($f['fwhm_A']) ?></td>
              <td class="num"><?= number_format($f['half_lo_A']) ?>–<?= number_format($f['half_hi_A']) ?></td>
              <td class="num"><?= number_format(100 * $f['peak']) ?> %</td>
              <td><a href="<?= h(AVA_DATA_URL . '/filters/' . rawurlencode($f['file'])) ?>" download><?= h($f['file']) ?></a></td>
            </tr>
          <?php endforeach; ?>
        </tbody>
      </table>
    </div>
    <?php if (is_file(AVA_DATA_DIR . '/filters/ava_lco_filters.zip')): ?>
      <a class="btn btn-ava btn-ava-gold mt-3" href="<?= h(AVA_DATA_URL) ?>/filters/ava_lco_filters.zip" download>Download all curves (zip)</a>
    <?php endif; ?>
  </div>
</section>
<?php endif; ?>

<section class="ava-section" id="cite">
  <div class="container-xxl">
    <div class="row g-5">
      <div class="col-lg-6 ava-prose">
        <p class="ava-eyebrow">How to cite</p>
        <h2>Acknowledging AVA</h2>
        <p>If your work uses AVA data, please cite:</p>
        <?php ava_citation_block(); ?>
        <p class="mt-3 small text-secondary">Also on the <a href="about.php#cite">About page</a>; see
          <a href="science.php">Science</a> for results from the Key Projects.</p>
      </div>

      <div class="col-lg-6" id="contact">
        <p class="ava-eyebrow">Contact</p>
        <h2>Request data or ask a question</h2>
        <p>To request access to AVA data products, or for any question about the archive, please email
          <?= h(AVA_PI) ?> at <?= ava_mailto(AVA_CONTACT_EMAIL, 'AVA data request') ?>.</p>
        <p class="small text-secondary">Key Project members: please say which programme you belong to and which
          targets and products you need.</p>
      </div>
    </div>
  </div>
</section>

<?php ava_page_end(['assets/js/sort-table.js']); ?>
