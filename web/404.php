<?php
// Site-wide "not found" page. Apache: ErrorDocument 404 /<site path>/404.php (deployment guide).
declare(strict_types=1);
require __DIR__ . '/includes/layout.php';
ava_not_found();
