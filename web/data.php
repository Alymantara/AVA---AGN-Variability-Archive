<?php
declare(strict_types=1);
require __DIR__ . '/includes/layout.php';

$targets = ava_targets();
usort($targets, fn($a, $b) => (int) $b['db_lco_images'] <=> (int) $a['db_lco_images']);
$s = ava_stats();
$fdict = ava_filter_dict();

// Contact form (sends only if AVA_CONTACT_TO is configured on the server).
$sent = null;
$err = [];
if (($_SERVER['REQUEST_METHOD'] ?? '') === 'POST') {
    $name = trim((string) ($_POST['name'] ?? ''));
    $email = trim((string) ($_POST['email'] ?? ''));
    $msg = trim((string) ($_POST['message'] ?? ''));
    if (($_POST['website'] ?? '') !== '') {          // honeypot
        $sent = true;
    } else {
        if ($name === '' || strlen($name) > 120) { $err['name'] = 'Please enter your name.'; }
        if (!filter_var($email, FILTER_VALIDATE_EMAIL)) { $err['email'] = 'Please enter a valid email address.'; }
        if (strlen($msg) < 10 || strlen($msg) > 5000) { $err['message'] = 'Please write a message (10–5000 characters).'; }
        if (!$err) {
            if (AVA_CONTACT_TO === '') {
                $err['form'] = 'The contact form is not configured on this server yet.';
            } else {
                $body = "From: $name <$email>\n\n$msg\n";
                $sent = mail(AVA_CONTACT_TO, '[AVA] Data enquiry from ' . preg_replace('/[\r\n]+/', ' ', $name), $body,
                    ['Reply-To' => $email, 'Content-Type' => 'text/plain; charset=UTF-8']);
                if (!$sent) { $err['form'] = 'Sorry, the message could not be sent. Please try again later.'; }
            }
        }
    }
}

ava_page_start('data', 'Data & Access', 'AVA observing summary, data format, download policy and citation.');
?>
<div class="container-xxl ava-page-head">
  <p class="ava-eyebrow">Data &amp; Access</p>
  <h1>Observing summary</h1>
  <p class="ava-lead">LCO imaging and FLOYDS spectroscopy for every AVA target, straight from the archive database:
    <?= number_format($s['images']) ?> photometric frames and <?= number_format($s['spectra']) ?> spectral epochs.</p>
</div>

<div class="container-xxl pb-5">
  <div class="ava-table-wrap">
    <table class="table table-hover ava-table" id="obs">
      <thead>
        <tr>
          <th scope="col" data-sort="text">AGN</th>
          <th scope="col" data-sort="text">Status</th>
          <th scope="col" class="num" data-sort="num">z</th>
          <th scope="col" class="num" data-sort="num">Phot. frames</th>
          <th scope="col" class="num" data-sort="num">Visits</th>
          <th scope="col" class="num" data-sort="num">Cadence (d)</th>
          <th scope="col" data-sort="text">Imaging span</th>
          <th scope="col" class="num" data-sort="num">Spectral epochs</th>
          <th scope="col" data-sort="text">Spectra span</th>
        </tr>
      </thead>
      <tbody>
        <?php foreach ($targets as $t): $st = ava_status($t); ?>
          <tr>
            <th scope="row"><a href="target.php?id=<?= (int) $t['id'] ?>"><?= h($t['name']) ?></a></th>
            <td><span class="ava-badge static ava-badge--<?= $st['key'] ?>"><?= $st['label'] ?></span></td>
            <td class="num"><?= fmt_num($t['redshift'], 4) ?></td>
            <td class="num"><?= fmt_int($t['db_lco_images']) ?></td>
            <td class="num"><?= fmt_int($t['db_lco_visits']) ?></td>
            <td class="num"><?= fmt_num($t['db_lco_cadence'], 2) ?></td>
            <td data-v="<?= h($t['db_lco_start']) ?>"><?= $t['db_lco_start'] ? h(substr($t['db_lco_start'], 0, 7) . ' → ' . substr((string) $t['db_lco_end'], 0, 7)) : '—' ?></td>
            <td class="num"><?= fmt_int($t['db_floyds_epochs']) ?></td>
            <td data-v="<?= h($t['db_floyds_start']) ?>"><?= $t['db_floyds_start'] ? h(substr($t['db_floyds_start'], 0, 7) . ' → ' . substr((string) $t['db_floyds_end'], 0, 7)) : '—' ?></td>
          </tr>
        <?php endforeach; ?>
      </tbody>
    </table>
  </div>
</div>

