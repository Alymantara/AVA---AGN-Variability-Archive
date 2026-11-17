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
    $parts = array_map('rawurlencode', explode('/', $release . '/' . $path));
    return AVA_DATA_URL . '/releases/' . implode('/', $parts);
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

/** "Data releases" section of the target page; prints nothing when the AGN has no public release. */
function ava_release_panel(array $t): void
{
    $rels = ava_agn_releases((string) ($t['data_id'] ?? ''));
    if (!$rels) {
        return;
    }
    ?>
      <h2 class="ava-h" id="downloads">Data releases</h2>
      <?php foreach ($rels as $rel => $r): $m = $r['meta']; ?>
      <p class="mb-1"><strong><?= h($m['title'] ?: $rel) ?></strong>
        <?php if ($m['date_start'] && $m['date_end']): ?>
          <span class="text-secondary">· data <?= h(substr($m['date_start'], 0, 10)) ?> → <?= h(substr($m['date_end'], 0, 10)) ?></span>
        <?php endif; ?>
        <span class="text-secondary">· released <?= h(substr($m['release_date'], 0, 10)) ?></span></p>
      <?php if ($m['description']): ?><p class="small text-secondary mb-1"><?= h($m['description']) ?></p><?php endif; ?>
      <div class="table-responsive">
      <table class="table ava-info">
        <thead><tr><th>File</th><th>Content</th><th class="num">Size</th></tr></thead>
        <tbody>
          <?php foreach ($r['files'] as $f): ?>
          <tr><td><a href="<?= h(ava_release_url($rel, $f['path'])) ?>" download
                     title="SHA-256 <?= h($f['sha256']) ?>"><?= h(basename($f['path'])) ?></a></td>
            <td><?= h($f['kind']) ?></td><td class="num"><?= ava_bytes((int) $f['bytes']) ?></td></tr>
          <?php endforeach; ?>
        </tbody>
      </table>
      </div>
      <p class="small text-secondary">
        <?php if ($m['doi']): ?>DOI <a href="https://doi.org/<?= h($m['doi']) ?>"><?= h($m['doi']) ?></a>. <?php endif; ?>
        <?php if ($m['url']): ?><a href="<?= h($m['url']) ?>">Release notes</a>. <?php endif; ?>
        File formats: <a href="data.php#format">Data</a>. Released under
        <a rel="license" href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a>; please
        <a href="about.php#cite">cite AVA</a>.</p>
      <?php endforeach;
}
