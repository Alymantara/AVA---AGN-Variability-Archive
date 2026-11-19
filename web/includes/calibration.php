<?php
/**
 * Photometric-calibration page (calibration.php): data loader and server-rendered SVG charts.
 *
 * Reads data/calibration/calibration.json, published by the pipeline's -w step from
 * web.calibration_src (made by tools/abscal_validation/export_web.py). Band colours come from
 * filter_dict.txt (--ava-f-<band>); target colours are the brand accents, assigned in order.
 */

declare(strict_types=1);

require_once __DIR__ . '/config.php';
require_once __DIR__ . '/filters.php';

/** Brand accents for up to four targets (fixed order); more targets are drawn muted with their median. */
const AVA_CAL_TARGET_VARS = ['--ava-cal-gold', '--ava-cal-sky', '--ava-aurora', '--ava-copper'];

function ava_cal_load(): ?array
{
    $f = AVA_DATA_DIR . '/calibration/calibration.json';
    if (!is_file($f)) {
        return null;
    }
    $d = json_decode((string) file_get_contents($f), true);
    return is_array($d) && !empty($d['targets']) ? $d : null;
}

/** mmag with sign, e.g. "+138". */
function ava_mmag(?float $v): string
{
    if ($v === null) {
        return '–';
    }
    $m = (int) round($v * 1000);
    return $m === 0 ? '0' : str_replace('-', '−', sprintf('%+d', $m));
}

function ava_cal_band_label(string $b): string
{
    return in_array($b, ['u', 'g', 'r', 'i'], true) ? $b . '′' : ($b === 'z' ? 'zₛ' : $b);
}

function ava_cal_n(float $v): string
{
    return number_format($v, 1, '.', '');
}

/**
 * One band: LCO passband (solid, filled) vs the reference passband of the Gaia anchors (dashed),
 * normalised to their peaks; shaded where LCO transmits more.
 */
function ava_cal_passband_svg(string $band, array $pb): string
{
    $W = 300; $H = 170; $ml = 10; $mr = 10; $mt = 26; $mb = 30;
    $pw = $W - $ml - $mr; $ph = $H - $mt - $mb;
    $all = array_merge($pb['lco'], $pb['ref']);
    $w0 = min(array_column($all, 0)); $w1 = max(array_column($all, 0));
    $X = fn(float $w) => $ml + ($w - $w0) / ($w1 - $w0) * $pw;
    $Y = fn(float $t) => $mt + (1 - $t) * $ph;
    $pts = fn(array $c) => implode(' ', array_map(fn($p) => ava_cal_n($X($p[0])) . ',' . ava_cal_n($Y($p[1])), $c));
    $c = 'var(' . ava_filter_var($band) . ')';
    $first = $pb['lco'][0][0]; $last = end($pb['lco'])[0];
    $lab = ava_cal_band_label($band);
    $o = ["<svg class=\"ava-chart ava-cal-pb\" viewBox=\"0 0 $W $H\" role=\"img\" aria-label=\"LCO $lab passband against "
        . h($pb['ref_name']) . "\" xmlns=\"http://www.w3.org/2000/svg\" style=\"--c:$c\">"];
    // wavelength ticks every 500 Å
    $o[] = '<g class="grid">';
    $dw = ($w1 - $w0) > 2600 ? 1000 : 500;              // about 3-5 ticks per panel
    $t0 = ceil($w0 / $dw) * $dw;
    for ($w = $t0; $w <= $w1; $w += $dw) {
        $o[] = '<line x1="' . ava_cal_n($X($w)) . '" x2="' . ava_cal_n($X($w)) . "\" y1=\"$mt\" y2=\"" . ($mt + $ph) . '"/>';
    }
    $o[] = '</g><g class="tick">';
    for ($w = $t0; $w <= $w1; $w += $dw) {
        if ($X($w) < $ml + 16 || $X($w) > $ml + $pw - 16) {
            continue;                                        // keep labels inside the panel
        }
        $o[] = '<text x="' . ava_cal_n($X($w)) . '" y="' . ($mt + $ph + 17) . '" text-anchor="middle">' . $w . '</text>';
    }
    $o[] = '</g>';
    $o[] = '<polygon class="fill" points="' . ava_cal_n($X($first)) . ',' . ava_cal_n($Y(0)) . ' ' . $pts($pb['lco']) . ' '
        . ava_cal_n($X($last)) . ',' . ava_cal_n($Y(0)) . '"/>';
    $o[] = '<polyline class="ref" points="' . $pts($pb['ref']) . '"><title>' . h($pb['ref_name']) . ': half power '
        . number_format($pb['ref_half'][0]) . '–' . number_format($pb['ref_half'][1]) . ' Å</title></polyline>';
    $o[] = '<polyline class="lco" points="' . $pts($pb['lco']) . '"><title>LCO ' . h($lab) . ': half power '
        . number_format($pb['lco_half'][0]) . '–' . number_format($pb['lco_half'][1]) . ' Å</title></polyline>';
    $o[] = '<line class="base" x1="' . $ml . '" x2="' . ($ml + $pw) . '" y1="' . ava_cal_n($Y(0)) . '" y2="' . ava_cal_n($Y(0)) . '"/>';
    $o[] = '<text class="title" x="' . $ml . '" y="16">' . h($lab) . ' <tspan class="sub">vs ' . h($pb['ref_name']) . '</tspan></text>';
    $o[] = '</svg>';
    return implode('', $o);
}

