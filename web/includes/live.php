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
    if ($y === 2017 && $m >= 2 || $y === 2018 && $m === 1) {
        return '2017AB';
    }
    if ($m === 1) {
        return ($y - 1) . 'B';
    }
    return $y . ($m <= 7 ? 'A' : 'B');
}

/** Next LCO semester; 2017 was one long semester, 2017AB (2016B -> 2017AB -> 2018A). */
function ava_next_semester(string $s): string
{
    if ($s === '2016B') {
        return '2017AB';
    }
    if ($s === '2017AB') {
        return '2018A';
    }
    $y = (int) substr($s, 0, 4);
    return $s[4] === 'A' ? "{$y}B" : ($y + 1) . 'A';
}

/**
 * project start => its semesters up to (and including) the current one. A new semester appears on its own when it
 * starts (no edit needed); later ones stay hidden until then.
 */
function ava_project_semesters(?int $ts = null): array
{
    $now = ava_current_semester($ts);
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
