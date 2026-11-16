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
    'last6' => ['_last6', 'LCO last 60 d'],
    'merged' => ['_merged', 'LCO merged'],
    'merged_pytics' => ['_merged_pytics', 'LCO merged (PyTICS)'],
    'merged_last6' => ['_merged_last6', 'LCO merged, last 60 d'],
    'swift' => ['_swift', 'Swift'],
    'zoom' => ['_zoom', 'Image'],
    'stan' => ['_stan', 'Variability plot'],
    'spec_avg' => ['_spec_avg', 'Spectroscopy'],
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
