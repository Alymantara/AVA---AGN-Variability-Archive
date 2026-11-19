<?php
declare(strict_types=1);
require __DIR__ . '/includes/layout.php';

$targets = ava_targets();
$derivedAll = ava_derived_all();
$nCamp = array_count_values(array_map(fn($t) => ava_campaign($t)['key'], $targets));
$nActive = count(array_filter($targets, fn($t) => ava_status($t)['key'] === 'active'));
$view = ($_GET['view'] ?? '') === 'classic' ? 'classic' : (($_GET['view'] ?? '') === 'modern' ? 'modern' : '');

/** Legacy pipeline state (agn.ava) for the classic table. */
function classic_state(array $t): array
{
    return match ((int) ($t['ava'] ?? -1)) {
        2 => ['observing', 'Observing'],
        1 => ['archived', 'Archived'],
        0 => ['pending', 'TBP'],                      // to be processed (explained in the Notes and the tooltip)
        default => ['tba', 'tba'],
    };
}

// Recent cadence (observing_recent): mean spacing of the observing nights in the last 30 d, or 60 d when there
// were fewer than 2 nights in 30 d. Null on a database without the table: the all-time cadence is shown instead.
$recent = ava_recent_cadence();
$recentWin = 30;
$recentMax = 60;
if ($recent) {
    $ws = array_filter(array_merge(array_map(fn($r) => (int) $r['phot_window'], $recent),
        array_map(fn($r) => (int) $r['spec_window'], $recent)));
    $recentWin = $ws ? min($ws) : 30;
    $recentMax = $ws ? max($ws) : 60;
}

/** One cadence cell: "1.08", "6.0 · 60 d" (longer window), "1 visit", or "—"; tooltip with nights and last night. */
function recent_cell(?array $r, string $k, int $dp): string
{
    $n = $r ? (int) $r["{$k}_nights"] : 0;
    $cad = $r[$k . '_cadence'] ?? null;
    $w = $r ? (int) $r["{$k}_window"] : 0;
    $tip = $r && $n ? "$n night" . ($n > 1 ? 's' : '') . " in the last $w d; last " . $r["{$k}_last"] : '';
    if (is_numeric($cad)) {
        $txt = number_format((float) $cad, $dp);                     // the window used is in the tooltip
        $v = (float) $cad;
    } elseif ($n === 1) {
        $txt = '<span class="text-secondary">1 visit</span>';
        $v = 9000;
    } else {
        $txt = '—';
        $v = 9999;
    }
    return '<td class="num ava-cad" data-v="' . $v . '"' . ($tip ? ' title="' . h($tip) . '"' : '') . '>' . $txt . '</td>';
}

