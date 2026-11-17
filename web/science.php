<?php
declare(strict_types=1);
require __DIR__ . '/includes/layout.php';
require __DIR__ . '/includes/publications.php';
require __DIR__ . '/includes/charts.php';

$ml = ava_mass_luminosity_svg(ava_targets());

$byYear = [];
foreach (AVA_PUBLICATIONS as $p) {
    $byYear[$p[3]][] = $p;
}
krsort($byYear);

// Main findings of the Intensive Broadband Reverberation Mapping Key Projects: [title, text, references].
$findings = [
    ['Lags follow the thin disc',
        'Longer wavelengths lag shorter ones throughout the optical/UV, roughly as τ ∝ λ<sup>4/3</sup>, the scaling of a standard thin accretion disc.',
        'Fausnaugh et al. 2016; Edelson et al. 2019'],
    ['…but the discs look too big',
        'Excess lags in <em>u</em> (Balmer jump) and <em>r</em> (Hα) and disc sizes larger than predicted point to diffuse continuum emission from the broad-line region.',
        'Korista &amp; Goad 2001; Netzer 2022; Prince et al. 2025'],
    ['X-rays are not a simple driver',
        'X-ray and optical/UV variations correlate weakly and inconsistently, challenging pure reprocessing and prompting new models of the central engine.',
        'Gardner &amp; Done 2017; Kammoun et al. 2021; Starkey et al. 2023'],
    ['The echoes change with time',
        'Years of monitoring show the lag spectrum evolving between epochs, driven by changes in luminosity or by transient obscuration.',
        'Kara et al. 2021; Vincentelli et al. 2022; Lewin et al. 2024, 2025'],
];

// Goals of the current Key Project ("echoes in time").
$goals = [
    'Follow how broadband reverberation signals evolve over years in the best-sampled AGN.',
    'Measure emitting-region sizes simultaneously in time (LCO) and in space (VLTI/MATISSE and GRAVITY+).',
    'Identify and follow AGN state transitions through changes in their reverberation response.',
    'Use evolving reverberation signals to test supermassive black-hole binary candidates.',
];

ava_page_start('science', 'Science', 'What reverberation mapping is, the AVA sample, main findings and publications of the LCO Key Projects on intensive broadband reverberation mapping of AGN.');

/** One year of papers as a compact list. */
function ava_pub_year(int $year, array $pubs): void
{
    echo '<div class="ava-pubyear"><h3 class="ava-pubyear__y">' . $year . '<span>' . count($pubs) . '</span></h3><ul class="ava-pubs2">';
    foreach ($pubs as [$title, $authors, $ref, , $ads]) {
        $t = $ads ? '<a href="' . AVA_ADS . h($ads) . '">' . h($title) . '</a>' : h($title);
        $pending = stripos($ref, 'submitted') !== false || stripos($ref, 'in press') !== false;
        echo '<li><span class="t">' . $t . '</span><span class="m">' . h($authors) . ' · '
            . ($pending ? '<span class="ava-pubs2__tag">' . h($ref) . '</span>' : h($ref)) . '</span></li>';
    }
    echo '</ul></div>';
}
$recentYears = array_slice(array_keys($byYear), 0, 2);
?>
<div class="container-xxl ava-page-head">
  <p class="ava-eyebrow">Science</p>
  <h1>Watching black holes feed, one echo at a time</h1>
  <nav class="ava-toc mt-3" aria-label="On this page">
    <a href="#rm">Reverberation mapping</a>
    <a href="#findings">Main findings</a>
    <a href="#now">Echoes in time</a>
    <a href="#publications">Publications</a>
  </nav>
</div>

