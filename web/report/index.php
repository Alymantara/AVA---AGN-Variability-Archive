<?php
/**
 * Daily status: an unlisted page at <site>/report/ (no link from the rest of the site, not indexed; public).
 * Reads <data>/report/daily_report.json, written each morning by scripts/daily_check.py --web (ava.web.report).
 * The report holds no paths, host names or log text; the full report is in the cron mail.
 */
declare(strict_types=1);
const AVA_BASE = '../';      // this page is one folder down: links resolve from the site root
const AVA_NOINDEX = true;
const AVA_REPORT_STALE_H = 26;   // the check runs daily at 07:00 UTC
require __DIR__ . '/../includes/layout.php';

$dir = AVA_DATA_DIR . '/report';
header('X-Robots-Tag: noindex, nofollow');
header('Cache-Control: no-store');

$r = json_decode((string) @file_get_contents("$dir/daily_report.json"), true) ?: null;
if ($r) {   // failures first, then warnings, then the rest (in their original order)
    $rank = ['fail' => 0, 'warn' => 1];
    $items = $r['items'] ?? [];
    $order = array_keys($items);
    usort($order, fn($a, $b) => ($rank[$items[$a]['level']] ?? 2) <=> ($rank[$items[$b]['level']] ?? 2) ?: $a <=> $b);
    $r['items'] = array_map(fn($i) => $items[$i], $order);
}
$checked = $r ? strtotime((string) $r['checked_utc']) : null;
$ageH = $checked ? (time() - $checked) / 3600 : null;
$stale = $ageH === null || $ageH > AVA_REPORT_STALE_H;
$status = $r['status'] ?? 'missing';
$label = ['passed' => 'All good', 'warnings' => 'Warnings', 'failed' => 'Needs attention', 'missing' => 'No report'][$status] ?? $status;
$levelLabel = ['ok' => 'OK', 'warn' => 'Warning', 'fail' => 'Failed'];

ava_page_start('report', 'Daily status');
?>
<div class="container-xxl ava-page-head">
  <h1>Daily status</h1>
  <p class="ava-lead mb-0">Result of the morning check of the scheduled AVA jobs. The full report is in the email.</p>
</div>

<div class="container-xxl pb-5 ava-report">
  <div class="ava-report__banner is-<?= h($stale && $status !== 'failed' ? 'warnings' : $status) ?>">
    <strong><?= h($label) ?></strong>
    <?php if ($r): ?>
      <span><?= (int) $r['failures'] ?> failure<?= (int) $r['failures'] === 1 ? '' : 's' ?>,
        <?= (int) $r['warnings'] ?> warning<?= (int) $r['warnings'] === 1 ? '' : 's' ?> ·
        checked <?= gmdate('D j M Y, H:i', $checked) ?> UTC</span>
    <?php endif; ?>
  </div>
  <?php if ($stale): ?>
    <p class="ava-report__stale"><?= $r ? 'This report is ' . (int) round($ageH) . ' h old: the morning check may not have run.'
      : 'No report has been written yet.' ?></p>
  <?php endif; ?>

  <?php if ($r && $r['items']): ?>
    <table class="table ava-table ava-report__table mt-4">
      <thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead>
      <tbody>
        <?php foreach ($r['items'] as $it): $lv = (string) $it['level']; ?>
          <tr class="is-<?= h($lv) ?>">
            <th scope="row"><?= h((string) $it['check']) ?></th>
            <td><span class="ava-report__dot"></span><?= h($levelLabel[$lv] ?? $lv) ?></td>
            <td><?= h((string) $it['text']) ?></td>
          </tr>
        <?php endforeach; ?>
      </tbody>
    </table>
  <?php endif; ?>

  <?php if ($r && count($r['history'] ?? []) > 1): ?>
    <h2 class="ava-h mt-5">Last <?= count($r['history']) ?> days</h2>
    <ol class="ava-report__history" aria-label="Daily results">
      <?php foreach ($r['history'] as $d): $s = (string) $d['status']; ?>
        <li class="is-<?= h($s) ?>" title="<?= h($d['day'] . ': ' . ($label = ['passed' => 'all good', 'warnings' => 'warnings', 'failed' => 'failed'][$s] ?? $s)) ?>">
          <span><?= h(date('j M', strtotime((string) $d['day']))) ?></span><b><?= h($label) ?></b></li>
      <?php endforeach; ?>
    </ol>
  <?php endif; ?>
</div>

<?php ava_page_end(); ?>
