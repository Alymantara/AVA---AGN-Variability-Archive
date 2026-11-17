<?php
declare(strict_types=1);
require __DIR__ . '/includes/layout.php';
require __DIR__ . '/includes/cite.php';

$s = ava_stats();
$proposals = ava_proposals();

/** PI of an LCO Key Project (by proposal semester); every later programme is led by the AVA PI. */
function ava_programme_pi(string $proposal): string
{
    $pis = ['KEY2014A' => 'K. Horne', 'KEY2018B' => 'R. Edelson'];
    return $pis[substr($proposal, 0, 8)] ?? AVA_PI;
}

// Team carried over from the legacy site. PI listed separately.
// Current co-investigators (name => affiliation), alphabetical by surname.
$team = [
    'Vardha N. Bennert' => 'California Polytechnic State University',
    'Edward M. Cackett' => 'Wayne State University',
    'Doron Chelouche' => 'University of Haifa',
    'Chris Done' => 'Durham University',
    'Rick Edelson' => 'Spectral Sciences Inc.',
    'Jonathan Gelbord' => 'Spectral Sciences Inc.',
    'Michael R. Goad' => 'University of Leicester',
    'Diego H. González-Buitrago' => 'Universidad Nacional Autónoma de México',
    'Scott Hagen' => 'Institute for Fundamental Physics of the Universe / SISSA',
    'Keith Horne' => 'University of St Andrews',
    'Erin Kara' => 'Massachusetts Institute of Technology',
    'Shai Kaspi' => 'Tel Aviv University',
    'Hermine Landt' => '',
    'James Leftley' => 'European Southern Observatory',
    'Yan-Rong Li' => 'Institute of High Energy Physics, Chinese Academy of Sciences',
    'Marcin Marculewicz' => 'Wayne State University',
    'Ian M. McHardy' => 'University of Southampton',
    'Hagai Netzer' => 'Tel Aviv University',
    'Christopher A. Onken' => 'Australian National University',
    'Encarni Romero-Colmenero' => 'South African Astronomical Observatory',
    'Aditya Sinha' => 'University of Leicester',
    'Marianne Vestergaard' => 'University of Copenhagen',
    'Roberta Vieliute' => 'University of St Andrews',
    'Carolin Villforth' => 'University of Bath',
    'Hartmut Winkler' => 'University of Johannesburg',
];
// Previous members (no current affiliation shown).
$teamPrevious = ['Aaron Barth', 'Paulina Lira', 'Bradley Peterson', 'Stefano Valenti'];

// Manuals published by the pipeline's -w step into data/manuals/ (built from docs/*.tex).
// Only the ones present are listed; size and date come from the published file.
$manualInfo = [
    'ava_system_manual.pdf' => ['System Manual',
        'Architecture, database, configuration, pipeline orchestration and installation.'],
    'photometry_manual.pdf' => ['Photometry Manual',
        'LCO cameras, data download, source extraction, photometric calibration and light-curve products.'],
    'spectroscopy_manual.pdf' => ['Spectroscopy Manual',
        'FLOYDS spectroscopy: data selection, reduction with banzai-floyds and the Hβ products.'],
    'report_pytics_update.pdf' => ['PyTICS Calibration Report',
        'Internal report #3: PyTICS in the new pipeline — validation, per-camera colour terms and MuSCAT3 intercalibration.'],
];
$manuals = [];
foreach ($manualInfo as $file => [$title, $desc]) {
    $path = AVA_DATA_DIR . '/manuals/' . $file;
    if (is_file($path)) {
        $manuals[] = ['url' => AVA_DATA_URL . '/manuals/' . rawurlencode($file) . '?v=' . filemtime($path),
            'title' => $title, 'desc' => $desc, 'size' => filesize($path), 'date' => filemtime($path)];
    }
}

ava_page_start('about', 'About', 'About AVA: the team, LCO programmes, manuals, collaborations, how to cite and acknowledgements.');
?>
<div class="container-xxl ava-page-head">
  <p class="ava-eyebrow">About AVA</p>
  <h1>The team behind the archive</h1>
  <p class="ava-lead">The AGN Variability Archive collects and systematically reduces the imaging and spectroscopy of the
    LCO Key Projects on intensive broadband reverberation mapping: <?= number_format($s['agn']) ?> AGN,
    <?= number_format($s['images']) ?> photometric images and <?= number_format($s['spectra']) ?> spectral epochs from
    <?= $s['years'] ?> years of monitoring, reduced by a single pipeline into one database. Read about the
    <a href="science.php">science behind it</a>.</p>
  <nav class="ava-toc" aria-label="On this page">
    <a href="#team">Team</a>
    <a href="#programmes">LCO programmes</a>
    <?php if ($manuals): ?><a href="#manuals">Manuals</a><?php endif; ?>
    <a href="#collaborations">Collaborations</a>
    <a href="#cite">How to cite</a>
    <a href="#funding">Funding &amp; credits</a>
  </nav>
