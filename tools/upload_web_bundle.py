#!/usr/bin/env python3
"""Upload the standalone AVA website bundle to a personal site over FTPS (or plain FTP).

Dry run by default: lists what would be sent. Add --live to upload.

    python tools/upload_web_bundle.py --host ftp.example.org --remote-dir public_html/ava            # dry run
    python tools/upload_web_bundle.py --host ftp.example.org --remote-dir public_html/ava --live     # upload

Settings can be kept in ~/.ava_web_upload.json (outside the repository) instead of on the command line:
    {"host": "ftp.example.org", "remote_dir": "public_html/ava", "protocol": "ftps", "user": "me"}

Password: read from ~/.netrc ("machine <host> login <user> password <...>", chmod 600), otherwise asked for in
the terminal. It is never stored by this script.

Only changed files are sent: a manifest of what was uploaded (path, size, mtime) is kept next to the bundle as
<bundle>.uploaded.json. Files that were uploaded before and are no longer in the bundle are deleted on the server;
files the script never uploaded are never touched. Each file is sent as <name>.tmp and then renamed, so visitors
never see a half-written ava.db. The .htaccess rules go first (so ava.db is never downloadable), then the data,
then ava.db and the PHP pages last, so the database never points at plots that are not there yet. Use --full to resend everything (e.g. after files were changed on the
server by hand).

Pure standard library (ftplib), Python >= 3.8.
"""

from __future__ import annotations

import argparse
import ftplib
import getpass
import json
import netrc
import os
import sys
import time
from pathlib import Path, PurePosixPath

SETTINGS = Path.home() / ".ava_web_upload.json"
SKIP = {".DS_Store"}


def load_settings(args: argparse.Namespace) -> dict:
    cfg = {}
    if SETTINGS.is_file():
        cfg = json.loads(SETTINGS.read_text())
    for key in ("host", "remote_dir", "protocol", "user", "port"):
        val = getattr(args, key)
        if val is not None:
            cfg[key] = val
    cfg.setdefault("protocol", "ftps")
    cfg.setdefault("port", 21)
    missing = [k for k in ("host", "remote_dir") if not cfg.get(k)]
    if missing:
        sys.exit(f"error: missing {', '.join(missing)} (command line or {SETTINGS})")
    if cfg["protocol"] not in ("ftps", "ftp"):
        sys.exit("error: --protocol must be ftps or ftp")
    return cfg


def scan(bundle: Path) -> dict[str, list[int]]:
    """Relative POSIX path -> [size, mtime_ns] for every file in the bundle (dotfiles included)."""
    out = {}
    for root, dirs, files in os.walk(bundle):
        dirs.sort()
        for name in sorted(files):
            if name in SKIP or name.endswith(".tmp"):
                continue
            p = Path(root, name)
            st = p.stat()
            out[p.relative_to(bundle).as_posix()] = [st.st_size, st.st_mtime_ns]
    return out


def upload_order(path: str) -> tuple:
    """Access rules first (ava.db is never exposed), then data and assets, then the database, then the PHP code."""
    if path.endswith(".htaccess"):
        return (0, path)
    if path == "data/ava.db":
        return (2, path)
    if path.endswith(".php"):
        return (3, path)
    return (1, path)


def credentials(cfg: dict) -> tuple[str, str]:
    user, password = cfg.get("user"), None
    try:
        auth = netrc.netrc().authenticators(cfg["host"])
    except (FileNotFoundError, netrc.NetrcParseError):
        auth = None
    if auth:
        user = user or auth[0]
        password = auth[2]
    if not user:
        user = input(f"FTP user for {cfg['host']}: ").strip()
    if password is None:
        if not sys.stdin.isatty():
            sys.exit(f"error: no password for {cfg['host']} in ~/.netrc and no terminal to ask for one")
        password = getpass.getpass(f"FTP password for {user}@{cfg['host']}: ")
    return user, password


class _FTPS(ftplib.FTP_TLS):
    """FTP_TLS whose uploads do not wait for the server's TLS close_notify on the data channel.

    Many shared-host FTPS servers never answer it, so ftplib's conn.unwrap() hangs until the timeout although the
    file has arrived. Completeness is checked instead by the transfer reply and by Remote.put (SIZE after rename).
    """

    def storbinary(self, cmd, fp, blocksize=65536, callback=None, rest=None):
        self.voidcmd("TYPE I")
        with self.transfercmd(cmd, rest) as conn:
            while True:
                buf = fp.read(blocksize)
                if not buf:
                    break
                conn.sendall(buf)
                if callback:
                    callback(buf)
        return self.voidresp()


def connect(cfg: dict) -> ftplib.FTP:
    user, password = credentials(cfg)
    ftp = _FTPS() if cfg["protocol"] == "ftps" else ftplib.FTP()
    ftp.connect(cfg["host"], int(cfg["port"]), timeout=60)
    ftp.login(user, password)
    if cfg["protocol"] == "ftps":
        ftp.prot_p()                      # encrypt the data channel too
    ftp.set_pasv(True)
    return ftp


