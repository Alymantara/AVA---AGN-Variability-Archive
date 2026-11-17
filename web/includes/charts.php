<?php
/**
 * Server-rendered SVG charts built from the published database (no JS library).
 */

declare(strict_types=1);

require_once __DIR__ . '/db.php';

/** log10 of the Eddington luminosity per solar mass: L_Edd = 1.26e38 (M/Msun) erg/s. */
const AVA_LOG_LEDD_PER_MSUN = 38.1004;

/**
 * Black-hole mass vs bolometric luminosity of every AGN with both values, with lines of
 * constant Eddington ratio (1, 0.1, 0.01). Filled dots: observed in the last 30 days; rings: not currently observed.
 * Each dot links to its target page and carries data-* for the hover tooltip.
 */
function ava_mass_luminosity_svg(array $targets): array
{
    $pts = [];
    $derived = ava_derived_all();           // L_bol = k_bol(Netzer) × L5100 where L5100 is known, else agn.logl
    $nAll = count($targets);
    $nActiveAll = count(array_filter($targets, fn($t) => ava_status($t)['key'] === 'active'));
    foreach ($targets as $t) {
        $m = $t['logm'] ?? null;
        $l = ava_log_lbol($t, $derived[$t['data_id']] ?? null);
        if (is_numeric($m) && is_numeric($l) && (float) $m > 3 && (float) $l > 38) {
            $pts[] = ['m' => (float) $m, 'l' => (float) $l, 'name' => (string) $t['name'], 'id' => (int) $t['id'],
                'active' => ava_status($t)['key'] === 'active', 'label' => ava_status($t)['label']];
        }
    }
    if (!$pts) {
        return ['svg' => '', 'n' => 0, 'n_all' => $nAll, 'n_active' => 0, 'n_active_all' => $nActiveAll];
    }
    $ms = array_column($pts, 'm');
    $ls = array_column($pts, 'l');
    $x0 = floor(min($ms) - 0.3);
    $x1 = ceil(max($ms) + 0.3);
    $y0 = floor(min($ls) - 0.4);
    $y1 = ceil(max($ls) + 0.4);

    $W = 520; $H = 430; $ml = 58; $mr = 12; $mt = 12; $mb = 50;
    $pw = $W - $ml - $mr; $ph = $H - $mt - $mb;
    $X = fn(float $v) => $ml + ($v - $x0) / ($x1 - $x0) * $pw;
    $Y = fn(float $v) => $mt + (1 - ($v - $y0) / ($y1 - $y0)) * $ph;
    $f = fn(float $v) => number_format($v, 1, '.', '');

    $o = [];
    $o[] = "<svg class=\"ava-chart\" viewBox=\"0 0 $W $H\" role=\"img\" aria-labelledby=\"mlTitle mlDesc\" xmlns=\"http://www.w3.org/2000/svg\">";
    $o[] = '<title id="mlTitle">Black-hole mass versus bolometric luminosity of the AVA sample</title>';
    $o[] = '<desc id="mlDesc">' . count($pts) . ' AGN, with lines of constant Eddington ratio 1, 0.1 and 0.01.</desc>';
    $o[] = "<defs><clipPath id=\"mlClip\"><rect x=\"$ml\" y=\"$mt\" width=\"$pw\" height=\"$ph\"/></clipPath></defs>";

    // Grid + ticks
    $o[] = '<g class="grid">';
    for ($v = $x0; $v <= $x1 + 1e-9; $v += 1) {
        $o[] = '<line x1="' . $f($X($v)) . "\" x2=\"" . $f($X($v)) . "\" y1=\"$mt\" y2=\"" . ($mt + $ph) . '"/>';
    }
    for ($v = $y0; $v <= $y1 + 1e-9; $v += 1) {
        $o[] = "<line x1=\"$ml\" x2=\"" . ($ml + $pw) . '" y1="' . $f($Y($v)) . '" y2="' . $f($Y($v)) . '"/>';
    }
    $o[] = '</g><g class="tick">';
    for ($v = $x0; $v <= $x1 + 1e-9; $v += 1) {
        $o[] = '<text x="' . $f($X($v)) . '" y="' . ($mt + $ph + 20) . '" text-anchor="middle">' . (int) $v . '</text>';
    }
    for ($v = $y0; $v <= $y1 + 1e-9; $v += 1) {
        $o[] = '<text x="' . ($ml - 10) . '" y="' . $f($Y($v) + 4) . '" text-anchor="end">' . (int) $v . '</text>';
    }
    $o[] = '</g>';
    $o[] = "<rect class=\"frame\" x=\"$ml\" y=\"$mt\" width=\"$pw\" height=\"$ph\"/>";
    $o[] = '<text class="axis-label" x="' . ($ml + $pw / 2) . '" y="' . ($H - 10) . '" text-anchor="middle">log M<tspan baseline-shift="sub" font-size="10">BH</tspan> / M<tspan baseline-shift="sub" font-size="10">☉</tspan></text>';
    $o[] = '<text class="axis-label" transform="translate(16 ' . ($mt + $ph / 2) . ') rotate(-90)" text-anchor="middle">log L<tspan baseline-shift="sub" font-size="10">Bol</tspan> / erg s<tspan baseline-shift="super" font-size="10">−1</tspan></text>';

    // Lines of constant Eddington ratio, labelled along the line near the left edge.
    $o[] = '<g class="edd" clip-path="url(#mlClip)">';
    $labels = [];
    foreach ([[0, '1', 'solid'], [-1, '0.1', 'dash'], [-2, '0.01', 'dashdot']] as [$lr, $txt, $style]) {
        $c = AVA_LOG_LEDD_PER_MSUN + $lr;                  // log L = log M + c
        $o[] = '<line class="' . $style . '" x1="' . $f($X($x0)) . '" y1="' . $f($Y($x0 + $c)) . '" x2="' . $f($X($x1)) . '" y2="' . $f($Y($x1 + $c)) . '"/>';
        // label where the line is inside the box, ~6% from its left visible end
        $xs = max($x0, $y0 - $c) + 0.06 * ($x1 - $x0);
        if ($xs + $c > $y1 - 0.2 || $xs > $x1 - 1) {
            continue;
        }
        $ang = rad2deg(atan2($Y($xs + 1 + $c) - $Y($xs + $c), $X($xs + 1) - $X($xs)));
        $labels[] = '<text transform="translate(' . $f($X($xs)) . ' ' . $f($Y($xs + $c) - 6) . ') rotate(' . $f($ang) . ')">L/L<tspan baseline-shift="sub" font-size="9">Edd</tspan> = ' . $txt . '</text>';
    }
    $o[] = '</g><g class="edd-label">' . implode('', $labels) . '</g>';

    // Points: archive first, active on top.
    usort($pts, fn($a, $b) => $a['active'] <=> $b['active']);
    $o[] = '<g class="pts">';
    foreach ($pts as $p) {
        $edd = $p['l'] - $p['m'] - AVA_LOG_LEDD_PER_MSUN;
        $tip = sprintf('%s — log M %.2f, log L %.2f, L/L_Edd %.2g', $p['name'], $p['m'], $p['l'], 10 ** $edd);
        $o[] = '<a href="target.php?id=' . $p['id'] . '" class="pt ' . ($p['active'] ? 'active' : 'archive') . '"'
            . ' data-name="' . h($p['name']) . '" data-m="' . number_format($p['m'], 2) . '" data-l="' . number_format($p['l'], 2) . '"'
            . ' data-edd="' . h(sprintf('%.2g', 10 ** $edd)) . '" data-status="' . h($p['label']) . '">'
            . '<title>' . h($tip) . '</title>'
            . '<circle class="hit" cx="' . $f($X($p['m'])) . '" cy="' . $f($Y($p['l'])) . '" r="11"/>'
            . '<circle class="dot" cx="' . $f($X($p['m'])) . '" cy="' . $f($Y($p['l'])) . '" r="5.5"/></a>';
    }
    $o[] = '</g></svg>';
    return ['svg' => implode('', $o), 'n' => count($pts), 'n_all' => $nAll, 'n_active_all' => $nActiveAll,
        'n_active' => count(array_filter($pts, fn($p) => $p['active']))];
}