<section class="pb-5" id="rm">
  <div class="container-xxl">
    <div class="row g-5 align-items-center">
      <div class="col-lg-6 ava-prose">
        <h2 class="mt-0">What is reverberation mapping?</h2>
        <p>The accretion disc feeding a supermassive black hole is a few light-days across — far too small to image. We
          resolve it in <em>time</em> instead: when the hot centre flickers in X-rays and UV, the disc and the gas around
          it echo the change at longer wavelengths, after a light-travel delay. Delays of hours to days map the disc's size
          and temperature.</p>
        <p><strong>Why it matters.</strong> Accretion powers the most luminous objects in the Universe and shapes how
          galaxies grow, yet the structure of the central engine is still debated. Echoes test accretion disc theory directly.</p>
        <p>Measuring them needs dense, uninterrupted, multi-band sampling for months — what the LCO network does best.
          Since 2014, four Key Projects have monitored AGN spanning
          about three orders of magnitude in black-hole mass and Eddington ratio, together with Swift and other observatories.</p>
      </div>
      <?php if ($ml['n']): ?>
      <figure class="col-lg-6 mb-0" id="sample">
        <div class="ava-chart-wrap mt-0">
          <div class="ava-chart-legend" aria-hidden="true">
            <span><span class="sw active"></span>Active (last 30 days): <?= (int) $ml['n_active'] ?></span>
            <span><span class="sw archive"></span>Not currently observed: <?= $ml['n'] - (int) $ml['n_active'] ?></span>
          </div>
          <?= $ml['svg'] ?>
        </div>
        <figcaption class="ava-figcap">The AVA sample: black-hole mass against bolometric luminosity for the
          <?= (int) $ml['n'] ?> of <?= (int) $ml['n_all'] ?> AGN with both estimated; lines mark constant Eddington
          ratio. Select a point to open the target.</figcaption>
      </figure>
      <?php endif; ?>
    </div>
  </div>
</section>

<section class="ava-section ava-section--alt" id="findings">
  <div class="container-xxl">
    <h2 class="mb-4">Main findings</h2>
    <div class="row g-3">
      <?php foreach ($findings as $i => [$title, $text, $refs]): ?>
        <div class="col-md-6 col-xl-3">
          <div class="ava-tile ava-finding">
            <span class="ava-tile__k"><?= sprintf('%02d', $i + 1) ?></span>
            <h3><?= $title ?></h3>
            <p><?= $text ?></p>
            <p class="ava-finding__refs"><?= $refs ?></p>
          </div>
        </div>
      <?php endforeach; ?>
    </div>
  </div>
</section>

<section class="ava-section" id="now">
  <div class="container-xxl">
    <div class="row g-5 align-items-start">
      <div class="col-lg-5 ava-prose">
        <p class="ava-eyebrow">Current Key Project</p>
        <h2>Echoes in time</h2>
        <p>Beyond static lag measurements, we now follow how reverberation signals change as AGN change state, combining
          LCO imaging and FLOYDS spectroscopy with coordinated X-ray, UV and IR monitoring.</p>
      </div>
      <div class="col-lg-7">
        <ol class="ava-goals">
          <?php foreach ($goals as $g): ?><li><?= h($g) ?></li><?php endforeach; ?>
        </ol>
      </div>
    </div>
  </div>
</section>

<section class="ava-section ava-section--alt" id="publications">
  <div class="container-xxl">
    <div class="d-flex flex-wrap align-items-baseline justify-content-between gap-2 mb-3">
      <h2 class="m-0">Publications</h2>
      <p class="text-secondary small m-0"><?= count(AVA_PUBLICATIONS) ?> papers · please also see
        <a href="about.php#cite">how to cite AVA</a></p>
    </div>
    <?php foreach ($byYear as $year => $pubs) { if (in_array($year, $recentYears, true)) { ava_pub_year((int) $year, $pubs); } } ?>
    <?php $older = array_diff_key($byYear, array_flip($recentYears)); ?>
    <?php if ($older): ?>
      <details class="ava-collapse mt-3">
        <summary><span class="ava-h m-0 h6">Earlier papers</span>
          <span class="ava-collapse__hint"><?= array_sum(array_map('count', $older)) ?> papers, <?= min(array_keys($older)) ?>–<?= max(array_keys($older)) ?></span></summary>
        <?php foreach ($older as $year => $pubs) { ava_pub_year((int) $year, $pubs); } ?>
      </details>
    <?php endif; ?>
  </div>
</section>

<?php ava_page_end(['assets/js/chart-tooltip.js']); ?>
