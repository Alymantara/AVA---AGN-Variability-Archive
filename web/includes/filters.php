<?php
/**
 * Filter colours, read from data/reference/filter_dict.txt (never hard-coded).
 * Emitted once per page as CSS custom properties: --ava-f-<filter>.
 */

declare(strict_types=1);

require_once __DIR__ . '/config.php';

/** @return array<string, array{wave: float, color: string}> keyed by filter name */
function ava_filter_dict(): array
{
    static $dict = null;
    if ($dict !== null) {
        return $dict;
    }
    $dict = [];
    if (!is_readable(AVA_FILTER_DICT) || !($fh = fopen(AVA_FILTER_DICT, 'r'))) {
        return $dict;
    }
    $head = fgetcsv($fh, null, ',', '"', '');
    $iF = array_search('Filter', $head, true);
    $iW = array_search('wave', $head, true);
    $iC = array_search('color', $head, true);
    while (($r = fgetcsv($fh, null, ',', '"', '')) !== false) {
        if (!isset($r[$iF], $r[$iC])) {
            continue;
        }
        $dict[$r[$iF]] = ['wave' => (float) $r[$iW], 'color' => ava_css_color($r[$iC])];
    }
    fclose($fh);
    return $dict;
}

/** matplotlib single-letter colours -> CSS; named and hex colours pass through. */
function ava_css_color(string $c): string
{
    $c = trim($c);
    $mpl = ['k' => 'black', 'w' => 'white', 'r' => 'red', 'g' => 'green', 'b' => 'blue',
            'c' => 'cyan', 'm' => 'magenta', 'y' => 'yellow'];
    if (isset($mpl[$c])) {
        return $mpl[$c];
    }
    return preg_match('/^(#[0-9A-Fa-f]{3,8}|[A-Za-z]+)$/', $c) ? $c : 'gray';
}

/** CSS variable name for a filter (case kept: B and b are distinct). */
function ava_filter_var(string $f): string
{
    return '--ava-f-' . preg_replace('/[^A-Za-z0-9]/', '_', $f);
}

function ava_filter_css(): string
{
    $lines = [];
    foreach (ava_filter_dict() as $name => $d) {
        $lines[] = ava_filter_var($name) . ':' . $d['color'] . ';';
    }
    return ':root{' . implode('', $lines) . '}';
}