/**
 * A target's median FLOYDS spectrum (normalised at 5100 Å rest) with its continuum fit, and below it
 * the LCO (solid) and reference (dashed) passbands, each labelled with the correction in mmag.
 */
function ava_cal_spectrum_svg(array $t, array $spec, array $pbs, array $bands): string
{
    $W = 760; $H = 380; $ml = 52; $mr = 14; $mt = 16; $mb = 44;
    $gap = 14; $hb = 104;                                  // passband strip height (two label rows)
    $pw = $W - $ml - $mr; $hs = $H - $mt - $mb - $gap - $hb;
    $w0 = 3200.0; $w1 = 10200.0;
    $fl = $spec['flux'];
    $sorted = $fl; sort($sorted);
    $ymax = $sorted[(int) floor(0.995 * (count($sorted) - 1))] * 1.12;
    $X = fn(float $w) => $ml + ($w - $w0) / ($w1 - $w0) * $pw;
    $Ys = fn(float $f) => $mt + (1 - min(max($f / $ymax, 0), 1.02)) * $hs;
    $yb0 = $mt + $hs + $gap;
    $Yb = fn(float $t) => $yb0 + (1 - $t) * ($hb - 36) + 36;
    $id = 'cs' . preg_replace('/[^A-Za-z0-9]/', '', $t['data_id']);
    $o = ["<svg class=\"ava-chart ava-cal-spec\" viewBox=\"0 0 $W $H\" role=\"img\" aria-labelledby=\"{$id}t\" xmlns=\"http://www.w3.org/2000/svg\">",
        "<title id=\"{$id}t\">" . h($t['name']) . ': median FLOYDS spectrum with the LCO and reference passbands</title>'];
    // grid + ticks
    $o[] = '<g class="grid">';
    for ($w = 4000; $w <= 10000; $w += 1000) {
        $o[] = '<line x1="' . ava_cal_n($X($w)) . '" x2="' . ava_cal_n($X($w)) . "\" y1=\"$mt\" y2=\"" . ($yb0 + $hb) . '"/>';
    }
    $step = $ymax > 4 ? 1.0 : 0.5;
    for ($v = 0; $v <= $ymax; $v += $step) {
        $o[] = "<line x1=\"$ml\" x2=\"" . ($ml + $pw) . '" y1="' . ava_cal_n($Ys($v)) . '" y2="' . ava_cal_n($Ys($v)) . '"/>';
    }
    $o[] = '</g><g class="tick">';
    for ($w = 4000; $w <= 10000; $w += 1000) {
        $o[] = '<text x="' . ava_cal_n($X($w)) . '" y="' . ($yb0 + $hb + 18) . '" text-anchor="middle">' . number_format($w) . '</text>';
    }
    for ($v = 0; $v <= $ymax; $v += $step) {
        $o[] = '<text x="' . ($ml - 8) . '" y="' . ava_cal_n($Ys($v) + 4) . '" text-anchor="end">' . rtrim(rtrim(number_format($v, 1), '0'), '.') . '</text>';
    }
    $o[] = '</g>';
    $o[] = '<text class="axis-label" x="' . ($ml + $pw / 2) . '" y="' . ($H - 4) . '" text-anchor="middle">Observed wavelength (Å)</text>';
    $o[] = '<text class="axis-label" transform="translate(14 ' . ($mt + $hs / 2) . ') rotate(-90)" text-anchor="middle">F<tspan baseline-shift="sub" font-size="10">λ</tspan> (5100 Å = 1)</text>';
    // spectrum + continuum
    $sp = []; $cp = [];
    $z = (float) $t['z'];
    foreach ($spec['wave'] as $k => $w) {
        if ($w < $w0 || $w > $w1) {
            continue;
        }
        $sp[] = ava_cal_n($X($w)) . ',' . ava_cal_n($Ys($fl[$k]));
        if ($w <= 9200 * (1 + $z)) {                       // continuum only where line-free windows constrain it
            $cp[] = ava_cal_n($X($w)) . ',' . ava_cal_n($Ys($spec['cont'][$k]));
        }
    }
    $o[] = '<polyline class="cont" points="' . implode(' ', $cp) . '"/>';
    $o[] = '<polyline class="spec" points="' . implode(' ', $sp) . '"/>';
    // line labels (rest wavelengths moved to the target's redshift)
    foreach (['Hβ' => 4861, '[O III]' => 5007, 'Hα' => 6563] as $name => $lam) {
        $x = $lam * (1 + $z);
        $k = 0; $best = INF;
        foreach ($spec['wave'] as $i => $w) {
            if (abs($w - $x) < $best) { $best = abs($w - $x); $k = $i; }
        }
        $peak = max(array_slice($fl, max($k - 3, 0), 7));
        $dx = $name === '[O III]' ? 16 : ($name === 'Hβ' ? -14 : 18);
        $o[] = '<text class="line-lab" x="' . ava_cal_n($X($x) + $dx) . '" y="' . ava_cal_n(max($Ys($peak) - 6, $mt + 10)) . '" text-anchor="middle">' . h($name) . '</text>';
    }
    // passband strip
    $o[] = '<line class="sep" x1="' . $ml . '" x2="' . ($ml + $pw) . '" y1="' . ava_cal_n($Yb(0)) . '" y2="' . ava_cal_n($Yb(0)) . '"/>';
    $row = 0;
    foreach ($pbs as $b => $pb) {
        $c = 'var(' . ava_filter_var((string) $b) . ')';
        $p = fn(array $cv) => implode(' ', array_map(fn($q) => ava_cal_n($X($q[0])) . ',' . ava_cal_n($Yb($q[1])), $cv));
        $info = $t['bands'][$b] ?? null;
        $lab = ava_cal_band_label((string) $b);
        $tip = 'LCO ' . $lab . ' (solid) vs ' . $pb['ref_name'] . ' (dashed)';
        if ($info) {
            $tip .= sprintf('; true − AVA %s ± %d mmag; lines %d %% of the LCO band flux',
                ava_mmag($info['dref']), (int) round(1000 * $info['err']), (int) round(100 * $info['linefrac_lco']));
        }
        $o[] = '<g class="band" style="--c:' . $c . '"><title>' . h($tip) . '</title>'
            . '<polyline class="ref" points="' . $p($pb['ref']) . '"/><polyline class="lco" points="' . $p($pb['lco']) . '"/>';
        $xc = ($pb['lco_half'][0] + $pb['lco_half'][1]) / 2;
        $txt = $lab;
        if ($info && in_array($b, $bands, true)) {
            $txt .= ' ' . ava_mmag($info['dref']);
        }
        $o[] = '<text x="' . ava_cal_n($X($xc)) . '" y="' . ava_cal_n($yb0 + 12 + 15 * ($row++ % 2)) . '" text-anchor="middle">' . h($txt) . '</text></g>';
    }
    $o[] = '</svg>';
    return implode('', $o);
}

