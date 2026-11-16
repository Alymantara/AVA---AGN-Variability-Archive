<?php
/**
 * Shared page shell: <head>, sticky header, light-curve banner, footer.
 *
 *   require __DIR__ . '/includes/layout.php';
 *   ava_page_start('targets', 'Targets', 'Description for search engines');
 *   ... page body ...
 *   ava_page_end();
 */

declare(strict_types=1);

require_once __DIR__ . '/db.php';
require_once __DIR__ . '/filters.php';

const AVA_BS_CSS = 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css';
const AVA_BS_JS = 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js';

const AVA_NAV = [
    'home' => ['index.php', 'Home'],
    'targets' => ['targets.php', 'Targets'],
    'data' => ['data.php', 'Data &amp; Access'],
    'live' => ['live.php', 'Live Updates'],
    'publications' => ['publications.php', 'Publications'],
    'about' => ['about.php', 'About'],
];

function h(?string $s): string
{
    return htmlspecialchars((string) $s, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

/** Cache-busting URL for a local asset. */
function asset(string $path): string
{
    $f = AVA_ROOT . '/' . $path;
    return h($path) . (is_file($f) ? '?v=' . filemtime($f) : '');
}

function ava_page_start(string $active, string $title, string $description = ''): void
{
    $full = $active === 'home' ? AVA_SITE_NAME : $title . ' · AVA';
    $description = $description ?: 'AVA — the AGN Variability Archive: long-baseline reverberation mapping of active galactic nuclei with the Las Cumbres Observatory global telescope network.';
    ?>
<!doctype html>
<html lang="en" data-bs-theme="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title><?= h($full) ?></title>
  <meta name="description" content="<?= h($description) ?>">
  <meta name="theme-color" content="#0A1628">
  <link rel="icon" href="favicon.ico">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap">
  <link rel="stylesheet" href="<?= AVA_BS_CSS ?>">
  <link rel="stylesheet" href="<?= asset('assets/css/ava.css') ?>">
  <style><?= ava_filter_css() ?></style>
</head>
<body class="page-<?= h($active) ?>">
<a class="visually-hidden-focusable skip-link" href="#main">Skip to content</a>

<header class="ava-header sticky-top">
  <nav class="navbar navbar-expand-xl" aria-label="Main">
    <div class="container-xxl">
      <a class="navbar-brand ava-wordmark" href="index.php">
        <span class="ava-wordmark__ava">AVA</span>
        <span class="ava-wordmark__sub">AGN Variability Archive</span>
      </a>
      <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#avaNav"
              aria-controls="avaNav" aria-expanded="false" aria-label="Toggle navigation">
        <span class="navbar-toggler-icon"></span>
      </button>
      <div class="collapse navbar-collapse" id="avaNav">
        <ul class="navbar-nav mx-xl-auto">
          <?php foreach (AVA_NAV as $key => [$href, $label]): ?>
            <li class="nav-item">
              <a class="nav-link<?= $key === $active ? ' active' : '' ?>" href="<?= $href ?>"
                 <?= $key === $active ? 'aria-current="page"' : '' ?>><?= $label ?></a>
            </li>
          <?php endforeach; ?>
        </ul>
        <div class="ava-inst-logos">
          <a href="https://www.st-andrews.ac.uk/physics-astronomy/" title="University of St Andrews">
            <img src="<?= asset('assets/img/standrews_white.png') ?>" alt="University of St Andrews" width="500" height="156">
          </a>
          <a href="https://lco.global/" title="Las Cumbres Observatory">
            <img src="<?= asset('assets/img/lco_logo_white.png') ?>" alt="Las Cumbres Observatory" width="640" height="114">
          </a>
        </div>
      </div>
    </div>
  </nav>
</header>

<main id="main">
<?php
}

function ava_page_end(array $scripts = []): void
{
    $year = date('Y');
    ?>
</main>

<footer class="ava-footer">
  <div class="container-xxl">
    <div class="row gy-4">
      <div class="col-md-5">
        <div class="ava-wordmark ava-wordmark--footer">
          <span class="ava-wordmark__ava">AVA</span>
          <span class="ava-wordmark__sub">AGN Variability Archive</span>
        </div>
        <p class="small mt-2 mb-0">
          School of Physics &amp; Astronomy, University of St Andrews<br>
          Las Cumbres Observatory global telescope network
        </p>
      </div>
      <div class="col-6 col-md-3">
        <h2 class="ava-footer__h">Archive</h2>
        <ul class="list-unstyled small">
          <li><a href="targets.php">Targets</a></li>
          <li><a href="data.php">Data &amp; Access</a></li>
          <li><a href="data.php#cite">How to cite</a></li>
          <li><a href="publications.php">Publications</a></li>
        </ul>
      </div>
      <div class="col-6 col-md-4">
        <h2 class="ava-footer__h">Links</h2>
        <ul class="list-unstyled small">
          <li><a href="https://lco.global/">Las Cumbres Observatory</a></li>
          <li><a href="https://archive.lco.global/">LCO Science Archive</a></li>
          <li><a href="https://www.st-andrews.ac.uk/physics-astronomy/">St Andrews Physics &amp; Astronomy</a></li>
          <li><a href="https://github.com/FergusDonnan/PyROA">PyROA</a></li>
        </ul>
      </div>
    </div>
    <div class="ava-footer__base">
      <span>&copy; <?= AVA_COPYRIGHT_START ?>–<?= $year ?> J. Hernández Santisteban</span>
      <span>Data released under <a rel="license" href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a></span>
    </div>
  </div>
</footer>

<script src="<?= AVA_BS_JS ?>" defer></script>
<?php foreach ($scripts as $s): ?>
<script src="<?= asset($s) ?>" defer></script>
<?php endforeach; ?>
</body>
</html>
<?php
}

/** Number formatting helpers. */
function fmt_int(mixed $n): string
{
    return $n === null || $n === '' ? '—' : number_format((int) $n);
}

function fmt_num(mixed $n, int $dp = 2): string
{
    return $n === null || $n === '' || !is_numeric($n) ? '—' : number_format((float) $n, $dp);
}

function fmt_compact(int $n): string
{
    return $n >= 1000 ? number_format(floor($n / 1000)) . 'k+' : number_format($n);
}

function fmt_date(?string $d): string
{
    return $d ? date('M Y', strtotime($d)) : '—';
}

/** Card for the target grid. */
function ava_target_card(array $t): void
{
    $stem = ava_image_stem($t);
    $st = ava_status($t);
    $filters = ava_target_filters($t);
    ?>
  <article class="ava-card" data-name="<?= h(strtolower($t['name'] . ' ' . $t['simbad_name'])) ?>"
           data-status="<?= $st['key'] ?>" data-z="<?= h((string) $t['redshift']) ?>"
           data-frames="<?= (int) $t['db_lco_images'] ?>">
    <a class="ava-card__link" href="target.php?id=<?= (int) $t['id'] ?>">
      <div class="ava-card__img">
        <?php if ($stem): ?>
          <img src="assets/agn/<?= h(rawurlencode($stem)) ?>_600.webp" alt="Colour composite of <?= h($t['name']) ?>"
               width="600" height="600" loading="lazy" decoding="async">
        <?php else: ?>
          <div class="ava-card__noimg" aria-hidden="true"><span><?= h($t['name']) ?></span></div>
        <?php endif; ?>
        <span class="ava-badge ava-badge--<?= $st['key'] ?>"><?= $st['label'] ?></span>
      </div>
      <div class="ava-card__body">
        <h3 class="ava-card__title"><?= h($t['name']) ?></h3>
        <dl class="ava-card__meta">
          <div><dt>z</dt><dd><?= fmt_num($t['redshift'], 4) ?></dd></div>
          <div><dt>Type</dt><dd><?= h($t['AGN_type'] ?: '—') ?></dd></div>
          <div><dt>Frames</dt><dd><?= fmt_int($t['db_lco_images']) ?></dd></div>
        </dl>
        <?php if ($filters): ?>
          <ul class="ava-filters" aria-label="LCO filters">
            <?php foreach (array_keys($filters) as $f): ?>
              <li style="--c: var(<?= ava_filter_var($f) ?>)"><?= h($f) ?></li>
            <?php endforeach; ?>
          </ul>
        <?php endif; ?>
      </div>
    </a>
  </article>
<?php
}
