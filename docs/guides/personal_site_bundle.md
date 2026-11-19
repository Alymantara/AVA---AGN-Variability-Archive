---
title: "AVA website on a personal site"
subtitle: "Exporting, uploading and refreshing a standalone copy"
---

# What this is

A standalone copy of the AVA website (`web/`) that serves only the published snapshot: the SQLite database
(`web/data/ava.db`) and the products under `web/data/` (plots, light curves, releases, downloads, usage plots,
manuals, filters, calibration). It runs no pipeline and needs no `ava` package, no config YAML and no access to the
LCO archive.

**Host requirements:** Apache with PHP 8.1 or newer, the `pdo_sqlite` extension, and `.htaccess` overrides
allowed (`AllowOverride All`, or at least `AuthConfig Indexes Options=Indexes`). Visitors' browsers load Bootstrap from
cdn.jsdelivr.net and the Inter font from Google Fonts, as on the main site.

All links are relative, so the copy works at a domain root (`https://ava.example.org/`) or in any sub-folder
(`https://example.org/ava/`) without changes.

# 0. SQLite needs no database server

The site does **not** use MySQL, and nothing has to be set up in the host's database panel. SQLite is a single
file (`data/ava.db`) that PHP opens directly through its `pdo_sqlite` extension, which is built into almost every
PHP 8 installation. "Updating the database" means uploading a new `ava.db` file over the old one (step 4). The
site only reads it.

To confirm that the host has `pdo_sqlite`, upload a file `sqlite_check.php` with this content, open it in a
browser, then **delete it**:

```php
<?php
echo 'PHP ', PHP_VERSION, '<br>';
echo 'pdo_sqlite: ', in_array('sqlite', PDO::getAvailableDrivers(), true) ? 'yes' : 'NO', '<br>';
$db = new PDO('sqlite::memory:');
echo 'SQLite ', $db->query('select sqlite_version()')->fetchColumn();
```

You need PHP 8.1 or newer and `pdo_sqlite: yes`. If it says `NO`, enable `pdo_sqlite` in the host's PHP settings
(often a list of extensions in cPanel's "Select PHP Version") or ask the host to enable it.

Shared hosts often still default to an old PHP (alymantara.com was on PHP 5.6 until it was set to 8.3). In cPanel,
set the domain's version in **MultiPHP Manager**; cPanel records it in the domain's `public_html/.htaccess`
(`cPanel-generated handler` block). Choose 8.3: the site is tested on 8.1 and 8.3; 8.4+ deprecates patterns that
may show warnings. Other PHP software on the same domain (e.g. an old WordPress) is affected by the change too.

# 1. Build the bundle

On the machine with the repository, after the usual web publish (`tools/publish_web.py`) has refreshed
`web/data/`:

```bash
tools/export_web_bundle.sh ~/ava_web_bundle
```

This mirrors `web/` (without `_legacy/`) into `~/ava_web_bundle`, adds a small root `.htaccess`
(`DirectoryIndex index.php`) and writes `BUNDLE_INFO.txt` (export time, git commit, database date; not served).
The folder must be outside the repository. The script refuses a non-empty folder that is not an earlier bundle,
because it mirrors with `rsync --delete`. Set `AVA_BUNDLE_TAR=1` to also write `~/ava_web_bundle.tar.gz`.
The bundle is about 125 MB, most of it the `data/downloads/` light curves.

# 2. Upload (FTP)

`tools/upload_web_bundle.py` sends the bundle over FTPS (encrypted FTP; plain FTP with `--protocol ftp` only if
the host offers nothing else). It needs only the Python standard library.

**One-time setup.** Save the host and folder (no password) in `~/.ava_web_upload.json`:

```json
{"host": "ftp.example.org", "user": "YOUR_FTP_USER", "remote_dir": "public_html/ava", "protocol": "ftps"}
```

The password is either typed when the script asks for it, or kept in `~/.netrc`, which you create yourself and
which only you can read:

```bash
touch ~/.netrc && chmod 600 ~/.netrc && open -e ~/.netrc
```

with one line: `machine ftp.example.org login YOUR_FTP_USER password YOUR_PASSWORD`.

**Upload.** A dry run first lists what would be sent; `--live` sends it:

```bash
python tools/upload_web_bundle.py
```

```bash
python tools/upload_web_bundle.py --live
```

The first upload sends everything (about 125 MB); later ones send only files that changed and delete on the
server the files that were removed from the bundle. The script remembers what it sent in
`~/ava_web_bundle.uploaded.json`; it never touches server files it did not upload. Each file is written as
`<name>.tmp` and renamed when complete, the `.htaccess` rules go first, and `ava.db` and the PHP pages last, so the
site stays consistent while an upload runs. If files on the server were changed by hand, resend everything with
`--full`. An interrupted upload resumes where it stopped when the command is rerun.

Hosts' firewalls block an IP for a while (the site and FTP both time out from that machine, while it still opens
on a phone over mobile data) after too many connections or stalled sessions. The script pauses 0.5 s between files
(`--pause` to change it); if a block happens, wait for it to lift (typically 5–60 min) or unblock the IP in the
hosting panel, then rerun. The first full upload to alymantara.com used plain FTP
(`"protocol": "ftp"`, about 6 min for 125 MB); updates use FTPS.

Hosts with SSH can use `rsync -av --delete ~/ava_web_bundle/ USER@HOST:public_html/ava/` instead (only into a
folder that holds nothing but the AVA copy).

# 3. Check it

- Open `https://YOUR-SITE/ava/` and click through Home, Targets, a target page, Data, Live Updates, Science and
  About.
- Confirm that the private files are blocked (each should give **403**):

```bash
curl -sI https://YOUR-SITE/ava/data/ava.db | head -1
```

```bash
curl -sI https://YOUR-SITE/ava/includes/config.php | head -1
```

If `ava.db` downloads instead, the host ignores `.htaccess`: ask for `AllowOverride` to be enabled, or move
`data/ava.db`, `data/filter_dict.txt` and `data/site.json` out of the web root and point the site at them (below).

# 4. Refresh when the data change

1. Publish as usual on the pipeline side (refreshes `web/data/`).
2. Rerun `tools/export_web_bundle.sh ~/ava_web_bundle`; it updates the folder in place and removes stale files.
3. Rerun `python tools/upload_web_bundle.py --live`; only changed files are sent (usually just `ava.db` and a
   few plots).

Code changes to the site (`web/`) reach the copy the same way.

# Notes

- **Data outside the web root (optional).** The site reads the environment variables `AVA_WEB_DATA` (the
  data folder on disk) and `AVA_WEB_DATA_URL` (its public URL, default `data`). On Apache they can be set with
  `SetEnv` in the root `.htaccess`, where the host allows it. The defaults need no setting.
- The Data page shows the contact address set in `includes/config.php` (`AVA_CONTACT_EMAIL`), as on the main
  site.
- **Nginx hosts** ignore `.htaccess`; deny `data/*.db`, `data/filter_dict.txt`, `data/site.json`,
  `BUNDLE_INFO.txt` and `includes/` in the server block instead.
