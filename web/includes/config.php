<?php
/**
 * AVA website configuration.
 *
 * Paths default to the repository layout (web/ next to data/). On a server,
 * override them with environment variables instead of editing this file:
 *   AVA_WEB_DATA     published data folder (default web/data)
 */

declare(strict_types=1);

define('AVA_ROOT', dirname(__DIR__));            // web/
define('AVA_REPO', dirname(AVA_ROOT));           // repository root

/*
 * The site reads ONLY from its own published data folder (default web/data/),
 * which tools/publish_web.py refreshes after each pipeline update:
 *   data/ava.db                       snapshot of the AVA database (read-only here)
 *   data/filter_dict.txt              filter names, wavelengths, colours
 *   data/plots/<data_id>/*.png        per-target pipeline figures
 *   data/usage/lco_usage_<sem>.png    LCO time-usage plots
 * Override the folder with the AVA_WEB_DATA environment variable.
 */
define('AVA_DATA_DIR', rtrim(getenv('AVA_WEB_DATA') ?: AVA_ROOT . '/data', '/'));
define('AVA_DATA_URL', getenv('AVA_WEB_DATA_URL') ?: 'data');   // public URL of AVA_DATA_DIR
define('AVA_DB_PATH', AVA_DATA_DIR . '/ava.db');
define('AVA_FILTER_DICT', AVA_DATA_DIR . '/filter_dict.txt');
define('AVA_CONTACT_EMAIL', 'jvhs1@st-andrews.ac.uk');   // shown on the Data page for data requests

// Key Projects shown on Live Updates (first semester => number of semesters).
// Key Projects shown on the Live usage page: first semester => number of semesters (KEY2020B-006, KEY2023B-001, KEY2026B-007).
const AVA_KEY_PROJECTS = ['2020B' => 6, '2023B' => 6, '2026B' => 6];

define('AVA_SITE_NAME', 'AVA — AGN Variability Archive');
define('AVA_PI', 'J.V. Hernández Santisteban');
define('AVA_COPYRIGHT_START', 2020);

// What the site shows and counts as an AVA AGN target (includes/db.php: ava_target_filter_sql):
//  - not listed here (catalogue entries that are not AVA targets, by data_id);
//  - not of a non-AGN type (agn.AGN_type, e.g. the X-ray binary IGR J17062-6143);
//  - with LCO frames or FLOYDS spectra in agn_lco (entries without data appear once data arrives).
const AVA_EXCLUDED = ['SDSS_RM201', 'SDSS_RM562'];
const AVA_NON_AGN_TYPES = ['XRB'];

// LCO broad-band filters shown on the site, in wavelength order.
const AVA_LCO_FILTERS = ['u', 'B', 'g', 'V', 'r', 'i', 'z', 'Y'];   // a filter shows only for targets with frames in it
