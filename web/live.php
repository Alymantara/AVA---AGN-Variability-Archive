<?php
declare(strict_types=1);
require __DIR__ . '/includes/layout.php';
require __DIR__ . '/includes/live.php';

$projects = ava_project_semesters();
$current = ava_current_semester();
$defaultProject = array_key_last($projects);

// Targets observed recently, straight from the database.
$recent = array_filter(ava_targets(), fn($t) => !empty($t['db_lco_end']));
usort($recent, fn($a, $b) => strcmp((string) $b['db_lco_end'], (string) $a['db_lco_end']));
$recent = array_slice($recent, 0, 12);

ava_page_start('live', 'Live Updates', 'LCO Key Project time usage per semester and the latest AVA observations.');
?>
<div class="container-xxl ava-page-head">
  <h1>Live updates</h1>
  <p class="ava-intro">Semester <?= h($current) ?>: usage of the allocated 1-m and 2-m time per semester (dotted black line: total time / days in
    semester) against the time used on the 1-m (green), 2-m FLOYDS (red) and 2-m MuSCAT3 (purple). Numbers come from
    the LCO API and are refreshed every 6 hours. For daily allocations see the
    <a href="https://schedule.lco.global/">LCO daily schedule</a>.</p>
</div>

<div class="container-xxl pb-5">
  <h2 class="ava-h mt-0">Semester usage</h2>

  <ul class="nav nav-tabs ava-tabs" role="tablist">
    <?php foreach ($projects as $p => $sems): ?>
      <li class="nav-item" role="presentation">
        <button class="nav-link<?= $p === $defaultProject ? ' active' : '' ?>" data-bs-toggle="tab" data-bs-target="#proj-<?= h($p) ?>"
                type="button" role="tab" aria-selected="<?= $p === $defaultProject ? 'true' : 'false' ?>">Key Project <?= h($p) ?></button>
      </li>
    <?php endforeach; ?>
  </ul>

  <div class="tab-content">
    <?php foreach ($projects as $p => $sems): $last = end($sems); ?>
      <div class="tab-pane fade<?= $p === $defaultProject ? ' show active' : '' ?>" id="proj-<?= h($p) ?>" role="tabpanel">
        <ul class="nav nav-pills ava-tabs" role="tablist">
          <?php foreach ($sems as $s): ?>
            <li class="nav-item" role="presentation">
              <button class="nav-link<?= $s === $last ? ' active' : '' ?>" data-bs-toggle="tab" data-bs-target="#sem-<?= h($s) ?>"
                      type="button" role="tab"><?= h($s) ?><?= $s === $current ? ' ●' : '' ?></button>
            </li>
          <?php endforeach; ?>
        </ul>
        <div class="tab-content">
          <?php foreach ($sems as $s): $u = ava_usage_url($s); ?>
            <div class="tab-pane fade<?= $s === $last ? ' show active' : '' ?>" id="sem-<?= h($s) ?>" role="tabpanel">
              <?php if ($u): ?>
                <a class="ava-plot ava-usage" href="<?= h($u) ?>" target="_blank" rel="noopener" title="Open full size">
                  <img src="<?= h($u) ?>" alt="LCO time usage, semester <?= h($s) ?>" loading="lazy"></a>
              <?php else: ?>
                <div class="ava-noplots">The usage plot for <?= h($s) ?> has not been published yet.</div>
              <?php endif; ?>
            </div>
          <?php endforeach; ?>
        </div>
      </div>
    <?php endforeach; ?>
  </div>

  <details class="ava-collapse mt-5">
    <summary><h2 class="ava-h m-0">Latest observations</h2>
      <span class="ava-collapse__hint"><?= count($recent) ?> most recently observed AGN</span></summary>
  <div class="ava-table-wrap mt-3" style="max-height:none">
    <table class="table table-hover ava-table">
      <thead><tr><th>AGN</th><th>Last image</th><th class="num">Frames</th><th class="num">Cadence (d)</th><th>Last spectrum</th><th class="num">Spectral epochs</th></tr></thead>
      <tbody>
        <?php foreach ($recent as $t): ?>
          <tr>
            <th scope="row"><a href="target.php?id=<?= (int) $t['id'] ?>"><?= h($t['name']) ?></a></th>
            <td><?= h((string) $t['db_lco_end']) ?></td>
            <td class="num"><?= fmt_int($t['db_lco_images']) ?></td>
            <td class="num"><?= fmt_num($t['db_lco_cadence'], 2) ?></td>
            <td><?= h((string) ($t['db_floyds_end'] ?: '—')) ?></td>
            <td class="num"><?= fmt_int($t['db_floyds_epochs'] ?: null) ?></td>
          </tr>
        <?php endforeach; ?>
      </tbody>
    </table>
  </div>
  </details>
  <p class="small text-secondary mt-2">From the archive database snapshot of <?= gmdate('Y-m-d H:i', (int) filemtime(AVA_DB_PATH)) ?> UTC.</p>
</div>

<?php ava_page_end(); ?>
