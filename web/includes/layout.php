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
    'data' => ['data.php', 'Data'],
    'live' => ['live.php', 'Live Updates'],
    'science' => ['science.php', 'Science'],
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
  <script>
    // Colour mode before first paint: saved choice, else dark (the AVA default).
    (function () {
      var t = 'dark';
      try { t = localStorage.getItem('ava-theme') === 'light' ? 'light' : 'dark'; } catch (e) {}
      document.documentElement.setAttribute('data-bs-theme', t);
      document.querySelector('meta[name=theme-color]').content = t === 'light' ? '#F7F6F2' : '#0A1628';
    })();
  </script>
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
      <div class="ava-header-end">
        <button class="ava-theme-toggle" type="button" id="avaTheme" aria-label="Switch to light mode" title="Switch to light mode">
          <svg class="i-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
          <svg class="i-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
        </button>
      <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#avaNav"
              aria-controls="avaNav" aria-expanded="false" aria-label="Toggle navigation">
        <span class="navbar-toggler-icon"></span>
      </button>
      </div>
      <div class="collapse navbar-collapse" id="avaNav">
        <ul class="navbar-nav mx-xl-auto">
          <?php foreach (AVA_NAV as $key => [$href, $label]): ?>
            <li class="nav-item">
              <a class="nav-link<?= $key === $active ? ' active' : '' ?>" href="<?= $href ?>"
                 <?= $key === $active ? 'aria-current="page"' : '' ?>><?= $label ?></a>
            </li>
          <?php endforeach; ?>
        </ul>
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
        <div class="ava-footer__logos">
          <a href="https://www.st-andrews.ac.uk/physics-astronomy/" title="University of St Andrews">
            <img class="ava-logo-d" src="<?= asset('assets/img/standrews_colour_dark.png') ?>" alt="University of St Andrews" width="638" height="120">
            <img class="ava-logo-l" src="<?= asset('assets/img/standrews_colour_light.png') ?>" alt="" width="638" height="120">
          </a>
          <a href="https://lco.global/" title="Las Cumbres Observatory">
            <img class="ava-logo-d" src="<?= asset('assets/img/lco_colour_dark.png') ?>" alt="Las Cumbres Observatory" width="709" height="120">
            <img class="ava-logo-l" src="<?= asset('assets/img/lco_colour_light.png') ?>" alt="" width="709" height="120">
          </a>
        </div>
      </div>
      <div class="col-6 col-md-3">
        <h2 class="ava-footer__h">Archive</h2>
        <ul class="list-unstyled small">
          <li><a href="targets.php">Targets</a></li>
          <li><a href="data.php">Data</a></li>
          <li><a href="about.php#cite">How to cite</a></li>
          <li><a href="science.php">Science</a></li>
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
<script src="<?= asset('assets/js/theme.js') ?>" defer></script>
<?php foreach ($scripts as $s): ?>
<script src="<?= asset($s) ?>" defer></script>
<?php endforeach; ?>
</body>
</html>
<?php
}

/** mailto link with the address written as HTML character references (less easy to harvest). */
function ava_mailto(string $email, string $subject = ''): string
{
    $enc = fn(string $s) => implode('', array_map(fn($c) => '&#' . ord($c) . ';', str_split($s)));
    $href = 'mailto:' . $email . ($subject !== '' ? '?subject=' . rawurlencode($subject) : '');
    return '<a href="' . $enc($href) . '">' . $enc($email) . '</a>';
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
           data-status="<?= $st['key'] ?>" data-campaign="<?= ava_campaign($t)['key'] ?>" data-z="<?= h((string) $t['redshift']) ?>"
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
