<?php
/**
 * Data releases (ava.database.releases → data_releases, agn_releases, release_files).
 *
 * An AGN gets download links for a release when agn_releases.available = 1 and the
 * release is public (release_date set and not in the future). The files themselves are
 * published to AVA_DATA_DIR/releases/<release>/<path> by ava.web.releases, which copies
 * exactly that set, so a link is only shown when its file is there.
 */

declare(strict_types=1);

require_once __DIR__ . '/db.php';
require_once __DIR__ . '/plots.php';      // ava_downloads(), fmt_bytes()

/** Public releases with this AGN flagged available: [release => ['meta' => row, 'files' => rows]]. */
function ava_agn_releases(string $dataId): array
{
    if ($dataId === '' || !ava_has_table('agn_releases') || !ava_has_table('release_files')
        || !ava_has_table('data_releases')) {
        return [];
    }
    $st = ava_db()->prepare(
        "SELECT r.*, f.path, f.kind, f.bytes, f.sha256
           FROM agn_releases a
           JOIN data_releases r ON r.release = a.release
           JOIN release_files f ON f.release = a.release AND f.data_id = a.data_id
          WHERE a.data_id = ? AND a.available = 1
            AND r.release_date IS NOT NULL AND date(r.release_date) <= date('now')
          ORDER BY r.release, f.kind, f.path");
    $st->execute([$dataId]);
    $out = [];
    foreach ($st as $row) {
        $rel = $row['release'];
        if (!is_file(AVA_DATA_DIR . '/releases/' . $rel . '/' . $row['path'])) {
            continue;                                  // registered but not published yet
        }
        $out[$rel] ??= ['meta' => $row, 'files' => []];
        $out[$rel]['files'][] = $row;
    }
    return $out;
}

/** Public URL of one release file (each path segment encoded). */
function ava_release_url(string $release, string $path): string
{
    return ava_data_url('releases/' . $release . '/' . $path);
}

function ava_bytes(?int $n): string
{
    $n = (int) $n;
    foreach (['B', 'kB', 'MB', 'GB'] as $i => $u) {
        if ($n < 1000 ** ($i + 1) || $u === 'GB') {
            return $i === 0 ? "$n B" : number_format($n / 1000 ** $i, 1) . " $u";
        }
    }
    return "$n B";
}

/** [group, label] for a release file, named like the target page's Download menu (includes/plots.php). */
function ava_release_label(string $path, ?string $kind): array
{
    $name = basename($path);
    foreach ([
        '_LCO_merged_lightcurve.csv' => ['Photometry', 'Merged light curve (CSV)'],
        '_FLOYDS_Hbeta_lightcurve.csv' => ['Spectra', 'H&beta; light curve (CSV)'],
        '_FLOYDS_prepspec.zip' => ['Spectra', 'PrepSpec input (zip)'],
        '_FLOYDS_1d.zip' => ['Spectra', '1-d FLOYDS spectra (FITS, zip)'],
    ] as $suffix => $gl) {
        if (str_ends_with($name, $suffix)) {
            return $gl;
        }
    }
    $group = match ($kind) { 'photometry' => 'Photometry', 'spectroscopy', 'spectra' => 'Spectra', default => ucfirst((string) $kind) };
    return [$group ?: 'Data', h($name)];
}

/**
 * Rows of one release for the table: [group, label, url|null, bytes|null, tooltip, note].
 *
 * Until releases carry their own spectra (the DR1 date cut is not decided yet), the target's current PrepSpec
 * and 1-d FLOYDS zips (data/downloads/, all dates) are listed with the release when it has none of its own.
 */
function ava_release_rows(string $rel, array $files, string $dataId): array
{
    $rows = [];
    foreach ($files as $f) {
        [$g, $label] = ava_release_label($f['path'], $f['kind']);
        $rows[$label] = [$g, $label, ava_release_url($rel, $f['path']), (int) $f['bytes'],
            basename($f['path']) . ' · SHA-256 ' . $f['sha256'], ''];
    }
    foreach (ava_downloads($dataId) as $k => [$g, $label, $url, $bytes, $note]) {
        if (in_array($k, ['prepspec', 'spec'], true) && !isset($rows[$label])
            && ($url !== null || $note !== 'not available')) {
            $rows[$label] = [$g, $label, $url, $bytes,
                $url ? rawurldecode(basename((string) parse_url($url, PHP_URL_PATH))) . ' · current full set (all dates)' : '', $note];
        }
    }
    $order = ['Photometry' => 0, 'Spectra' => 1];
    uasort($rows, fn($a, $b) => ($order[$a[0]] ?? 2) <=> ($order[$b[0]] ?? 2));
    return array_values($rows);
}

/** "Data releases" section of the target page; prints nothing when the AGN has no public release. */
function ava_release_panel(array $t): void
{
    $dataId = (string) ($t['data_id'] ?? '');
    $rels = ava_agn_releases($dataId);
    if (!$rels) {
        return;
    }
    ?>
      <h2 class="ava-h" id="downloads">Data releases</h2>
      <?php foreach ($rels as $rel => $r): $m = $r['meta']; $group = null; ?>
      <div class="ava-release">
      <p class="ava-release__title"><?= h($m['title'] ?: $rel) ?></p>
      <p class="ava-release__meta">
        <?php if ($m['date_start'] && $m['date_end']): ?>
          data <?= h(substr($m['date_start'], 0, 10)) ?> → <?= h(substr($m['date_end'], 0, 10)) ?> ·
        <?php endif; ?>
        released <?= h(substr($m['release_date'], 0, 10)) ?></p>
      <?php if ($m['description']): ?><p class="ava-release__desc"><?= h($m['description']) ?></p><?php endif; ?>
      <ul class="ava-release__files">
        <?php foreach (ava_release_rows($rel, $r['files'], $dataId) as [$g, $label, $url, $bytes, $tip, $note]): ?>
          <?php if ($g !== $group): $group = $g; ?>
            <li class="ava-release__group"><?= h($g) ?></li>
          <?php endif; ?>
          <li class="ava-release__file">
            <span class="ava-release__label"><?= $label ?></span>
            <?php if ($url): ?>
              <span class="ava-dl-size"><?= fmt_bytes($bytes) ?></span>
              <a class="btn btn-sm ava-release__btn" href="<?= h($url) ?>" download title="<?= h($tip) ?>"
                 aria-label="Download <?= h(strip_tags(html_entity_decode($label))) ?>">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12M7 10l5 5 5-5M4 20h16"/></svg>
              </a>
            <?php else: ?>
              <span class="ava-dl-size"><?= h($note) ?></span>
            <?php endif; ?>
          </li>
        <?php endforeach; ?>
      </ul>
      </div>
      <p class="small text-secondary">
        <?php if ($m['doi']): ?>DOI <a href="https://doi.org/<?= h($m['doi']) ?>"><?= h($m['doi']) ?></a>. <?php endif; ?>
        <?php if ($m['url']): ?><a href="<?= h($m['url']) ?>">Release notes</a>. <?php endif; ?>
        File formats: <a href="data.php#format">Data</a>. Released under
        <a rel="license" href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a>; please
        <a href="about.php#cite">cite AVA</a>.</p>
      <?php endforeach;
}
