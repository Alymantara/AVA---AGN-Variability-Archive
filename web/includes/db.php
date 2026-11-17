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

/**
 * SQL condition selecting the AVA AGN targets shown and counted on the site (aliases: a = agn,
 * l = agn_lco): not in AVA_EXCLUDED, not a non-AGN type, and with LCO frames or FLOYDS spectra.
 * Values come from fixed config lists and are quoted.
 */
function ava_target_filter_sql(): string
{
    $q = fn(array $v) => implode(', ', array_map(fn($d) => ava_db()->quote($d), $v ?: ['']));
    return "COALESCE(a.data_id, '') NOT IN (" . $q(AVA_EXCLUDED) . ")"
        . " AND COALESCE(a.AGN_type, '') NOT IN (" . $q(AVA_NON_AGN_TYPES) . ")"
        . " AND (COALESCE(l.db_lco_images, 0) > 0 OR COALESCE(l.db_floyds_epochs, 0) > 0)";
}

/** Headline numbers for the stats strip. */
function ava_stats(): array
{
    static $s = null;
    if ($s !== null) {
        return $s;
    }
    $db = ava_db();
    $agn = (int) $db->query('SELECT COUNT(*) FROM agn a LEFT JOIN agn_lco l ON l.db_ava_id = a.id WHERE ' . ava_target_filter_sql())->fetchColumn();
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
            WHERE ' . ava_target_filter_sql() . '
            ORDER BY a.name COLLATE NOCASE';
    return ava_db()->query($sql)->fetchAll();
}

function ava_target(int $id): ?array
{
    $st = ava_db()->prepare('SELECT ' . AVA_TARGET_COLUMNS . '
            FROM agn a LEFT JOIN agn_lco l ON l.db_ava_id = a.id WHERE a.id = ? AND ' . ava_target_filter_sql());
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

/** Observing status from agn.ava (2 = LCO data in the last 30 days, kept current by ava.database.activity). */
function ava_status(array $t): array
{
    return match ((int) ($t['ava'] ?? -1)) {
        2 => ['key' => 'active', 'label' => 'Active'],
        1 => ['key' => 'archived', 'label' => 'Archived'],
        0 => ['key' => 'pending', 'label' => 'To be processed'],
        default => ['key' => 'tba', 'label' => 'tba'],
    };
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

/** True if the (published) database has this table — newer pipeline tables may be missing. */
function ava_has_table(string $name): bool
{
    static $cache = [];
    if (!isset($cache[$name])) {
        $st = ava_db()->prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?");
        $st->execute([$name]);
        $cache[$name] = (bool) $st->fetchColumn();
    }
    return $cache[$name];
}

/**
 * Spectroscopic line variability (ava.spectroscopy.products → line_variability),
 * keyed by quantity ("flux", "cont5100") for one target and line.
 */
function ava_line_variability(string $dataId, string $line = 'Hbeta_broad'): array
{
    if (!ava_has_table('line_variability')) {
        return [];
    }
    $st = ava_db()->prepare('SELECT * FROM line_variability WHERE data_id = ? AND line = ?');
    $st->execute([$dataId, $line]);
    $out = [];
    foreach ($st as $r) {
        $out[$r['quantity']] = $r;
    }
    return $out;
}

/** data_id => Hβ broad-line flux variability row, for every target that has one. */
function ava_hbeta_all(): array
{
    if (!ava_has_table('line_variability')) {
        return [];
    }
    $out = [];
    foreach (ava_db()->query("SELECT * FROM line_variability WHERE line='Hbeta_broad' AND quantity='flux'") as $r) {
        $out[$r['data_id']] = $r;
    }
    return $out;
}

/** Per-band F_var of the merged light curve (ava.photometry.variability), keyed by band. */
function ava_band_variability(string $dataId): array
{
    if (!ava_has_table('photometry_variability')) {
        return [];
    }
    $st = ava_db()->prepare('SELECT * FROM photometry_variability WHERE data_id = ?');
    $st->execute([$dataId]);
    $out = [];
    foreach ($st as $r) {
        $out[$r['filter']] = $r;
    }
    return $out;
}

/** Derived properties (ava.database.derived → agn_derived): k_bol, L_bol, Eddington ratio, disc lags. */
function ava_derived(string $dataId): ?array
{
    if (!ava_has_table('agn_derived')) {
        return null;
    }
    $st = ava_db()->prepare('SELECT * FROM agn_derived WHERE data_id = ?');
    $st->execute([$dataId]);
    return $st->fetch() ?: null;
}

/** Literature properties (ava.database.literature → agn_literature): Hβ lag, mass error, type, with citations. */
function ava_literature(string $dataId): ?array
{
    if (!ava_has_table('agn_literature')) {
        return null;
    }
    $st = ava_db()->prepare('SELECT * FROM agn_literature WHERE data_id = ?');
    $st->execute([$dataId]);
    return $st->fetch() ?: null;
}

/** log L_bol for a target: agn_derived (k_bol × L5100, follows the curated mass/L5100), else the curated agn.logl. */
function ava_log_lbol(array $t, ?array $derived): ?float
{
    $l = $derived['log_lbol'] ?? null;
    if (!is_numeric($l)) {
        $l = $t['logl'] ?? null;
    }
    return is_numeric($l) && (float) $l > 38 ? (float) $l : null;
}

/** data_id => agn_derived row, for every AGN (empty if the table is not published yet). */
function ava_derived_all(): array
{
    if (!ava_has_table('agn_derived')) {
        return [];
    }
    $out = [];
    foreach (ava_db()->query('SELECT * FROM agn_derived') as $r) {
        $out[$r['data_id']] = $r;
    }
    return $out;
}


/** Legacy percentage text ("10.215%", "0.0") as "10.2%"; "—" when missing or zero. */
function fmt_pct($v): string
{
    $x = is_string($v) ? rtrim(trim($v), '%') : $v;
    if (!is_numeric($x) || (float) $x == 0.0) {
        return '—';
    }
    return number_format((float) $x, 1) . '%';
}
