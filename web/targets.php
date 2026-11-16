<?php
declare(strict_types=1);
require __DIR__ . '/includes/layout.php';

$targets = ava_targets();
$nActive = count(array_filter($targets, fn($t) => ava_status($t)['key'] === 'active'));
$view = ($_GET['view'] ?? '') === 'classic' ? 'classic' : (($_GET['view'] ?? '') === 'modern' ? 'modern' : '');

/** Legacy pipeline state (agn.ava) for the classic table. */
function classic_state(array $t): array
{
    return match ((int) ($t['ava'] ?? -1)) {
        2 => ['observing', 'Observing'],
        1 => ['archived', 'Archived'],
        0 => ['pending', 'to be processed'],
        default => ['tba', 'tba'],
    };
}

// Classic table: observing status first (Observing, Archived, to be processed, tba), then name.
$classic = $targets;
$hbeta = ava_hbeta_all();   // data_id => Hβ variability (spectroscopy products)
usort($classic, fn($a, $b) => ((int) ($b['ava'] ?? -1) <=> (int) ($a['ava'] ?? -1))
    ?: strnatcasecmp((string) $a['name'], (string) $b['name']));

ava_page_start('targets', 'Targets', 'All AGN monitored by AVA with the Las Cumbres Observatory network.');
?>
<script>
  // Apply the saved view before the content paints (no flash).
  (function () {
    var v = <?= json_encode($view) ?>;
    try { if (!v) v = localStorage.getItem('ava-view') || 'classic'; } catch (e) { v = v || 'classic'; }
    document.documentElement.dataset.view = v;
  })();
</script>

<div class="container-xxl ava-page-head pb-3">
  <p class="ava-eyebrow">The sample</p>
  <h1>Targets</h1>
  <p class="ava-lead mb-0"><?= count($targets) ?> active galactic nuclei, <?= $nActive ?> of them actively monitored.
    Select a target for its data summary, light curves and diagnostics.</p>
</div>