/** Published filter summary (data/filters/filters.json), or [] if not published yet. */
function ava_filters_published(): array
{
    $f = AVA_DATA_DIR . '/filters/filters.json';
    if (!is_file($f)) {
        return [];
    }
    $d = json_decode((string) file_get_contents($f), true);
    if (!is_array($d['filters'] ?? null)) {
        return [];
    }
    // wavelength order
    uasort($d['filters'], fn($a, $b) => $a['pivot_A'] <=> $b['pivot_A']);
    return $d['filters'];
}

/** Transmission curves of the LCO filters, coloured from filter_dict.txt (--ava-f-<band>). */
function ava_transmission_svg(array $filters): string
{
    if (!$filters) {
        return '';
    }
    $W = 720; $H = 300; $ml = 50; $mr = 14; $mt = 26; $mb = 44;
    $pw = $W - $ml - $mr; $ph = $H - $mt - $mb;
    $wmin = 3000.0; $wmax = 10500.0;
    foreach ($filters as $f) {
        $wmin = min($wmin, $f['curve'][0][0]);
        $wmax = max($wmax, end($f['curve'])[0]);
    }
    $wmin = floor($wmin / 500) * 500; $wmax = ceil($wmax / 500) * 500;
    $X = fn(float $w) => $ml + ($w - $wmin) / ($wmax - $wmin) * $pw;
    $Y = fn(float $t) => $mt + (1 - $t) * $ph;
    $n = fn(float $v) => number_format($v, 1, '.', '');

    $o = ["<svg class=\"ava-chart ava-trans\" viewBox=\"0 0 $W $H\" role=\"img\" aria-labelledby=\"trTitle\" xmlns=\"http://www.w3.org/2000/svg\">",
        '<title id="trTitle">Transmission curves of the LCO filters (filter, Sinistro CCD response and atmosphere at airmass 1)</title>',
        '<g class="grid">'];
    for ($w = $wmin; $w <= $wmax; $w += 1000) {
        $o[] = '<line x1="' . $n($X($w)) . '" x2="' . $n($X($w)) . "\" y1=\"$mt\" y2=\"" . ($mt + $ph) . '"/>';
    }
    foreach ([0, .2, .4, .6, .8, 1] as $t) {
        $o[] = "<line x1=\"$ml\" x2=\"" . ($ml + $pw) . '" y1="' . $n($Y($t)) . '" y2="' . $n($Y($t)) . '"/>';
    }
    $o[] = '</g><g class="tick">';
    for ($w = $wmin; $w <= $wmax; $w += 1000) {
        $o[] = '<text x="' . $n($X($w)) . '" y="' . ($mt + $ph + 18) . '" text-anchor="middle">' . number_format($w) . '</text>';
    }
    foreach ([0, .2, .4, .6, .8, 1] as $t) {
        $o[] = '<text x="' . ($ml - 8) . '" y="' . $n($Y($t) + 4) . '" text-anchor="end">' . number_format($t, 1) . '</text>';
    }
    $o[] = '</g>';
    $o[] = '<text class="axis-label" x="' . ($ml + $pw / 2) . '" y="' . ($H - 6) . '" text-anchor="middle">Wavelength (Å)</text>';
    $o[] = '<text class="axis-label" transform="translate(14 ' . ($mt + $ph / 2) . ') rotate(-90)" text-anchor="middle">Transmission</text>';
    foreach ($filters as $band => $f) {
        $pts = array_map(fn($p) => $n($X((float) $p[0])) . ',' . $n($Y((float) $p[1])), $f['curve']);
        $c = 'var(' . ava_filter_var((string) $band) . ')';
        $first = $f['curve'][0][0]; $last = end($f['curve'])[0];
        $o[] = '<g class="band" style="--c:' . $c . '"><title>' . h((string) $band) . ': pivot ' . number_format($f['pivot_A']) . ' Å, FWHM '
            . number_format($f['fwhm_A']) . ' Å, peak ' . number_format(100 * $f['peak']) . ' %</title>'
            . '<polygon class="fill" points="' . $n($X($first)) . ',' . $n($Y(0)) . ' ' . implode(' ', $pts) . ' ' . $n($X($last)) . ',' . $n($Y(0)) . '"/>'
            . '<polyline class="line" points="' . implode(' ', $pts) . '"/>'
            . '<text x="' . $n($X($f['pivot_A'])) . '" y="' . $n($Y($f['peak']) - 7) . '" text-anchor="middle">' . h((string) $band) . '</text></g>';
    }
    $o[] = '</svg>';
    return implode('', $o);
}