class Remote:
    def __init__(self, ftp: ftplib.FTP, root: str):
        self.ftp, self.root, self.made = ftp, PurePosixPath(root), set()

    def path(self, rel: str) -> str:
        return str(self.root / rel)

    def makedirs(self, rel_dir: PurePosixPath) -> None:
        parts = (self.root / rel_dir).parts
        for i in range(1, len(parts) + 1):
            d = str(PurePosixPath(*parts[:i]))
            if d in self.made or d == "/":
                continue
            try:
                self.ftp.mkd(d)
            except ftplib.error_perm:
                pass                          # already exists
            self.made.add(d)

    def put(self, local: Path, rel: str) -> None:
        self.makedirs(PurePosixPath(rel).parent)
        target, tmp = self.path(rel), self.path(rel) + ".tmp"
        with open(local, "rb") as fh:
            self.ftp.storbinary(f"STOR {tmp}", fh)
        try:
            self.ftp.rename(tmp, target)
        except ftplib.error_perm:             # some servers will not rename over an existing file
            try:
                self.ftp.delete(target)
            except ftplib.error_perm:
                pass
            self.ftp.rename(tmp, target)
        size = local.stat().st_size
        try:
            remote_size = self.ftp.size(target)
        except ftplib.error_perm:             # server without SIZE: trust the transfer reply
            remote_size = size
        if remote_size != size:
            raise RuntimeError(f"{rel}: server has {remote_size} bytes, expected {size}; rerun to resend")

    def delete(self, rel: str) -> None:
        try:
            self.ftp.delete(self.path(rel))
        except ftplib.error_perm as exc:
            print(f"  (could not delete {rel}: {exc})")


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("bundle", nargs="?", default=str(Path.home() / "ava_web_bundle"),
                    help="bundle folder from tools/export_web_bundle.sh (default ~/ava_web_bundle)")
    ap.add_argument("--host")
    ap.add_argument("--remote-dir", dest="remote_dir", help="folder on the server, e.g. public_html/ava")
    ap.add_argument("--protocol", choices=("ftps", "ftp"), help="default ftps (encrypted); ftp only if the host has no TLS")
    ap.add_argument("--user")
    ap.add_argument("--port", type=int)
    ap.add_argument("--live", action="store_true", help="really upload (default: dry run)")
    ap.add_argument("--full", action="store_true", help="ignore the manifest and resend every file")
    ap.add_argument("--pause", type=float, default=0.5,
                    help="seconds between files (default 0.5), to stay under hosts' connection-rate firewalls")
    args = ap.parse_args(argv)

    bundle = Path(args.bundle).expanduser().resolve()
    if not (bundle / "BUNDLE_INFO.txt").is_file():
        sys.exit(f"error: {bundle} is not a bundle from tools/export_web_bundle.sh")
    cfg = load_settings(args)
    if cfg["protocol"] == "ftp":
        print("warning: plain FTP sends the password unencrypted; use ftps if the host supports it")

    key = f"{cfg['host']}/{cfg['remote_dir'].strip('/')}"    # same server folder whatever the protocol
    manifest_path = bundle.parent / (bundle.name + ".uploaded.json")
    manifests = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    for old in [k for k in manifests if k.split("://", 1)[-1] == key and k != key]:   # older protocol-keyed entries
        manifests.setdefault(key, {}).update(manifests.pop(old))
    sent = {} if args.full else manifests.get(key, {})

    local = scan(bundle)
    changed = sorted((p for p, sig in local.items() if sent.get(p) != sig), key=upload_order)
    removed = sorted(p for p in sent if p not in local)
    nbytes = sum(local[p][0] for p in changed)

    print(f"target:  {cfg['protocol']}://{key}")
    print(f"bundle:  {bundle}  ({len(local)} files)")
    print(f"upload:  {len(changed)} files, {human(nbytes)}" + ("  (first upload: everything)" if not sent else ""))
    print(f"delete:  {len(removed)} files no longer in the bundle")
    for p in changed[:15]:
        print(f"  + {p}")
    if len(changed) > 15:
        print(f"  ... and {len(changed) - 15} more")
    for p in removed[:15]:
        print(f"  - {p}")
    if not args.live:
        print("dry run: nothing sent. Add --live to upload.")
        return 0
    if not changed and not removed:
        print("nothing to do")
        return 0

    ftp = connect(cfg)
    remote = Remote(ftp, cfg["remote_dir"])
    done = dict(sent)

    def save() -> None:
        manifests[key] = done
        tmp = manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(manifests, indent=1, sort_keys=True))
        tmp.replace(manifest_path)

    t0, sofar = time.time(), 0
    try:
        for i, p in enumerate(changed, 1):
            if i > 1 and args.pause > 0:
                time.sleep(args.pause)
            remote.put(bundle / p, p)
            done[p] = local[p]
            sofar += local[p][0]
            if i % 20 == 0 or i == len(changed):
                save()
                print(f"  {i}/{len(changed)} files, {human(sofar)} of {human(nbytes)}, {time.time() - t0:.0f} s")
        for p in removed:
            remote.delete(p)
            done.pop(p, None)
        save()
    finally:
        save()
        try:
            ftp.quit()
        except Exception:
            ftp.close()
    print(f"done: {len(changed)} uploaded, {len(removed)} deleted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