/**
 * Correction against redshift for one band: each target's spectrum moved from z = 0 to 0.2.
 * Up to four targets are coloured (brand accents, fixed order); with more, all are thin and muted
 * and their median is drawn. data-* carry the curves for the hover crosshair (assets/js/calibration.js).
 */
function ava_cal_zscan_svg(string $band, array $zscan, array $targets): string
{
    $W = 300; $H = 220; $ml = 44; $mr = 10; $mt = 24; $mb = 36;
    $pw = $W - $ml - $mr; $ph = $H - $mt - $mb;
    $zs = $zscan['z'];
    $vals = [];
    foreach ($targets as $t) {
        foreach ($zscan['curves'][$t['data_id']][$band] ?? [] as $v) {
            if ($v !== null) { $vals[] = 1000 * $v; }
        }
    }
    if (!$vals) {
        return '';
    }
    $y0 = floor(min(min($vals), 0) / 50) * 50; $y1 = ceil(max(max($vals), 0) / 50) * 50;
    if ($y1 - $y0 < 100) { $y1 = $y0 + 100; }
    $step = ($y1 - $y0) > 250 ? 100 : 50;
    $X = fn(float $z) => $ml + ($z - $zs[0]) / (end($zs) - $zs[0]) * $pw;
    $Y = fn(float $v) => $mt + (1 - ($v - $y0) / ($y1 - $y0)) * $ph;
    $lab = ava_cal_band_label($band);
    $series = [];
    $o = ["<svg class=\"ava-chart ava-cal-z\" viewBox=\"0 0 $W $H\" role=\"img\" aria-label=\"Correction in $lab against redshift\" xmlns=\"http://www.w3.org/2000/svg\">"];
    $o[] = '<g class="grid">';
    for ($v = $y0; $v <= $y1 + 1e-9; $v += $step) {
        $o[] = "<line x1=\"$ml\" x2=\"" . ($ml + $pw) . '" y1="' . ava_cal_n($Y($v)) . '" y2="' . ava_cal_n($Y($v)) . '"/>';
    }
    foreach ([0.05, 0.1, 0.15] as $z) {
        $o[] = '<line x1="' . ava_cal_n($X($z)) . '" x2="' . ava_cal_n($X($z)) . "\" y1=\"$mt\" y2=\"" . ($mt + $ph) . '"/>';
    }
    $o[] = '</g><g class="tick">';
    for ($v = $y0; $v <= $y1 + 1e-9; $v += $step) {
        $o[] = '<text x="' . ($ml - 6) . '" y="' . ava_cal_n($Y($v) + 4) . '" text-anchor="end">' . ava_mmag($v / 1000) . '</text>';
    }
    foreach ([0, 0.05, 0.1, 0.15, 0.2] as $z) {
        $o[] = '<text x="' . ava_cal_n($X($z)) . '" y="' . ($mt + $ph + 16) . '" text-anchor="middle">' . $z . '</text>';
    }
    $o[] = '</g>';
    $o[] = '<line class="zero" x1="' . $ml . '" x2="' . ($ml + $pw) . '" y1="' . ava_cal_n($Y(0)) . '" y2="' . ava_cal_n($Y(0)) . '"/>';
    $o[] = '<text class="title" x="' . $ml . '" y="15">' . h($lab) . '</text>';
    $o[] = '<text class="axis-label small" x="' . ($ml + $pw / 2) . '" y="' . ($H - 3) . '" text-anchor="middle">redshift</text>';
    $many = count($targets) > count(AVA_CAL_TARGET_VARS);
    foreach (array_values($targets) as $k => $t) {
        $cv = $zscan['curves'][$t['data_id']][$band] ?? [];
        $pts = [];
        foreach ($cv as $i => $v) {
            if ($v !== null) { $pts[] = ava_cal_n($X($zs[$i])) . ',' . ava_cal_n($Y(1000 * $v)); }
        }
        $col = $many ? 'var(--ava-muted)' : 'var(' . AVA_CAL_TARGET_VARS[$k] . ')';
        $o[] = '<polyline class="curve' . ($many ? ' thin' : '') . '" style="--c:' . $col . '" points="' . implode(' ', $pts) . '"/>';
        // the target's own redshift
        $zt = (float) $t['z'];
        if (!$many && $zt <= end($zs)) {
            $i = (int) round(($zt - $zs[0]) / ($zs[1] - $zs[0]));
            $v = $cv[$i] ?? null;
            if ($v !== null) {
                $o[] = '<circle class="here" style="--c:' . $col . '" cx="' . ava_cal_n($X($zt)) . '" cy="' . ava_cal_n($Y(1000 * $v)) . '" r="4.5"/>';
            }
        }
        $series[] = ['name' => $t['name'], 'c' => $col, 'v' => array_map(fn($x) => $x === null ? null : round(1000 * $x), $cv)];
    }
    if ($many) {
        $med = [];
        foreach ($zs as $i => $z) {
            $col = array_values(array_filter(array_map(fn($t) => $zscan['curves'][$t['data_id']][$band][$i] ?? null, $targets), fn($x) => $x !== null));
            sort($col);
            $med[] = $col ? ava_cal_n($X($z)) . ',' . ava_cal_n($Y(1000 * $col[intdiv(count($col), 2)])) : null;
        }
        $o[] = '<polyline class="curve" style="--c:var(--ava-cal-gold)" points="' . implode(' ', array_filter($med)) . '"/>';
    }
    $o[] = '<line class="xhair" x1="0" x2="0" y1="' . $mt . '" y2="' . ($mt + $ph) . '" visibility="hidden"/>';
    $o[] = '<rect class="hit" x="' . $ml . '" y="' . $mt . '" width="' . $pw . '" height="' . $ph . '"/>';
    $o[] = '</svg>';
    $data = h(json_encode(['band' => $lab, 'z' => $zs, 'x0' => $ml, 'pw' => $pw, 'W' => $W, 'series' => $series]));
    return '<div class="ava-cal-zwrap" data-zscan="' . $data . '">' . implode('', $o) . '</div>';
}

