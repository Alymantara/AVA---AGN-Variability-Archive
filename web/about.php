<?php
declare(strict_types=1);
require __DIR__ . '/includes/layout.php';

$s = ava_stats();
$proposals = ava_proposals();

// Team carried over from the legacy site. PI listed separately.
$team = [
    'Rick Edelson', 'Keith Horne', 'Aaron Barth', 'Ed Cackett', 'Doron Chelouche',
    'Encarni Romero-Colmenero', 'Jonathan Gelbord', 'Michael Goad', 'Diego H. Gonzalez-Buitrago',
    'Erin Kara', 'Shai Kaspi', 'Paulina Lira', 'Ian McHardy', 'Hagai Netzer', 'Christopher Onken',
    'Bradley Peterson', 'Stefano Valenti', 'Carolin Villforth',
];

ava_page_start('about', 'About', 'About AVA: science case, team, collaborators and funding.');
?>
<div class="container-xxl ava-page-head">
  <p class="ava-eyebrow">About AVA</p>
  <h1>Watching black holes feed, one echo at a time</h1>
  <p class="ava-lead">AVA is a living archive of high-cadence, multi-band monitoring of active galactic nuclei, built from
    <?= $s['years'] ?> years of Las Cumbres Observatory Key Project data.</p>
</div>

<section class="ava-section pt-0">
  <div class="container-xxl">
    <div class="row g-5">
      <div class="col-lg-7 ava-prose">
        <h2>Project overview</h2>
        <p>The AGN Variability Archive (AVA) collects and systematically reduces the imaging and spectroscopy obtained by
          the LCO Key Projects dedicated to intensive broadband reverberation mapping. It started as a tool to follow
          incoming data from the telescope network in real time, and is growing into an open legacy database:
          <?= number_format($s['agn']) ?> AGN, <?= number_format($s['images']) ?> photometric images and
          <?= number_format($s['spectra']) ?> spectral epochs, reduced by a single pipeline into one database.</p>
        <p>Alongside the LCO data, AVA will host coordinated, processed data sets from other facilities — Swift, HST,
          NICER — to add multi-wavelength context and legacy value to every target.</p>

        <h2 class="mt-5">Science case</h2>
        <p>The accretion disc around a supermassive black hole is far too small to resolve with any telescope.
          Reverberation mapping resolves it in time instead: when the central X-ray/UV source flickers, the disc
          re-emits that variability at longer wavelengths after a light-travel delay. Measuring those delays across
          the ultraviolet–optical–infrared maps the disc's size and temperature structure.</p>
        <p>The lags are hours to days, so sampling must be dense and uninterrupted. The LCO network — identical robotic
          telescopes spread in longitude across both hemispheres — can observe a target several times a day for months
          to years, in seven bands from <em>u</em> to <em>z</em>, with FLOYDS spectroscopy tracing the broad-line region.
          The sample spans about three orders of magnitude in black-hole mass and Eddington ratio, testing how
          disc structure depends on both.</p>
      </div>

      <aside class="col-lg-5">
        <div class="ava-pi mb-4">
          <p class="ava-eyebrow mb-1">Principal Investigator</p>
          <h3 class="h4 mb-1"><?= h(AVA_PI) ?></h3>
          <p class="mb-0 text-secondary">School of Physics &amp; Astronomy, University of St Andrews</p>
        </div>
        <h3 class="h5">LCO programmes</h3>
        <p class="text-secondary small">Key Project allocations contributing data to AVA:</p>
        <ul class="ava-filters mb-4">
          <?php foreach ($proposals as $p): ?><li style="--c: var(--ava-sky)"><?= h($p) ?></li><?php endforeach; ?>
        </ul>
      </aside>
    </div>
  </div>
</section>

<section class="ava-section ava-section--alt" id="team">
  <div class="container-xxl">
    <p class="ava-eyebrow">People</p>
    <h2 class="mb-4">Team</h2>
    <ul class="ava-team">
      <li><strong><?= h(AVA_PI) ?></strong> <span class="text-secondary small">(PI)</span></li>
      <?php foreach ($team as $m): ?><li><?= h($m) ?></li><?php endforeach; ?>
    </ul>
  </div>
</section>

<section class="ava-section">
  <div class="container-xxl">
    <div class="row g-5">
      <div class="col-lg-6 ava-prose">
        <p class="ava-eyebrow">Collaborators</p>
        <h2>External collaborations</h2>
        <p>Not every target is monitored with the same intensity: some are sparsely sampled or observed in a subset of
          bands as part of external campaigns, including:</p>
        <ul>
          <li><strong>AGN STORM 2</strong> — the multi-facility campaign on Mrk 817</li>
          <li><strong>LAMP2016</strong> — the Lick AGN Monitoring Project 2016</li>
          <li><strong>SEAMBH</strong> — Super-Eddington Accreting Massive Black Holes</li>
        </ul>
      </div>
      <div class="col-lg-6 ava-prose">
        <p class="ava-eyebrow">Support</p>
        <h2>Facilities &amp; funding</h2>
        <p>AVA is based on observations from the <a href="https://lco.global/">Las Cumbres Observatory</a> global
          telescope network, obtained through the Key Projects listed above, and is developed at the
          <a href="https://www.st-andrews.ac.uk/physics-astronomy/">University of St Andrews</a>.</p>
        <?php /* TODO(PI): add grant acknowledgements (funder, grant number). */ ?>
      </div>
    </div>
  </div>
</section>

<?php ava_page_end(); ?>