<div class="container-xxl pb-5">
  <form class="ava-toolbar" role="search" onsubmit="return false">
    <div class="btn-group" role="group" aria-label="View">
      <input type="radio" class="btn-check" name="view" id="v-classic" value="classic">
      <label class="btn btn-sm" for="v-classic">Classic table</label>
      <input type="radio" class="btn-check" name="view" id="v-modern" value="modern">
      <label class="btn btn-sm" for="v-modern">Cards</label>
    </div>
    <label class="visually-hidden" for="q">Search targets</label>
    <input class="form-control form-control-sm ava-search" id="q" type="search" placeholder="Search by name…" autocomplete="off">
    <div class="btn-group" role="group" aria-label="Status">
      <input type="radio" class="btn-check" name="status" id="st-all" value="all" checked>
      <label class="btn btn-sm" for="st-all">All</label>
      <input type="radio" class="btn-check" name="status" id="st-active" value="active">
      <label class="btn btn-sm" for="st-active">Active</label>
      <input type="radio" class="btn-check" name="status" id="st-archive" value="archive">
      <label class="btn btn-sm" for="st-archive">Archive</label>
    </div>
    <span class="ava-view-modern">
      <label class="visually-hidden" for="sort">Sort cards by</label>
      <select class="form-select form-select-sm w-auto" id="sort">
        <option value="name">Name</option>
        <option value="z">Redshift</option>
        <option value="frames">Most frames</option>
      </select>
    </span>
    <span class="ava-count" id="count" aria-live="polite"><?= count($targets) ?> targets</span>
  </form>

  <!-- Modern: image cards -->
  <div class="ava-grid ava-view-modern" id="grid">
    <?php foreach ($targets as $t) { ava_target_card($t); } ?>
  </div>

  <!-- Classic: the original AVA table -->
  <div class="ava-view-classic">
    <p class="small ava-legend">
      <span class="st-observing">Observing</span> = data collected in the last 30 days ·
      <span class="st-archived">Archived</span> = all available data processed and archived ·
      <span class="st-pending">to be processed</span> = observed but <strong>not</strong> archived.
      Click a column header to sort.
    </p>
    <div class="ava-table-wrap">
      <table class="table table-hover ava-table ava-classic" id="classic">
        <thead>
          <tr>
            <th data-sort="num" class="num">ID</th>
            <th data-sort="text">Name</th>
            <th data-sort="text">RA<br><small>(hms)</small></th>
            <th data-sort="text">Dec<br><small>(dms)</small></th>
            <th data-sort="num" class="num">g<sub>mag</sub></th>
            <th data-sort="num" class="num">log L<sub>Bol</sub><br><small>(erg/s)</small></th>
            <th data-sort="num" class="num">log M<sub>●</sub><br><small>(M<sub>☉</sub>)</small></th>
            <th data-sort="num" class="num">z</th>
            <th data-sort="text">LCO<br>filters</th>
            <th data-sort="num" class="num">Frames</th>
            <th data-sort="num" class="num">Photo<br>⟨Δt⟩/d</th>
            <th data-sort="num" class="num">Spec<br>⟨Δt⟩/d</th>
            <th data-sort="num" class="num">Spec<br>epochs</th>
            <th data-sort="num" class="num">H&beta;<br>F<sub>var</sub></th>
            <th data-sort="num">Status</th>
          </tr>
        </thead>
        <tbody>
          <?php foreach ($classic as $t):
              [$sk, $sl] = classic_state($t);
              $href = 'target.php?id=' . (int) $t['id'];
              $pcad = (float) ($t['db_lco_cadence'] ?: $t['lco_cadence']);
              $scad = (float) ($t['db_floyds_cadence'] ?: $t['floyds_cadence']); ?>
            <tr data-name="<?= h(strtolower($t['name'] . ' ' . $t['simbad_name'])) ?>" data-status="<?= ava_status($t)['key'] ?>">
              <td class="num"><a href="<?= $href ?>"><?= (int) $t['id'] ?></a></td>
              <th scope="row"><a href="<?= $href ?>"><?= h($t['name']) ?></a></th>
              <td><?= h($t['ra']) ?></td>
              <td><?= h($t['dec']) ?></td>
              <td class="num"><?= fmt_num($t['Vmag'], 2) ?></td>
              <td class="num"><?= fmt_num($t['logl'], 2) ?></td>
              <td class="num"><?= fmt_num($t['logm'], 2) ?></td>
              <td class="num"><?= h((string) $t['redshift']) ?></td>
              <td class="filters"><?php foreach (array_keys(ava_target_filters($t)) as $f): ?><span style="color: var(<?= ava_filter_var($f) ?>)"><?= h($f) ?></span><?php endforeach; ?></td>
              <td class="num"><?= fmt_int($t['db_lco_images']) ?></td>
              <td class="num"><?= $pcad > 0 ? number_format($pcad, 2) : '—' ?></td>
              <td class="num"><?= $scad > 0 ? number_format($scad, 1) : '—' ?></td>
              <td class="num"><?= fmt_int($t['db_floyds_epochs'] ?: null) ?></td>
              <?php $hb = $hbeta[$t['data_id']] ?? null; ?>
              <td class="num" data-v="<?= $hb && is_numeric($hb['fvar']) ? (float) $hb['fvar'] : '' ?>"
                  <?= $hb ? 'title="' . (int) $hb['n_nights'] . ' nights, F_max/F_min ' . number_format((float) $hb['rmax'], 2) . '"' : '' ?>><?=
                  $hb && is_numeric($hb['fvar']) ? number_format(100 * (float) $hb['fvar'], 1) . '%' : '—' ?></td>
              <td data-v="<?= (int) $t['ava'] ?>"><span class="st-<?= $sk ?>"><?= h($sl) ?></span></td>
            </tr>
          <?php endforeach; ?>
        </tbody>
      </table>
    </div>
  </div>

  <p class="text-secondary mt-4" id="empty" hidden>No targets match.</p>
</div>

<?php ava_page_end(['assets/js/targets.js', 'assets/js/sort-table.js']); ?>
