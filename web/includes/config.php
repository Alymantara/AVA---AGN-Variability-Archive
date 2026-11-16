<?php
/**
 * AVA website configuration.
 *
 * Paths default to the repository layout (web/ next to data/). On a server,
 * override them with environment variables instead of editing this file:
 *   AVA_WEB_DATA     published data folder (default web/data)
 *   AVA_CONTACT_TO   address that receives contact-form messages (blank = form disabled)
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
define('AVA_CONTACT_TO', getenv('AVA_CONTACT_TO') ?: '');

// Key Projects shown on Live Updates (first semester => number of semesters).
const AVA_KEY_PROJECTS = ['2020B' => 6, '2023B' => 6, '2026B' => 6];

define('AVA_SITE_NAME', 'AVA — AGN Variability Archive');
define('AVA_PI', 'J.V. Hernández Santisteban');
define('AVA_COPYRIGHT_START', 2020);

// LCO broad-band filters shown on the site, in wavelength order.
const AVA_LCO_FILTERS = ['u', 'B', 'g', 'V', 'r', 'i', 'z'];