// Classic table: observing status first (Observing, Archived, to be processed, tba), then g mag (the column
// shown, from agn.Vmag; brightest first, no magnitude last), then name.
$classic = $targets;
$gmag = fn(array $t): float => is_numeric($t['Vmag'] ?? null) && (float) $t['Vmag'] > 0 ? (float) $t['Vmag'] : INF;
usort($classic, fn($a, $b) => ((int) ($b['ava'] ?? -1) <=> (int) ($a['ava'] ?? -1))
    ?: ($gmag($a) <=> $gmag($b))
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
      <input type="radio" class="btn-check" name="status" id="st-archived" value="archived">
      <label class="btn btn-sm" for="st-archived">Archived</label>
      <input type="radio" class="btn-check" name="status" id="st-pending" value="pending">
      <label class="btn btn-sm" for="st-pending">To be processed</label>
    </div>
    <label class="visually-hidden" for="campaign">Campaign type</label>
    <select class="form-select form-select-sm w-auto" id="campaign" title="Campaign type">
      <option value="all">All campaigns</option>
      <option value="ibrm">IBRM (<?= $nCamp['ibrm'] ?? 0 ?>)</option>
      <option value="few">Few-band monitoring (<?= $nCamp['few'] ?? 0 ?>)</option>
      <option value="sparse">Sparse / no data (<?= $nCamp['sparse'] ?? 0 ?>)</option>
    </select>
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
    <details class="ava-notes small ava-legend mb-2">
      <summary>Notes</summary>
        <span class="st-observing">Observing</span> = data collected in the last 30 days ·
        <span class="st-archived">Archived</span> = all available data processed and archived ·
        <span class="st-pending">TBP</span> (to be processed) = observed in the past, no longer observing, and its data <strong>not</strong> yet processed by the AVA pipeline.
        Ordered by status, then g<sub>mag</sub> (brightest first); click a column header to sort.<br>
        <?php if ($recent !== null): ?>
        <strong>Current</strong>: status, and cadence = mean spacing (days) of the LCO imaging / FLOYDS nights in the last
        <?= $recentWin ?> days, or over the last <?= $recentMax ?> days when there were fewer than two nights in that time (the tooltip says which); <em>1 visit</em> = a
        single night. The full-history cadence is on each target's page.<br>
        <?php endif; ?>
        <strong>IBRM</strong> = intensive broadband reverberation mapping: ≥<?= AVA_IBRM_MIN_BANDS ?> LCO filters with
        ≥<?= AVA_IBRM_MIN_FRAMES ?> frames each and ≥<?= AVA_IBRM_MIN_VISITS ?> visits (or still observing) ·
        <strong>Few-band</strong> = regular monitoring in fewer filters (mostly V-band support for spectroscopic RM) ·
        <strong>Sparse</strong> = fewer than <?= AVA_IBRM_MIN_VISITS ?> visits.
    </details>
    <div class="ava-table-wrap">
      <table class="table table-hover ava-table ava-classic" id="classic">
        <thead class="ava-thead-2">
          <tr>
            <th rowspan="2" data-sort="num" class="num">ID</th>
            <th rowspan="2" data-sort="text">Name</th>
            <th rowspan="2" data-sort="text">RA<br><small>(hms)</small></th>
            <th rowspan="2" data-sort="text">Dec<br><small>(dms)</small></th>
            <th rowspan="2" data-sort="num" class="num">g<sub>mag</sub></th>
            <th rowspan="2" data-sort="num" class="num">log L<sub>Bol</sub><br><small>(erg/s)</small></th>
            <th rowspan="2" data-sort="num" class="num">log M<sub>●</sub><br><small>(M<sub>☉</sub>)</small></th>
            <th rowspan="2" data-sort="num" class="num">z</th>
            <th rowspan="2" data-sort="text">LCO<br>filters</th>
            <th colspan="3" class="ava-th-group"><?= $recent !== null
                ? 'Current <small class="ava-th-note">(cadence in days)</small>'
                : 'Status <small class="ava-th-note">(cadence in days, all data)</small>' ?></th>
          </tr>
          <tr>
            <th data-sort="num" data-col="9">Status</th>
            <th data-sort="num" data-col="10" class="num ava-cad">Photo</th>
            <th data-sort="num" data-col="11" class="num ava-cad">Spec</th>
          </tr>
        </thead>
        <tbody>
          <?php foreach ($classic as $t):
              [$sk, $sl] = classic_state($t);
              $href = 'target.php?id=' . (int) $t['id'];
              $pcad = (float) ($t['db_lco_cadence'] ?: $t['lco_cadence']);
              $scad = (float) ($t['db_floyds_cadence'] ?: $t['floyds_cadence']); ?>
            <tr data-name="<?= h(strtolower($t['name'] . ' ' . $t['simbad_name'])) ?>" data-status="<?= ava_status($t)['key'] ?>" data-campaign="<?= ava_campaign($t)['key'] ?>">
              <td class="num"><a href="<?= $href ?>"><?= (int) $t['id'] ?></a></td>
              <th scope="row"><a href="<?= $href ?>"><?= h($t['name']) ?></a></th>
              <td><?= h($t['ra']) ?></td>
              <td><?= h($t['dec']) ?></td>
              <td class="num"><?= fmt_num($t['Vmag'], 2) ?></td>
              <td class="num"><?= fmt_num(ava_log_lbol($t, $derivedAll[$t['data_id']] ?? null), 2) ?></td>
              <td class="num"><?= fmt_num($t['logm'], 2) ?></td>
              <td class="num"><?= fmt_num($t['redshift'], 4) ?></td>
              <td class="filters"><?php foreach (array_keys(ava_target_filters($t)) as $f): ?><span style="color: var(<?= ava_filter_var($f) ?>)"><?= h($f) ?></span><?php endforeach; ?></td>
              <td data-v="<?= (int) $t['ava'] ?>"><span class="st-<?= $sk ?>"<?= $sk === 'pending' ? ' title="To be processed"' : '' ?>><?= h($sl) ?></span></td>
              <?php if ($recent !== null): $rc = $recent[$t['data_id']] ?? null; ?>
              <?= recent_cell($rc, 'phot', 1) ?>
              <?= recent_cell($rc, 'spec', 1) ?>
              <?php else: ?>
              <td class="num ava-cad"><?= $pcad > 0 ? number_format($pcad, 1) : '—' ?></td>
              <td class="num ava-cad"><?= $scad > 0 ? number_format($scad, 1) : '—' ?></td>
              <?php endif; ?>
            </tr>
          <?php endforeach; ?>
        </tbody>
      </table>
    </div>
  </div>

  <p class="text-secondary mt-4" id="empty" hidden>No targets match.</p>
</div>

<?php ava_page_end(['assets/js/targets.js', 'assets/js/sort-table.js']); ?>