/**
 * One band of the test-field stars: Gaia GSPC − AVA per comparison star against GSPC magnitude, with the
 * median per 1-mag bin. Filled points are the stars that set the zero point, open ones were clipped.
 */
function ava_cal_stars_svg(string $band, array $d): string
{
    $mag = $d['mag'] ?? [];
    $res = array_map(fn($v) => 1000 * (float) $v, $d['res'] ?? []);
    $used = $d['used'] ?? [];
    $n = count($mag);
    if ($n < 5) {
        return '';
    }
    $W = 300; $H = 220; $ml = 44; $mr = 10; $mt = 24; $mb = 36;
    $pw = $W - $ml - $mr; $ph = $H - $mt - $mb;
    $lim = 50.0;
    $x0 = floor(min($mag) * 2) / 2 - 0.25; $x1 = ceil(max($mag) * 2) / 2 + 0.25;
    if ($x1 - $x0 < 2) { $x1 = $x0 + 2; }
    $X = fn(float $m) => $ml + ($m - $x0) / ($x1 - $x0) * $pw;
    $Y = fn(float $v) => $mt + (1 - (max(-$lim, min($lim, $v)) + $lim) / (2 * $lim)) * $ph;
    $med = function (array $v): float { sort($v); $k = count($v); return $k % 2 ? $v[intdiv($k, 2)] : 0.5 * ($v[$k / 2 - 1] + $v[$k / 2]); };
    $u = array_values(array_filter($res, fn($v, $i) => !empty($used[$i]), ARRAY_FILTER_USE_BOTH));
    $m0 = $u ? $med($u) : $med($res);
    $sig = 1.4826 * $med(array_map(fn($v) => abs($v - $m0), $u ?: $res));
    $lab = ava_cal_band_label($band);
    $col = 'var(' . ava_filter_var($band) . ', var(--ava-cal-sky))';
    $o = ["<svg class=\"ava-chart ava-cal-z ava-cal-stars\" viewBox=\"0 0 $W $H\" role=\"img\" aria-label=\"Gaia minus AVA for the test-field stars in $lab: median "
        . sprintf('%+.1f', $m0) . ' mmag, scatter ' . sprintf('%.0f', $sig) . " mmag per star\" xmlns=\"http://www.w3.org/2000/svg\">"];
    $o[] = '<g class="grid">';
    foreach ([-50, -25, 0, 25, 50] as $v) {
        $o[] = "<line x1=\"$ml\" x2=\"" . ($ml + $pw) . '" y1="' . ava_cal_n($Y($v)) . '" y2="' . ava_cal_n($Y($v)) . '"/>';
    }
    $o[] = '</g><g class="tick">';
    foreach ([-50, -25, 0, 25, 50] as $v) {
        $o[] = '<text x="' . ($ml - 6) . '" y="' . ava_cal_n($Y($v) + 4) . '" text-anchor="end">' . ($v > 0 ? '+' : ($v < 0 ? '−' : '')) . abs($v) . '</text>';
    }
    for ($m = ceil($x0); $m <= $x1 + 1e-9; $m += 1) {
        $o[] = '<text x="' . ava_cal_n($X($m)) . '" y="' . ($mt + $ph + 16) . '" text-anchor="middle">' . (int) $m . '</text>';
    }
    $o[] = '</g>';
    $o[] = '<line class="zero" x1="' . $ml . '" x2="' . ($ml + $pw) . '" y1="' . ava_cal_n($Y(0)) . '" y2="' . ava_cal_n($Y(0)) . '"/>';
    foreach ($mag as $i => $m) {
        $cls = empty($used[$i]) ? 'pt off' : 'pt';
        $o[] = '<circle class="' . $cls . '" style="--c:' . $col . '" cx="' . ava_cal_n($X((float) $m)) . '" cy="' . ava_cal_n($Y($res[$i])) . '" r="2.6"/>';
    }
    // median per 1-mag bin (≥ 4 used stars)
    $pts = [];
    for ($b = floor($x0); $b < $x1; $b += 1) {
        $v = [];
        foreach ($mag as $i => $m) {
            if (!empty($used[$i]) && $m >= $b && $m < $b + 1) { $v[] = $res[$i]; }
        }
        if (count($v) >= 4) {
            $pts[] = ava_cal_n($X($b + 0.5)) . ',' . ava_cal_n($Y($med($v)));
        }
    }
    if (count($pts) >= 2) {
        $o[] = '<polyline class="curve" style="--c:var(--ava-strong)" points="' . implode(' ', $pts) . '"/>';
    }
    foreach ($pts as $p) {
        [$cx, $cy] = explode(',', $p);
        $o[] = '<circle class="here" style="--c:var(--ava-strong)" cx="' . $cx . '" cy="' . $cy . '" r="3.5"/>';
    }
    $o[] = '<text class="title" x="' . $ml . '" y="15">' . h($lab) . '<tspan class="sub" dx="8">median '
        . sprintf('%+.1f', $m0) . ' · σ ' . sprintf('%.0f', $sig) . ' mmag · ' . count($u) . ' stars</tspan></text>';
    $o[] = '<text class="axis-label small" x="' . ($ml + $pw / 2) . '" y="' . ($H - 3) . '" text-anchor="middle">Gaia GSPC magnitude</text>';
    $o[] = '</svg>';
    return implode('', $o);
}
