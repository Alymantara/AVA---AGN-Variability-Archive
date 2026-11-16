<?php
/** Key Project semesters and LCO usage plots for the Live Updates page. */

declare(strict_types=1);

require_once __DIR__ . '/config.php';

/** Current LCO semester: A = Feb–Jul, B = Aug–Jan (January belongs to the previous year's B). */
function ava_current_semester(?int $ts = null): string
{
    $ts ??= time();
    $y = (int) date('Y', $ts);
    $m = (int) date('n', $ts);
    if ($m === 1) {
        return ($y - 1) . 'B';
    }
    return $y . ($m <= 7 ? 'A' : 'B');
}

function ava_next_semester(string $s): string
{
    $y = (int) substr($s, 0, 4);
    return $s[4] === 'A' ? "{$y}B" : ($y + 1) . 'A';
}

/** project start => semesters up to (and including) the current one. */
function ava_project_semesters(): array
{
    $now = ava_current_semester();
    $out = [];
    foreach (AVA_KEY_PROJECTS as $start => $n) {
        $list = [];
        for ($s = $start, $i = 0; $i < $n && strcmp($s, $now) <= 0; $i++, $s = ava_next_semester($s)) {
            $list[] = $s;
        }
        if ($list) {
            $out[$start] = $list;
        }
    }
    return $out;
}

/** Public URL of a published usage plot, or null. */
function ava_usage_url(string $semester): ?string
{
    $path = AVA_DATA_DIR . "/usage/lco_usage_$semester.png";
    return is_file($path) ? AVA_DATA_URL . "/usage/lco_usage_$semester.png?v=" . filemtime($path) : null;
}
