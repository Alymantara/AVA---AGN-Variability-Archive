<?php
declare(strict_types=1);
require __DIR__ . '/includes/layout.php';
require __DIR__ . '/includes/plots.php';
require __DIR__ . '/includes/releases.php';

$id = filter_input(INPUT_GET, 'id', FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
$t = $id ? ava_target($id) : null;
if (!$t) {
    http_response_code(404);
    ava_page_start('targets', 'Target not found');
    echo '<div class="container-xxl ava-page-head"><h1>Target not found</h1>
          <p class="ava-lead">No AGN with that identifier. <a href="targets.php">Back to all targets</a>.</p></div>';
    ava_page_end();
    exit;
}

/* ---------- helpers local to this page ---------- */
const ADS = 'https://ui.adsabs.harvard.edu/abs/';

function ads_link(?string $bib, ?string $label): string
{
    $label = trim((string) $label);
    $bib = trim((string) $bib);
    if ($bib === '') {
        return $label !== '' ? h($label) : '—';
    }
    return '<a href="' . ADS . h(rawurlencode($bib)) . '/abstract">' . h($label !== '' ? $label : $bib) . '</a>';
}

/** "7.59 ± 0.07" (error omitted when absent). */
function pm_num(mixed $v, mixed $e, int $dp): string
{
    if (!is_numeric($v)) {
        return '—';
    }
    return number_format((float) $v, $dp) . (is_numeric($e) && (float) $e > 0 ? ' ± ' . number_format((float) $e, $dp) : '');
}

/** Redshift with up to 5 decimals, trailing zeros dropped (0.0160540007 → 0.01605, 0.064 → 0.064). */
function fmt_z(mixed $z): string
{
    if (!is_numeric($z)) {
        return '—';
    }
    $d = (float) $z < 0.01 ? 6 : 5;
    return rtrim(rtrim(number_format((float) $z, $d, '.', ''), '0'), '.');
}

/** Value present and positive (the legacy DB uses 0 / negative for "none"). */
function is_pos(mixed $v): bool
{
    return is_numeric($v) && (float) $v > 0;
}

function mjd(?string $date): string
{
    if (!$date || ($ts = strtotime($date . ' UTC')) === false) {
        return '';
    }
    return number_format($ts / 86400 + 40587, 0, '.', '');
}

function date_cell(?string $date): string
{
    if (!$date) {
        return '<td>—</td>';
    }
    return '<td>' . h($date) . '<span class="mjd">MJD ' . mjd($date) . '</span></td>';
}

/** Epochs, with the number of frames underneath in grey (data summary tables). */
function epochs_cell(mixed $epochs, mixed $frames): string
{
    $e = is_pos($epochs) ? fmt_int($epochs) : '—';
    $f = is_pos($frames) ? '<span class="mjd">' . fmt_int($frames) . ' frames</span>' : '';
    return '<td class="num">' . $e . $f . '</td>';
}

/** Allow only simple typographic markup stored in the DB (e.g. logl_comment). */
function db_markup(?string $s): string
{
    return strip_tags((string) $s, '<em><i><sub><sup><b><strong>');
}

$v = fn(string $k) => $t[$k] ?? null;
$lcoFrames = fn(string $f) => is_pos($v("db_lco_$f")) ? (int) $v("db_lco_$f") : (int) $v("lco_$f");

$stem = ava_image_stem($t);
$st = ava_status($t);
$lcoStart = $v('db_lco_start') ?: $v('lco_start');
$lcoEnd = $v('db_lco_end') ?: $v('lco_end');
$lcoCad = is_pos($v('db_lco_cadence')) ? $v('db_lco_cadence') : $v('lco_cadence');
$fEpochs = is_pos($v('db_floyds_epochs')) ? $v('db_floyds_epochs') : $v('floyds_epochs');
$fStart = $v('db_floyds_start') ?: $v('floyds_start');
$fEnd = $v('db_floyds_end') ?: $v('floyds_end');
$fCad = is_pos($v('db_floyds_cadence')) ? $v('db_floyds_cadence') : $v('floyds_cadence');
$simbadId = $t['simbad_name'] ?: $t['name'];
$lcoArchive = 'https://archive.lco.global/?' . http_build_query([
    'target_name' => rawurldecode((string) ($t['lco_id'] ?: $t['name'])),
    'start' => ($lcoStart ?: '2014-01-01') . ' 00:00', 'end' => ($lcoEnd ?: date('Y-m-d')) . ' 23:59',
    'public' => 'true', 'limit' => 50]);
$cites = array_values(array_filter(array_map(null,
    explode('|', (string) $t['cite_name']), explode('|', (string) $t['cite_url'])), fn($c) => trim((string) $c[0]) !== ''));

/* Plot tabs: only the ones that have been published. */
// Photometry: the merged (intercalibrated) light curves when they exist — merged full
// light curve first, so it is the default view; the per-telescope LCO plots only otherwise.
$photoTabs = [];
foreach ([['merged', 'merged_season', 'merged_last6', 'merged_pytics'], ['lco', 'season', 'last6']] as $group) {
    foreach ($group as $k) {
        if ($u = ava_plot_url($t, $k)) {
            $photoTabs[$k] = [AVA_PLOT_KINDS[$k][1], $u];
        }
    }
    if ($photoTabs) {
        break;
    }
}
if ($u = ava_plot_url($t, 'swift')) {
    $photoTabs['swift'] = [AVA_PLOT_KINDS['swift'][1], $u];
}
$skyTabs = [];
foreach (array_keys(AVA_SKY_FILTERS) as $f) {
    if ($u = ava_plot_url($t, "sky_$f")) {
        $skyTabs[$f] = $u;
    }
}
$zoom = ava_plot_url($t, 'zoom');
$stan = ava_plot_url($t, 'stan');
$specTabs = [];
foreach (['spec', 'spec_avg', 'hbeta', 'hbeta_fit'] as $k) {
    if ($u = ava_plot_url($t, $k)) {
        $specTabs[$k] = [AVA_PLOT_KINDS[$k][1], $u];
    }
}
$lineVar = ava_line_variability((string) $t['data_id']);
$bandVar = ava_band_variability((string) $t['data_id']);
$derived = ava_derived((string) $t['data_id']);
$lit = ava_literature((string) $t['data_id']);
// mass error only when the shown mass is the literature value it belongs to
$massErr = is_numeric($lit['log_MBH'] ?? null) && is_numeric($t['logm']) && abs((float) $lit['log_MBH'] - (float) $t['logm']) < 0.005
    ? ($lit['log_MBH_err'] ?? null) : null;
$plotsUpdated = ava_plots_updated($t);

/** "6.17 ± 0.12 × 10⁻¹³" with a shared exponent. */
function sci(mixed $v, mixed $e = null, int $dp = 2): string
{
    if (!is_numeric($v) || (float) $v == 0.0) {
        return '—';
    }
    $x = (int) floor(log10(abs((float) $v)));
    $m = (float) $v / 10 ** $x;
    $s = number_format($m, $dp);
    if (is_numeric($e) && (float) $e > 0) {
        $s .= ' ± ' . number_format((float) $e / 10 ** $x, $dp);
    }
    $sup = strtr((string) $x, ['-' => '⁻', '0' => '⁰', '1' => '¹', '2' => '²', '3' => '³', '4' => '⁴',
        '5' => '⁵', '6' => '⁶', '7' => '⁷', '8' => '⁸', '9' => '⁹']);
    return $s . ' × 10' . $sup;
}

function pct(mixed $v, mixed $e = null): string
{
    if (!is_numeric($v)) {
        return '—';
    }
    return number_format(100 * (float) $v, 1) . (is_numeric($e) ? ' ± ' . number_format(100 * (float) $e, 1) : '') . ' %';
}

$breakdownCols = ['u', 'B', 'g', 'V', 'r', 'i', 'z', 'Y'];   // by wavelength

/** Filter name for a table header: SDSS u′ g′ r′ i′ in lower case, Pan-STARRS z<sub>s</sub>, Bessell/Y as is. */
function band_label(string $f, bool $zs = true): string
{
    $sdss = ['u' => 'u′', 'g' => 'g′', 'r' => 'r′', 'i' => 'i′', 'z' => $zs ? 'z<sub>s</sub>' : 'z′'];
    return '<span class="ava-band">' . ($sdss[$f] ?? h($f)) . '</span>';
}

ava_page_start('targets', $t['name'], 'AVA data summary, light curves and diagnostics for ' . $t['name'] . '.');

/** Render a plot figure (click opens full size). */
function plot_img(string $url, string $alt): string
{
    return '<a class="ava-plot" href="' . h($url) . '" target="_blank" rel="noopener" title="Open full size in a new tab">'
        . '<img src="' . h($url) . '" alt="' . h($alt) . '" loading="lazy" decoding="async"></a>';
}

/** Bootstrap tab nav + panes. $tabs = [key => [label, html]] */
function tabs(string $id, array $tabs, string $style = 'tabs'): void
{
    if (!$tabs) {
        return;
    }
    $first = array_key_first($tabs);
    echo '<ul class="nav nav-' . $style . ' ava-tabs" role="tablist">';
    foreach ($tabs as $k => [$label]) {
        $a = $k === $first;
        echo '<li class="nav-item" role="presentation"><button class="nav-link' . ($a ? ' active' : '') . '" data-bs-toggle="tab"'
            . ' data-bs-target="#' . h("$id-$k") . '" type="button" role="tab" aria-selected="' . ($a ? 'true' : 'false') . '">'
            . $label . '</button></li>';
    }
    echo '</ul><div class="tab-content">';
    foreach ($tabs as $k => [, $html]) {
        echo '<div class="tab-pane fade' . ($k === $first ? ' show active' : '') . '" id="' . h("$id-$k") . '" role="tabpanel">' . $html . '</div>';
    }
    echo '</div>';
}
?>
<div class="container-xxl ava-target">
  <div class="ava-target__head">
    <div>
      <nav aria-label="breadcrumb"><ol class="breadcrumb small mb-1">
        <li class="breadcrumb-item"><a href="targets.php">Targets</a></li>
        <li class="breadcrumb-item active" aria-current="page">AVA #<?= (int) $t['id'] ?></li>
      </ol></nav>
      <h1 class="mb-1"><?= h($t['name']) ?> <span class="ava-badge static ava-badge--<?= $st['key'] ?>"><?= $st['label'] ?></span></h1>
      <div class="ava-links mb-0">
        <a href="https://simbad.cds.unistra.fr/simbad/sim-id?Ident=<?= h(rawurlencode($simbadId)) ?>">SIMBAD</a>
        <a href="https://ned.ipac.caltech.edu/byname?objname=<?= h(rawurlencode($simbadId)) ?>">NED</a>
        <?php if (is_pos($t['bentz_id'])): ?>
          <a href="http://www.astro.gsu.edu/AGNmass/details.php?varname=<?= (int) $t['bentz_id'] ?>">Bentz DB</a>
        <?php endif; ?>
        <a href="<?= h($lcoArchive) ?>">LCO Archive (raw images)</a>
        <?php if (ava_downloads_enabled()): $dl = ava_downloads((string) $t['data_id']); $group = null; ?>
        <span class="dropdown ava-download">
          <button class="btn btn-sm btn-ava btn-ava-gold dropdown-toggle" type="button" data-bs-toggle="dropdown" aria-expanded="false">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12M7 10l5 5 5-5M4 20h16"/></svg>
            Download
          </button>
          <ul class="dropdown-menu ava-dropdown">
            <?php foreach ($dl as [$g, $label, $url, $bytes, $note]): ?>
              <?php if ($g !== $group): $group = $g; ?>
                <li><h6 class="dropdown-header"><?= h($g) ?></h6></li>
              <?php endif; ?>
              <li>
                <?php if ($url): ?>
                  <a class="dropdown-item" href="<?= h($url) ?>" download><?= h($label) ?> <span class="ava-dl-size"><?= fmt_bytes($bytes) ?></span></a>
                <?php else: ?>
                  <span class="dropdown-item disabled" aria-disabled="true"><?= h($label) ?> <span class="ava-dl-size"><?= h($note) ?></span></span>
                <?php endif; ?>
              </li>
            <?php endforeach; ?>
            <li><hr class="dropdown-divider"></li>
            <li><a class="dropdown-item small" href="data.php#format">File formats</a></li>
          </ul>
        </span>
        <?php endif; ?>
      </div>
    </div>
    <a class="btn btn-sm btn-ava btn-ava-outline" href="targets.php">← Back</a>
  </div>

  <div class="row g-4">
    <!-- ================= LEFT: information ================= -->
    <div class="col-xl-6">
      <table class="table ava-info ava-coords">
        <thead><tr><th>RA (h:m:s)</th><th>Dec (d:m:s)</th><th>RA (deg)</th><th>Dec (deg)</th></tr></thead>
        <tbody><tr>
          <td><?= h($t['ra']) ?></td><td><?= h($t['dec']) ?></td>
          <td><?= fmt_num($t['ra_deg'], 5) ?></td><td><?= fmt_num($t['dec_deg'], 5) ?></td>
        </tr></tbody>
      </table>

      <h2 class="ava-h">Basic information</h2>
      <table class="table ava-info">
        <tbody>
          <tr><th>Redshift</th><td class="num"><?= fmt_z($t['redshift']) ?></td><td></td>
              <td class="ref"><?= ads_link($t['red_url'], $t['red_cite'] ?: ($t['red_url'] ? 'reference' : '')) ?></td></tr>
          <?php $nh = is_pos($t['nh'] ?? null) ? (float) $t['nh'] : null; $nhExp = $nh ? (int) floor(log10($nh)) : 0; ?>
          <tr><th><?php if ($nh): ?><button type="button" class="ava-rowtoggle collapsed" data-bs-toggle="collapse"
                data-bs-target="#nhRow" aria-expanded="false" aria-controls="nhRow">E(B−V)</button><?php else: ?>E(B−V)<?php endif; ?></th>
              <td class="num"><?= fmt_num($t['ebv'], 3) ?></td><td>mag</td>
              <td class="ref"><?= ads_link('2011ApJ...737..103S', 'Schlafly & Finkbeiner (2011)') ?></td></tr>
          <?php if ($nh): ?>
          <tr class="collapse ava-subrow" id="nhRow"><th>Galactic N<sub>H</sub></th>
              <td class="num"><?= number_format($nh / 10 ** $nhExp, 2) ?> × 10<sup><?= $nhExp ?></sup></td><td>cm⁻²</td>
              <td class="ref"><?= ads_link('2016A&A...594A.116H', 'HI4PI Collaboration (2016)') ?></td></tr>
          <?php endif; ?>
          <tr><th>Black hole mass</th><td class="num"><?= pm_num($t['logm'], $massErr, 2) ?></td><td>log M<sub>☉</sub></td>
              <td class="ref"><?= ads_link($t['logm_url'], $t['logm_cite']) ?></td></tr>
          <?php if (is_numeric($lit['tau_hbeta_days'] ?? null)): ?>
          <tr><th>Hβ lag</th><td class="num"><?= pm_num($lit['tau_hbeta_days'], $lit['tau_hbeta_err'], 1) ?></td><td>days (rest)</td>
              <td class="ref"><?= ads_link($lit['tau_ref'], $lit['tau_cite']) ?></td></tr>
          <?php endif; ?>
          <?php if (is_pos($t['l_5100'])): ?>
          <tr><th>log L<sub>5100</sub></th><td class="num"><?= fmt_num($t['l_5100'], 2) ?></td><td>erg s⁻¹</td>
              <td class="ref"><?= ads_link($t['l_5100_url'], $t['l_5100_cite']) ?></td></tr>
          <?php endif; ?>
          <tr><th>log L<sub>Bol</sub></th><td class="num"><?= fmt_num(ava_log_lbol($t, $derived), 2) ?></td><td>erg s⁻¹</td>
              <td class="ref"><?php if (($derived['lbol_source'] ?? '') === 'l_5100'): ?><em>k</em><sub>bol</sub> = <?= fmt_num($derived['kbol'], 1) ?>, <?= ads_link('2019MNRAS.488.5185N', 'Netzer (2019)') ?>
                  <?php else: ?><?= ads_link($t['logl_url'], $t['logl_cite']) ?><?php endif; ?></td></tr>
          <tr><th>L / L<sub>Edd</sub></th><td class="num"><?= fmt_num($derived['eddington_ratio'] ?? $t['ledd'], 3) ?></td><td></td><td class="ref text-secondary">(caution)</td></tr>
          <?php foreach (['ug' => ['u', 'g'], 'gz' => ['g', 'z']] as $k => [$a, $b]):
              $lag = $derived["lag_{$k}_days"] ?? null; if (!is_numeric($lag)) { continue; } ?>
          <tr><th>Lag <em><?= $a ?></em>–<em><?= $b ?></em></th><td class="num"><?= fmt_num($lag, 2) ?></td><td>days</td>
              <td class="ref"><span class="text-secondary">(theoretical)</span> <?= ads_link('2016ApJ...821...56F', 'Fausnaugh et al. (2016)') ?></td></tr>
          <?php endforeach; ?>
          <tr><th>Mean <em>g</em></th><td class="num"><?= fmt_num($t['Vmag'], 2) ?></td><td>mag</td><td class="ref text-secondary">LCO</td></tr>
          <?php if (trim((string) $t['AGN_type']) !== ''): ?>
          <tr><th>Type</th><td class="num"><?= h($t['AGN_type']) ?></td><td></td>
              <td class="ref"><?= ($lit['agn_type'] ?? null) === $t['AGN_type'] ? ads_link($lit['type_ref'], $lit['type_cite']) : '' ?></td></tr>
          <?php endif; ?>
        </tbody>
      </table>
      <details class="ava-notes"><summary>Notes</summary>
        <?php if (trim((string) $t['Comments']) !== ''): ?><p><strong>Comments:</strong> <?= h($t['Comments']) ?></p><?php endif; ?>
        <?php if (trim((string) $t['PI']) !== ''): ?><p><strong>PI:</strong> <?= h($t['PI']) ?></p><?php endif; ?>
        <p><strong>Processing:</strong> <?= h(ava_processing($t)) ?></p>
      </details>

      <h2 class="ava-h">Photometric data summary</h2>
      <div class="table-responsive">
      <table class="table ava-info ava-summary">
        <thead><tr><th>Facility</th><th class="num">Cadence (d)</th><th>Start</th><th>End</th><th class="num">Epochs</th></tr></thead>
        <tbody>
          <?php if (is_pos($lcoCad) || is_pos($v('db_lco_images'))): ?>
          <tr><th>LCO</th><td class="num"><?= fmt_num($lcoCad, 2) ?></td><?= date_cell($lcoStart) ?><?= date_cell($lcoEnd) ?>
              <?= epochs_cell($v('db_lco_visits'), $v('db_lco_images')) ?></tr>
          <?php endif; ?>
          <?php if (is_pos($t['swift_cadence'])): ?>
          <tr><th>Swift</th><td class="num"><?= fmt_num($t['swift_cadence'], 2) ?></td><?= date_cell($t['swift_start']) ?><?= date_cell($t['swift_end']) ?>
              <td class="num">—</td></tr>
          <?php endif; ?>
          <?php if (is_pos($t['lt_cadence'])): ?>
          <tr><th>LT</th><td class="num"><?= fmt_num($t['lt_cadence'], 2) ?></td><?= date_cell($t['lt_start']) ?><?= date_cell($t['lt_end']) ?>
              <td class="num">—</td></tr>
          <?php endif; ?>
          <?php if (is_pos($t['hst_tot'])): ?>
          <tr><th>HST</th><td class="num">—</td><td>—</td><td>—</td><?= epochs_cell(null, $t['hst_tot']) ?></tr>
          <?php endif; ?>
        </tbody>
      </table>
      </div>
      <?php if (is_pos($v('db_lco_visits'))): ?>
        <details class="ava-notes"><summary>Notes</summary><p>LCO: <?= fmt_int($v('db_lco_visits')) ?> visits, <?= fmt_num($v('db_lco_exp_h'), 1) ?> h exposure.
          <?php if ($v('db_lco_proposals')): ?>Programmes: <?= h(str_replace(';', ', ', (string) $v('db_lco_proposals'))) ?>.<?php endif; ?></p></details>
      <?php endif; ?>

      <?php if (is_pos($fEpochs)): ?>
      <h2 class="ava-h">Spectroscopic data summary</h2>
      <div class="table-responsive">
      <table class="table ava-info ava-summary">
        <thead><tr><th>Facility</th><th class="num">Cadence (d)</th><th>Start</th><th>End</th><th class="num">Epochs</th></tr></thead>
        <tbody><tr><th>LCO FLOYDS</th><td class="num"><?= fmt_num($fCad, 2) ?></td><?= date_cell($fStart) ?><?= date_cell($fEnd) ?>
          <?= epochs_cell($fEpochs, $v('db_floyds_frames')) ?></tr></tbody>
      </table>
      </div>
      <?php if (is_pos($v('db_floyds_frames'))): ?>
        <details class="ava-notes"><summary>Notes</summary><p>FLOYDS: <?= fmt_int($v('db_floyds_frames')) ?> frames, <?= fmt_num($v('db_floyds_exp_h'), 1) ?> h exposure.</p></details>
      <?php endif; ?>
      <?php endif; ?>

      <?php if ($lineVar):
          $any = reset($lineVar);
          $rows = ['flux' => ['Broad H&beta;', 'erg s⁻¹ cm⁻²'], 'cont5100' => ['Continuum 5100 Å', 'erg s⁻¹ cm⁻² Å⁻¹']]; ?>
      <h2 class="ava-h">H&beta; variability</h2>
      <div class="table-responsive">
      <table class="table ava-info">
        <thead><tr><th></th><th class="num">Mean</th><th class="num"><abbr title="Fractional variability: rms variation in excess of the measurement errors, as a fraction of the mean flux">F<sub>var</sub></abbr></th><th class="num">Median S/N</th></tr></thead>
        <tbody>
          <?php foreach ($rows as $q => [$label, $unit]): if (!isset($lineVar[$q])) { continue; } $r = $lineVar[$q]; ?>
          <tr><th><?= $label ?><span class="mjd"><?= $unit ?></span></th>
            <td class="num"><?= sci($r['mean'], $r['mean_err']) ?></td>
            <td class="num"><?= pct($r['fvar'], $r['fvar_err']) ?></td>
            <td class="num"><?= fmt_num($r['snr_median'], 0) ?></td></tr>
          <?php endforeach; ?>
        </tbody>
      </table>
      </div>
      <details class="ava-notes"><summary>Notes</summary><p>
        <?= fmt_int($any['n_spectra']) ?> spectra on <?= fmt_int($any['n_nights']) ?> nights
        (MJD <?= fmt_num($any['mjd_first'], 1) ?>–<?= fmt_num($any['mjd_last'], 1) ?>)<?php if (is_pos($any['fwhm_kms_median'])): ?>;
        median H&beta; FWHM <?= fmt_int(round((float) $any['fwhm_kms_median'])) ?> km s⁻¹<?php endif; ?>;
        <?= (int) $any['oiii_calibrated'] ? '[O III]-calibrated' : 'not [O III]-calibrated' ?>;
        fit <code><?= h($any['method']) ?></code>; updated <?= h(substr((string) $any['updated_utc'], 0, 10)) ?>.
        F<sub>var</sub>: rms variation in excess of the errors, as a fraction of the mean (Vaughan et al. 2003).
      </p></details>
      <?php endif; ?>

      <?php ava_release_panel($t); ?>

      <h2 class="ava-h">Data citation</h2>
      <?php if ($cites): ?>
        <ul class="ava-cites">
          <?php foreach ($cites as [$n, $u]): ?><li><?= ads_link($u, $n) ?></li><?php endforeach; ?>
        </ul>
        <p class="small text-secondary">Please use these references if you use this object's data, and also cite AVA
          and PyTICS — see <a href="about.php#cite">how to cite data from AVA</a>.</p>
      <?php else: ?>
        <p class="text-secondary">No publication yet — please cite AVA (see <a href="about.php#cite">how to cite</a>).</p>
      <?php endif; ?>
    </div>

    <!-- ================= RIGHT: plots ================= -->
    <div class="col-xl-6">
      <div class="ava-plots">
        <?php
        $top = [];
        if ($photoTabs) {
            ob_start();
            tabs('ph', array_map(fn($p) => [$p[0], plot_img($p[1], $t['name'] . ' ' . $p[0] . ' light curve')], $photoTabs), 'pills');
            $top['photo'] = ['Photometry', ob_get_clean()];
        }
        if ($stem || $zoom) {
            $html = '';
            if ($zoom) { $html .= plot_img($zoom, $t['name'] . ' LCO image'); }
            if ($stem) {
                $big = 'assets/agn/' . rawurlencode($stem) . '_1200.webp';
                $html .= '<a class="ava-plot" href="' . h($big) . '" target="_blank" rel="noopener"><img src="' . h($big)
                    . '" alt="LCO colour composite of ' . h($t['name']) . '" loading="lazy" width="1200" height="1200"></a>'
                    . '<p class="small text-secondary mt-1">LCO colour composite (u, g, i).</p>';
            }
            $top['image'] = ['Image', $html];
        }
        // QC: the variability plot, then the sky conditions per filter.
        $qc = [];
        if ($stan) {
            $qc['stan'] = ['Variability plot', plot_img($stan, 'Variability plot: field-star magnitude vs RMS, AGN marked')];
        }
        foreach ($skyTabs as $f => $u) {
            $qc["sky_$f"] = ['Sky ' . h($f), plot_img($u, "$f-band seeing, airmass and zero point")];
        }
        if ($qc) {
            ob_start();
            tabs('qc', $qc, 'pills');
            $top['qc'] = ['QC', ob_get_clean()];
        }
        if ($specTabs) {
            ob_start();
            tabs('sp', array_map(fn($p) => [$p[0], plot_img($p[1], $t['name'] . ' FLOYDS ' . html_entity_decode(strip_tags($p[0])))], $specTabs), 'pills');
            $top['spec'] = ['Spectroscopy', ob_get_clean()];
        }

        if ($top) {
            // Tab order: Photometry, Spectroscopy, then the diagnostics.
            $top = array_filter(array_replace(array_fill_keys(['photo', 'spec', 'image', 'qc'], null), $top));
            tabs('pl', $top);
        } else {
            echo '<div class="ava-noplots">Light curves and diagnostics have not been published for this target yet.</div>';
        }
        ?>
        <?php if ($plotsUpdated): ?>
          <p class="small text-secondary mt-2 mb-0">Plots updated <?= gmdate('Y-m-d H:i', $plotsUpdated) ?> UTC · click a plot to open it full size.</p>
        <?php endif; ?>
      </div>
    </div>
  </div>

  <!-- ================= Photometry breakdown ================= -->
  <h2 class="ava-h mt-4">Photometry breakdown</h2>
  <div class="table-responsive">
    <table class="table ava-info ava-breakdown">
      <thead><tr><th>LCO</th>
        <?php foreach ($breakdownCols as $f): ?><th class="num" style="--c: var(<?= ava_filter_var($f) ?>)"><span class="fdot"></span><?= band_label($f) ?></th><?php endforeach; ?>
      </tr></thead>
      <tbody>
        <tr><th>#Epochs</th><?php foreach ($breakdownCols as $f): ?><td class="num"><?= fmt_int($lcoFrames($f)) ?></td><?php endforeach; ?></tr>
        <tr><th>Mean mag (AB), last 10 d</th><?php foreach ($breakdownCols as $f): ?><td class="num"><?= is_pos($t["avg_$f"] ?? null) ? fmt_num($t["avg_$f"], 2) : '—' ?></td><?php endforeach; ?></tr>
        <?php if ($bandVar): ?>
        <tr><th>F<sub>var</sub> (merged)</th><?php foreach ($breakdownCols as $f): $r = $bandVar[$f] ?? null; ?>
          <td class="num"<?= $r ? ' title="' . (int) $r['n_epochs'] . ' epochs"' : '' ?>><?=
            $r && is_numeric($r['fvar']) ? number_format(100 * (float) $r['fvar'], 1) . '<span class="mjd">± '
              . ((float) $r['fvar_err'] < 0.0005 ? '&lt;0.1' : number_format(100 * (float) $r['fvar_err'], 1)) . ' %</span>' : '—' ?></td>
        <?php endforeach; ?></tr>
        <?php elseif (is_pos($t['merged'])): ?>
        <tr><th>Fractional variability</th><?php foreach ($breakdownCols as $f): ?><td class="num"><?= fmt_pct($t["frac_$f"] ?? null) ?></td><?php endforeach; ?></tr>
        <?php endif; ?>
      </tbody>
    </table>
  </div>
  <?php $bv0 = $bandVar ? reset($bandVar) : null; ?>
  <?php if (is_pos($t['lt_cadence'])): $lt = ['u', 'g', 'r', 'i', 'z']; ?>
  <div class="table-responsive">
    <table class="table ava-info ava-breakdown">
      <thead><tr><th>LT — Liverpool Telescope</th><?php foreach ($lt as $f): ?><th class="num" style="--c: var(<?= ava_filter_var($f) ?>)"><span class="fdot"></span><?= band_label($f, false) ?></th><?php endforeach; ?></tr></thead>
      <tbody>
        <tr><th>#Epochs</th><?php foreach ($lt as $f): ?><td class="num"><?= fmt_int($t["lt_$f"]) ?></td><?php endforeach; ?></tr>
        <tr><th>Mean mag (AB), last 10 d</th><?php foreach ($lt as $f): ?><td class="num"><?= is_pos($t["avg_lt_$f"]) ? fmt_num($t["avg_lt_$f"], 2) : '—' ?></td><?php endforeach; ?></tr>
      </tbody>
    </table>
  </div>
  <?php endif; ?>

  <?php if (is_pos($t['swift_w2'])): $sw = ['FX' => 'X-rays', 'w2' => 'UVW2', 'm2' => 'UVM2', 'w1' => 'UVW1', 'U' => 'U', 'B' => 'B', 'V' => 'V'];
      $swDict = ['FX' => 'SX', 'w2' => 'UVW2', 'm2' => 'UVM2', 'w1' => 'UVW1', 'U' => 'Us', 'B' => 'Bs', 'V' => 'Vs'];   // filter_dict colours ?>
  <div class="table-responsive">
    <table class="table ava-info ava-breakdown">
      <thead><tr><th>Swift</th><?php foreach ($sw as $k => $label): ?><th class="num" style="--c: var(<?= ava_filter_var($swDict[$k]) ?>)"><span class="fdot"></span><?= h($label) ?></th><?php endforeach; ?></tr></thead>
      <tbody>
        <tr><th>#Epochs</th><?php foreach (array_keys($sw) as $k): ?><td class="num"><?= fmt_int($t["swift_$k"]) ?></td><?php endforeach; ?></tr>
        <tr><th>Mean mag (AB), last 10 d</th><?php foreach (array_keys($sw) as $k): ?><td class="num"><?= is_pos($t["avg_sw_$k"] ?? null) ? fmt_num($t["avg_sw_$k"], 2) : '—' ?></td><?php endforeach; ?></tr>
      </tbody>
    </table>
  </div>
  <?php endif; ?>

  <?php if ($bv0 || $v('db_updated')): ?>
    <details class="ava-notes"><summary>Notes</summary>
      <?php if ($bv0): ?><p>F<sub>var</sub>: rms variation in excess of the errors, as a fraction of the mean flux, of the PyTICS-merged
        light curve (errors: <?= h((string) $bv0['error_model']) ?>), MJD <?= fmt_num($bv0['mjd_first'], 0) ?>–<?= fmt_num($bv0['mjd_last'], 0) ?>;
        updated <?= h(substr((string) $bv0['updated_utc'], 0, 10)) ?>.</p><?php endif; ?>
      <?php if ($v('db_updated')): ?><p>Observing summary updated <?= h($v('db_updated')) ?>.</p><?php endif; ?>
    </details>
  <?php endif; ?>
</div>

<?php ava_page_end(); ?>
