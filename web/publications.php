<?php
declare(strict_types=1);
require __DIR__ . '/includes/layout.php';
require __DIR__ . '/includes/publications.php';

$byYear = [];
foreach (AVA_PUBLICATIONS as $p) {
    $byYear[$p[3]][] = $p;
}
krsort($byYear);

ava_page_start('publications', 'Publications', 'Papers from the LCO Key Projects on intensive broadband reverberation mapping of AGN.');
?>
<div class="container-xxl ava-page-head">
  <p class="ava-eyebrow">Science output</p>
  <h1>Publications</h1>
  <p class="ava-lead"><?= count(AVA_PUBLICATIONS) ?> papers from the Las Cumbres Observatory Key Projects on intensive
    broadband reverberation mapping. If you use AVA data, see <a href="data.php#cite">how to cite</a>.</p>
</div>

<div class="container-xxl pb-5 ava-prose">
  <?php foreach ($byYear as $year => $pubs): ?>
    <h2 class="ava-year"><?= (int) $year ?></h2>
    <ul class="ava-pubs">
      <?php foreach ($pubs as [$title, $authors, $ref, , $ads]): ?>
        <li>
          <?php if ($ads): ?>
            <a class="title" href="<?= AVA_ADS . h($ads) ?>"><?= h($title) ?></a>
          <?php else: ?>
            <span class="title"><?= h($title) ?></span>
          <?php endif; ?>
          <div class="ref"><?= h($authors) ?> · <?= h($ref) ?></div>
        </li>
      <?php endforeach; ?>
    </ul>
  <?php endforeach; ?>
</div>

<?php ava_page_end(); ?>
