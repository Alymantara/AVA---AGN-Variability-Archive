<?php
/**
 * Read-only access to data/ava.db. Every page gets its content from here.
 *
 * The database is opened with SQLITE_OPEN_READONLY, so the site can never
 * write to it. All queries use bound parameters.
 */

declare(strict_types=1);

require_once __DIR__ . '/config.php';

function ava_db(): PDO
{
    static $pdo = null;
    if ($pdo === null) {
        if (!is_readable(AVA_DB_PATH)) {
            throw new RuntimeException('AVA database not found at ' . AVA_DB_PATH);
        }
        $opts = [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        ];
        if (defined('PDO::SQLITE_ATTR_OPEN_FLAGS')) {          // PHP >= 8.1
            $opts[PDO::SQLITE_ATTR_OPEN_FLAGS] = PDO::SQLITE_OPEN_READONLY;
        }
        $pdo = new PDO('sqlite:' . AVA_DB_PATH, null, null, $opts);
        $pdo->exec('PRAGMA query_only = ON');
    }
    return $pdo;
}

/** Headline numbers for the stats strip. */
function ava_stats(): array
{
    static $s = null;
    if ($s !== null) {
        return $s;
    }
    $db = ava_db();
    $agn = (int) $db->query('SELECT COUNT(*) FROM agn')->fetchColumn();
    $row = $db->query('SELECT SUM(db_lco_images) AS images, SUM(db_floyds_epochs) AS spectra,
                              MIN(db_lco_start) AS first FROM agn_lco')->fetch();
    $first = $db->query('SELECT MIN(d) FROM (SELECT MIN(lco_start) AS d FROM agn
                         UNION ALL SELECT MIN(db_lco_start) FROM agn_lco)')->fetchColumn();
    $years = 0;
    if ($first) {
        $years = (int) floor((time() - strtotime((string) $first)) / (365.25 * 86400));
    }
    return $s = [
        'agn' => $agn,
        'images' => (int) $row['images'],
        'spectra' => (int) $row['spectra'],
        'years' => $years,
    ];
}

const AVA_TARGET_COLUMNS = 'a.*, l.*';   // agn_lco columns are all db_-prefixed

/** All targets with their LCO observing summary, ordered by name. */
function ava_targets(): array
{
    $sql = 'SELECT ' . AVA_TARGET_COLUMNS . '
            FROM agn a LEFT JOIN agn_lco l ON l.db_ava_id = a.id
            ORDER BY a.name COLLATE NOCASE';
    return ava_db()->query($sql)->fetchAll();
}

function ava_target(int $id): ?array
{
    $st = ava_db()->prepare('SELECT ' . AVA_TARGET_COLUMNS . '
            FROM agn a LEFT JOIN agn_lco l ON l.db_ava_id = a.id WHERE a.id = ?');
    $st->execute([$id]);
    return $st->fetch() ?: null;
}

/** Distinct LCO proposal IDs across all targets (for the About page). */
function ava_proposals(): array
{
    $ids = [];
    foreach (ava_db()->query('SELECT db_lco_proposals FROM agn_lco') as $r) {
        foreach (explode(';', (string) $r['db_lco_proposals']) as $p) {
            $p = trim($p);
            if ($p !== '') {
                $ids[rtrim($p, 'f')] = true;   // KEY2023B-001f is a follow-up of KEY2023B-001
            }
        }
    }
    $ids = array_keys($ids);
    sort($ids);
    return $ids;
}

/** Observing status from agn.lco_active. */
function ava_status(array $t): array
{
    return ((int) ($t['lco_active'] ?? 0) === 1)
        ? ['key' => 'active', 'label' => 'Active']
        : ['key' => 'archive', 'label' => 'Archive'];
}

/** Processing state from the legacy agn.ava flag. */
function ava_processing(array $t): string
{
    return match ((int) ($t['ava'] ?? -1)) {
        2 => 'Observing — data in the last 30 days',
        1 => 'Processed and archived',
        0 => 'Observed, not yet archived',
        default => 'Not scheduled',
    };
}

/** LCO filters with at least one frame for this target. */
function ava_target_filters(array $t): array
{
    $out = [];
    foreach (AVA_LCO_FILTERS as $f) {
        $n = (int) ($t["db_lco_$f"] ?? 0) ?: (int) ($t["lco_$f"] ?? 0);
        if ($n > 0) {
            $out[$f] = $n;
        }
    }
    return $out;
}

/**
 * Map a target to its poster image stem in assets/agn/ (e.g. "Mrk_817"),
 * matching data_id, name or simbad_name with punctuation and case ignored.
 */
function ava_image_stem(array $t): ?string
{
    static $index = null;
    if ($index === null) {
        $index = [];
        foreach (glob(AVA_ROOT . '/assets/agn/*_600.webp') ?: [] as $f) {
            $stem = substr(basename($f), 0, -strlen('_600.webp'));
            $index[ava_norm($stem)] = $stem;
        }
    }
    foreach (['data_id', 'name', 'simbad_name'] as $k) {
        $key = ava_norm((string) ($t[$k] ?? ''));
        if ($key !== '' && isset($index[$key])) {
            return $index[$key];
        }
    }
    return null;
}

function ava_norm(string $s): string
{
    return strtolower(preg_replace('/[^A-Za-z0-9+\-]/', '', $s));
}
