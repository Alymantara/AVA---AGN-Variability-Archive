<?php
declare(strict_types=1);
require __DIR__ . '/includes/layout.php';

$s = ava_stats();
$targets = ava_targets();
// Featured: active targets with an image, most-observed first.
$featured = array_filter($targets, fn($t) => ava_status($t)['key'] === 'active' && ava_image_stem($t));
usort($featured, fn($a, $b) => (int) $b['db_lco_images'] <=> (int) $a['db_lco_images']);
$featured = array_slice($featured, 0, 6);

ava_page_start('home', 'Home');
?>
<section class="ava-hero">
  <div class="container-xxl">
    <p class="ava-eyebrow">University of St Andrews · Las Cumbres Observatory</p>
    <h1><span class="gold">AGN</span> Variability<br class="d-none d-sm-inline"> Archive</h1>
    <p class="ava-lead">Reverberation mapping of AGN with the Las Cumbres Observatory.
      A long-baseline, multi-band record of how accretion discs around supermassive black holes flicker and echo.</p>
    <div class="d-flex flex-wrap gap-3">
      <a class="btn btn-ava btn-ava-gold" href="targets.php">Browse Targets</a>
      <a class="btn btn-ava btn-ava-outline" href="data.php">Access Data</a>
    </div>
  </div>
</section>

<section class="ava-stats" aria-label="Archive in numbers">
  <div class="ava-stat"><span class="ava-stat__n"><?= number_format($s['agn']) ?></span><span class="ava-stat__l">AGN monitored</span></div>
  <div class="ava-stat"><span class="ava-stat__n"><?= fmt_compact($s['images']) ?></span><span class="ava-stat__l">photometric images</span></div>
  <div class="ava-stat"><span class="ava-stat__n"><?= number_format($s['spectra']) ?>+</span><span class="ava-stat__l">spectra</span></div>
  <div class="ava-stat"><span class="ava-stat__n"><?= $s['years'] ?></span><span class="ava-stat__l">years of data</span></div>
</section>

<section class="ava-section">
  <div class="container-xxl">
    <div class="row g-3 g-lg-4">
      <div class="col-md-4"><div class="ava-tile"><span class="ava-tile__k">01</span>
        <h3>A global network</h3>
        <p>Robotic 1-m and 2-m telescopes on six sites keep an AGN in view around the clock, so light curves are sampled every few hours rather than every few days.</p></div></div>
      <div class="col-md-4"><div class="ava-tile"><span class="ava-tile__k">02</span>
        <h3>Seven bands, one disc</h3>
        <p>Continuum lags between <em>u</em> and <em>z</em> map the temperature structure of the accretion disc; FLOYDS spectra follow the broad-line region.</p></div></div>
      <div class="col-md-4"><div class="ava-tile"><span class="ava-tile__k">03</span>
        <h3>A living archive</h3>
        <p>Every frame is reduced by the AVA pipeline into a single database, from which this site is built — targets, light curves and observing summaries.</p></div></div>
    </div>
  </div>
</section>

<?php if ($featured): ?>
<section class="ava-section ava-section--alt">
  <div class="container-xxl">
    <div class="d-flex flex-wrap align-items-end justify-content-between gap-3 mb-4">
      <div>
        <p class="ava-eyebrow">Currently observing</p>
        <h2 class="mb-0">Featured targets</h2>
      </div>
      <a class="btn btn-ava btn-ava-outline" href="targets.php">All <?= count($targets) ?> targets →</a>
    </div>
    <div class="ava-grid">
      <?php foreach ($featured as $t) { ava_target_card($t); } ?>
    </div>
  </div>
</section>
<?php endif; ?>

<?php ava_page_end(); ?>