</div>

<section class="pb-5" id="team">
  <div class="container-xxl">
    <h2 class="ava-h mt-0 mb-3">Principal Investigator</h2>
    <ul class="ava-team ava-team--pi">
      <li><strong>Juan V. Hernández Santisteban</strong><span>University of St Andrews</span></li>
    </ul>
    <h2 class="ava-h mt-4 mb-3">Co-investigators</h2>
    <ul class="ava-team">
      <?php foreach ($team as $name => $aff): ?><li><strong><?= h($name) ?></strong><?php if ($aff !== ''): ?><span><?= h($aff) ?></span><?php endif; ?></li><?php endforeach; ?>
    </ul>
    <h2 class="ava-h mt-4 mb-3">Previous members</h2>
    <ul class="ava-team ava-team--past">
      <?php foreach ($teamPrevious as $name): ?><li><?= h($name) ?></li><?php endforeach; ?>
    </ul>
  </div>
</section>

<section class="ava-section ava-section--alt" id="programmes">
  <div class="container-xxl">
    <div class="row g-5">
      <div class="col-lg-6 ava-prose">
        <p class="ava-eyebrow">LCO programmes</p>
        <h2>Four Key Projects, one archive</h2>
        <p>AVA started as a tool to follow incoming data from the LCO network in real time, and is growing into an open
          legacy database. Alongside the LCO data it will host coordinated, processed data sets from other facilities —
          Swift, HST, NICER — to add multi-wavelength context and legacy value to every target.</p>
      </div>
      <div class="col-lg-6">
        <div class="ava-programmes">
          <h3 class="h6 mb-3">Allocations contributing data to AVA</h3>
          <table class="table ava-info mb-0">
            <thead><tr><th>Programme</th><th>PI</th></tr></thead>
            <tbody>
              <?php foreach ($proposals as $p): ?>
                <tr><th><?= h($p) ?></th><td><?= h(ava_programme_pi($p)) ?></td></tr>
              <?php endforeach; ?>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</section>

<?php if ($manuals): ?>
<section class="ava-section" id="manuals">
  <div class="container-xxl">
    <p class="ava-eyebrow">Documentation</p>
    <h2 class="mb-2">Manuals</h2>
    <p class="text-secondary mb-4">How the archive is built, from raw LCO frames to the light curves and spectra on this site.</p>
    <div class="row g-3">
      <?php foreach ($manuals as $m): ?>
        <div class="col-md-6 col-xl-3">
          <a class="ava-manual" href="<?= h($m['url']) ?>" target="_blank" rel="noopener">
            <span class="ava-manual__type">PDF</span>
            <h3><?= h($m['title']) ?></h3>
            <p><?= h($m['desc']) ?></p>
            <span class="ava-manual__meta"><?= number_format($m['size'] / 1048576, 1) ?> MB · updated <?= date('j M Y', $m['date']) ?></span>
          </a>
        </div>
      <?php endforeach; ?>
    </div>
  </div>
</section>
<?php endif; ?>

<section class="ava-section" id="collaborations">
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
      <div class="col-lg-6 ava-prose" id="funding">
        <p class="ava-eyebrow">Support</p>
        <h2>Facilities, funding &amp; credits</h2>
        <p>AVA is based on observations from the <a href="https://lco.global/">Las Cumbres Observatory</a> global
          telescope network, obtained through the Key Projects listed above, and is developed at the
          <a href="https://www.st-andrews.ac.uk/physics-astronomy/">University of St Andrews</a>.</p>
        <?php /* TODO(PI): add grant acknowledgements (funder, grant number). */ ?>
        <h3 class="h6 mt-4 mb-2">Credits</h3>
        <p>The AVA pipeline was created by <?= h(AVA_PI) ?>. Version 2 — the current photometric and spectroscopic
          pipeline and this website — is based on, and improves, that original pipeline. It was designed by
          <?= h(AVA_PI) ?>, with development assistance from Claude Opus 5.5 (Anthropic).</p>
      </div>
    </div>
  </div>
</section>

<section class="ava-section ava-section--alt" id="cite">
  <div class="container-xxl">
    <div class="ava-cite-section">
      <p class="ava-eyebrow">Citation</p>
      <h2>How to cite &amp; acknowledgements</h2>
      <p>If you use AVA data or products, please cite:</p>
      <?php ava_citation_block(); ?>
    </div>
  </div>
</section>

<?php ava_page_end(); ?>
