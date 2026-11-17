<?php
declare(strict_types=1);
require __DIR__ . '/includes/layout.php';

$s = ava_stats();
$targets = ava_targets();
// Featured: active targets with an image, most-observed first.
$featured = array_filter($targets, fn($t) => ava_status($t)['key'] === 'active' && ava_image_stem($t));
usort($featured, fn($a, $b) => (int) $b['db_lco_images'] <=> (int) $a['db_lco_images']);
$featured = array_slice($featured, 0, 6);
// Hero background: a slow cross-fade through target images (active first), heavily diluted.
$heroPool = array_values(array_filter($targets, fn($t) => ava_image_stem($t) && is_file(AVA_ROOT . '/assets/agn/' . ava_image_stem($t) . '_1200.webp')));
usort($heroPool, fn($a, $b) => (ava_status($b)['key'] === 'active') <=> (ava_status($a)['key'] === 'active') ?: (int) $b['db_lco_images'] <=> (int) $a['db_lco_images']);
$hero = array_slice($heroPool, 0, 10);
shuffle($hero);

ava_page_start('home', 'Home');
?>
<section class="ava-hero">
  <?php if ($hero): ?>
  <div class="ava-hero__bg" aria-hidden="true">
    <?php foreach ($hero as $i => $t): $src = asset('assets/agn/' . ava_image_stem($t) . '_1200.webp'); ?>
      <img <?= $i === 0 ? 'class="is-on" src' : 'data-src' ?>="<?= h($src) ?>" alt="" data-name="<?= h($t['name']) ?>" data-href="target.php?id=<?= (int) $t['id'] ?>"<?= $i === 0 ? ' fetchpriority="high"' : '' ?>>
    <?php endforeach; ?>
  </div>
  <?php endif; ?>
  <div class="container-xxl ava-hero__content">
    <div class="ava-hero__logos">
      <a href="https://www.st-andrews.ac.uk/physics-astronomy/" title="University of St Andrews">
        <img class="ava-logo-d" src="<?= asset('assets/img/standrews_colour_dark.png') ?>" alt="University of St Andrews" width="638" height="120">
        <img class="ava-logo-l" src="<?= asset('assets/img/standrews_colour_light.png') ?>" alt="" width="638" height="120">
      </a>
      <a href="https://lco.global/" title="Las Cumbres Observatory">
        <img class="ava-logo-d" src="<?= asset('assets/img/lco_colour_dark.png') ?>" alt="Las Cumbres Observatory" width="709" height="120">
        <img class="ava-logo-l" src="<?= asset('assets/img/lco_colour_light.png') ?>" alt="" width="709" height="120">
      </a>
    </div>
    <p class="ava-eyebrow">University of St Andrews · Las Cumbres Observatory</p>
    <h1><span class="gold">AGN</span> Variability<br class="d-none d-sm-inline"> Archive</h1>
    <div class="ava-hero__row">
      <p class="ava-lead">Reverberation mapping of AGN with the Las Cumbres Observatory.
        A long-baseline, multi-band record of how accretion discs around supermassive black holes flicker and echo.</p>
      <a class="btn btn-ava btn-ava-gold ava-hero__cta" href="targets.php">Browse Targets <span aria-hidden="true">→</span></a>
    </div>
  </div>
  <?php if ($hero): ?>
    <a class="ava-hero__credit" id="heroCredit" href="target.php?id=<?= (int) $hero[0]['id'] ?>"><span>In the background</span> <?= h($hero[0]['name']) ?></a>
  <?php endif; ?>
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

<?php ava_page_end(['assets/js/hero.js']); ?>