<section class="ava-section ava-section--alt" id="access">
  <div class="container-xxl">
    <div class="row g-5">
      <div class="col-lg-6 ava-prose">
        <p class="ava-eyebrow">Download policy</p>
        <h2>Access to data products</h2>
        <p>Raw LCO frames are public through the <a href="https://archive.lco.global/">LCO Science Archive</a> once their
          proprietary period ends. Reduced AVA products — calibrated photometry, merged light curves and spectra — are
          currently available to members of the LCO Key Projects that obtained them, and will be released with the AVA data paper.</p>
        <p>Released products are distributed under the
          <a rel="license" href="https://creativecommons.org/licenses/by-sa/4.0/">Creative Commons Attribution-ShareAlike 4.0</a> licence.</p>
        <div class="ava-callout ava-callout--info mt-3">
          Key Project members and collaborators can request access using the form on this page.
        </div>
      </div>

      <div class="col-lg-6 ava-prose" id="format">
        <p class="ava-eyebrow">File format</p>
        <h2>Light-curve files</h2>
        <p>Photometry is delivered as one CSV file per AGN, with columns:</p>
        <ol>
          <li><strong>Object</strong> — AGN name</li>
          <li><strong>Filter</strong> — filter code (below)</li>
          <li><strong>MJD</strong> — Modified Julian Date (days)</li>
          <li><strong>Flux</strong>, <strong>Error</strong> — mJy</li>
          <li><strong>Tel</strong> — LCO telescope code, used for intercalibration</li>
          <li><strong>Site</strong> — LCO site code</li>
        </ol>
        <ul class="ava-filters mb-3">
          <?php foreach (AVA_LCO_FILTERS as $f): if (!isset($fdict[$f])) { continue; } ?>
            <li style="--c: var(<?= ava_filter_var($f) ?>)" title="<?= (int) $fdict[$f]['wave'] ?> Å"><?= h($f) ?> · <?= (int) $fdict[$f]['wave'] ?> Å</li>
          <?php endforeach; ?>
        </ul>
        <p>Small flux offsets (up to ~5%) between telescopes in the network mean we recommend intercalibrating each band with
          <a href="https://github.com/FergusDonnan/PyROA">PyROA</a> (Donnan et al. 2023) before measuring lags.</p>
      </div>
    </div>
  </div>
</section>

<section class="ava-section" id="cite">
  <div class="container-xxl">
    <div class="row g-5">
      <div class="col-lg-6 ava-prose">
        <p class="ava-eyebrow">How to cite</p>
        <h2>Acknowledging AVA</h2>
        <p>If your work uses AVA data, please cite the paper listed on each target's page, and acknowledge the archive:</p>
        <div class="ava-cite">AVA — AGN Variability Archive, Hernández Santisteban 2026, in prep.</div>
        <p class="mt-3 small text-secondary">See <a href="publications.php">Publications</a> for results from the Key Projects.</p>
      </div>

      <div class="col-lg-6" id="contact">
        <p class="ava-eyebrow">Contact</p>
        <h2>Request data or ask a question</h2>
        <?php if ($sent): ?>
          <div class="ava-callout ava-callout--info">Thank you — your message has been sent.</div>
        <?php else: ?>
          <?php if (isset($err['form'])): ?><div class="ava-callout mb-3"><?= h($err['form']) ?></div><?php endif; ?>
          <form method="post" action="data.php#contact" novalidate>
            <div class="mb-3">
              <label class="form-label" for="c-name">Name</label>
              <input class="form-control<?= isset($err['name']) ? ' is-invalid' : '' ?>" id="c-name" name="name" required maxlength="120"
                     value="<?= h($_POST['name'] ?? '') ?>" autocomplete="name">
              <?php if (isset($err['name'])): ?><div class="invalid-feedback"><?= h($err['name']) ?></div><?php endif; ?>
            </div>
            <div class="mb-3">
              <label class="form-label" for="c-email">Email</label>
              <input class="form-control<?= isset($err['email']) ? ' is-invalid' : '' ?>" id="c-email" name="email" type="email" required
                     value="<?= h($_POST['email'] ?? '') ?>" autocomplete="email">
              <?php if (isset($err['email'])): ?><div class="invalid-feedback"><?= h($err['email']) ?></div><?php endif; ?>
            </div>
            <div class="mb-3">
              <label class="form-label" for="c-msg">Message</label>
              <textarea class="form-control<?= isset($err['message']) ? ' is-invalid' : '' ?>" id="c-msg" name="message" rows="5" required maxlength="5000"><?= h($_POST['message'] ?? '') ?></textarea>
              <?php if (isset($err['message'])): ?><div class="invalid-feedback"><?= h($err['message']) ?></div><?php endif; ?>
            </div>
            <div class="visually-hidden" aria-hidden="true">
              <label for="c-web">Leave blank</label><input id="c-web" name="website" tabindex="-1" autocomplete="off">
            </div>
            <button class="btn btn-ava btn-ava-gold" type="submit">Send message</button>
          </form>
        <?php endif; ?>
      </div>
    </div>
  </div>
</section>

<?php ava_page_end(['assets/js/sort-table.js']); ?>
