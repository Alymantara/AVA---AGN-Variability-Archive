<?php
/**
 * Pipeline figures published into AVA_DATA_DIR/plots/<data_id>/ by tools/publish_web.py.
 * File names follow ava/pipeline/tasks/webplot.py: lco_latest_<data_id><suffix>.png
 */

declare(strict_types=1);

require_once __DIR__ . '/config.php';

/** kind => [file suffix, label] */
const AVA_PLOT_KINDS = [
    'lco' => ['', 'LCO'],
    'season' => ['_season', 'LCO last season'],
    'last6' => ['_last6', 'LCO last 60 d'],
    'merged' => ['_merged', 'LCO merged'],
    'merged_season' => ['_merged_season', 'LCO merged, last season'],
    'merged_pytics' => ['_merged_pytics', 'LCO merged (PyTICS)'],
    'merged_last6' => ['_merged_last6', 'LCO merged, last 60 d'],
    'swift' => ['_swift', 'Swift'],
    'zoom' => ['_zoom', 'Image'],
    'stan' => ['_stan', 'Variability plot'],
    'spec' => ['_spec', 'Latest spectrum'],
    'hbeta' => ['_hbeta', 'H&beta; light curve'],
    'hbeta_fit' => ['_hbeta_fit', 'H&beta; fit'],
    'spec_avg' => ['_spec_avg', 'Mean &amp; RMS spectrum'],
];

/** Sky diagnostics: site filter label => LCO filter code used in the file name. */
const AVA_SKY_FILTERS = ['u' => 'up', 'B' => 'B', 'g' => 'gp', 'V' => 'V', 'r' => 'rp', 'i' => 'ip', 'z' => 'zs', 'Y' => 'Y'];

function ava_plot_file(string $dataId, string $kind): ?string
{
    if (isset(AVA_PLOT_KINDS[$kind])) {
        $suffix = AVA_PLOT_KINDS[$kind][0];
    } elseif (str_starts_with($kind, 'sky_') && isset(AVA_SKY_FILTERS[substr($kind, 4)])) {
        $suffix = '_' . AVA_SKY_FILTERS[substr($kind, 4)] . '_sky';
    } else {
        return null;
    }
    return "lco_latest_{$dataId}{$suffix}.png";
}

/** Public URL of a published plot (cache-busted), or null if it isn't there. */
function ava_plot_url(array $t, string $kind): ?string
{
    $id = (string) ($t['data_id'] ?? '');
    $file = ava_plot_file($id, $kind);
    if ($file === null || !preg_match('/^[A-Za-z0-9_.+\-]+$/', $id)) {
        return null;
    }
    $path = AVA_DATA_DIR . "/plots/$id/$file";
    if (!is_file($path)) {
        return null;
    }
    return AVA_DATA_URL . '/plots/' . rawurlencode($id) . '/' . rawurlencode($file) . '?v=' . filemtime($path);
}

/** Time of the most recent published plot for a target (for "updated" stamps). */
function ava_plots_updated(array $t): ?int
{
    $files = glob(AVA_DATA_DIR . '/plots/' . basename((string) $t['data_id']) . '/*.png') ?: [];
    return $files ? max(array_map('filemtime', $files)) : null;
}

/** Per-target downloads published by ava.web.publish (data/downloads/<data_id>/). */
const AVA_DOWNLOADS = [
    'phot'     => ['Photometry', 'Merged light curve (CSV)', '%s_LCO_merged_lightcurve.csv'],
    'spec'     => ['Spectra', '1-d FLOYDS spectra (FITS, zip)', '%s_FLOYDS_1d.zip'],
    'prepspec' => ['Spectra', 'PrepSpec input (zip)', '%s_FLOYDS_prepspec.zip'],
];

/** Downloads switch (web.downloads in the AVA config, published to data/site.json). Off when unknown. */
function ava_downloads_enabled(): bool
{
    static $on = null;
    if ($on === null) {
        $j = @file_get_contents(AVA_DATA_DIR . '/site.json');
        $on = (bool) (($j !== false ? json_decode($j, true) : null)['downloads'] ?? false);
    }
    return $on;
}

/**
 * Downloads that staging copies (AVA_STAGING) do not carry: they are large and served only by the main site.
 * tools/export_web_bundle.sh leaves the matching files out of a staging bundle.
 */
const AVA_STAGING_MAIN_ONLY = ['spec'];

/** [key => [group, label, url|null, bytes|null, note]] for one target; url null = not available (note says why). */
function ava_downloads(string $dataId): array
{
    $out = [];
    foreach (AVA_DOWNLOADS as $k => [$group, $label, $pat]) {
        $name = sprintf($pat, $dataId);
        $f = AVA_DATA_DIR . '/downloads/' . $dataId . '/' . $name;
        $mainOnly = AVA_STAGING !== '' && in_array($k, AVA_STAGING_MAIN_ONLY, true);
        $ok = !$mainOnly && $dataId !== '' && !str_contains($dataId, '/') && is_file($f);
        $out[$k] = [$group, $label, $ok ? ava_data_url("downloads/$dataId/$name") : null,
            $ok ? filesize($f) : null, $mainOnly ? 'on the main AVA site only' : 'not available'];
    }
    return $out;
}

function fmt_bytes(?int $b): string
{
    if ($b === null) return '';
    foreach (['B', 'kB', 'MB', 'GB'] as $i => $u) {
        if ($b < 1024 ** ($i + 1) || $u === 'GB') return ($i ? number_format($b / 1024 ** $i, $b < 10 * 1024 ** $i ? 1 : 0) : $b) . ' ' . $u;
    }
    return '';
}
