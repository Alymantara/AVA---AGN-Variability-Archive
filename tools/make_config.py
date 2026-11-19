#!/usr/bin/env python
"""This machine's AVA and lcodb config: OVERRIDES on top of the repository templates.

    python tools/make_config.py init --token-file /data/ava/.secrets/lco_token        # production layout
    python tools/make_config.py init --set paths.archive_root=data/test_archive ...  # any other key
    python tools/make_config.py show                                                 # the merged config in use
    python tools/make_config.py diff /path/to/full_copy_of_ava_config.yaml           # what a full copy changes
    python tools/make_config.py check                                                # paths of other machines?

``init`` writes ``data/config/ava_config.yaml`` and ``data/config/lcodb_config.yaml`` (git-ignored). Each starts with
``base: <the template>`` and holds only what this machine changes; AVA and lcodb load the template and apply the
overrides (``ava.utils.layered_config``), so new template keys arrive with ``git pull`` and nothing is merged by
hand. Both are found without AVA_CONFIG / LCODB_CONFIG (``data/config/`` is looked at first); setting the variables
to these files is fine too.

Production layout written by ``init`` (relative to the checkout, ``paths.ava_root``):

    data/archive/          paths.archive_root (template default)
    data/ava.db            paths.database (template default)
    data/lcodb/            lcodb db_dir (written as an absolute path)
    data/logs/             paths.logs (template default)
    data/web/              web.data_dir
    data/live/lco_usage/snapshots.csv
                           lco_usage.snapshots.file: the LIVE log, outside git. The repository's
                           data/lco_usage/snapshots.csv is the tracked seed; appending to it would make `git pull` fail.
    ../banzai-floyds, ../miniforge3/envs/banzai/bin/python
                           banzai-floyds (template defaults, relative to the checkout)

``--token-file`` sets ``lco.token_file`` and lcodb ``token_file`` (the path only; the token is never written).
``check`` (also run by ``init``) fails when the merged configs still hold another machine's paths (/Users/, /data2/,
/data3/ that do not exist here), and warns about missing files and folders.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from ava.utils.layered_config import deep_merge, flatten, load_layered  # noqa: E402

TEMPLATES = {"ava": REPO / "config" / "ava_config.yaml", "lcodb": REPO / "config" / "lcodb_config.yaml"}
LOCAL = {"ava": REPO / "data" / "config" / "ava_config.yaml", "lcodb": REPO / "data" / "config" / "lcodb_config.yaml"}
FOREIGN = ("/Users/", "/data2/", "/data3/")

PRODUCTION = {
    "ava": {"web": {"data_dir": "data/web"},
            "lco_usage": {"snapshots": {"file": "data/live/lco_usage/snapshots.csv"}}},
    "lcodb": {},
}


def nested(dotted: str, value) -> dict:
    out = cur = {}
    keys = dotted.split(".")
    for k in keys[:-1]:
        cur[k] = {}
        cur = cur[k]
    cur[keys[-1]] = value
    return out


def parse_set(items: list[str]) -> dict:
    """--set ava:photometry.x=1 / lcodb:db_dir=... / key=value (ava)."""
    out = {"ava": {}, "lcodb": {}}
    for it in items or []:
        if "=" not in it:
            raise SystemExit(f"--set {it!r}: expected key=value")
        key, val = it.split("=", 1)
        which = "ava"
        if ":" in key and key.split(":", 1)[0] in out:
            which, key = key.split(":", 1)
        out[which] = deep_merge(out[which], nested(key, yaml.safe_load(val)))
    return out


def write(which: str, overrides: dict, force: bool) -> Path:
    path = LOCAL[which]
    if path.exists() and not force:
        raise SystemExit(f"{path} exists: use --force to replace it (`show` prints what it holds)")
    path.parent.mkdir(parents=True, exist_ok=True)
    head = (f"# This machine's {which} config: overrides on top of the template below (tools/make_config.py).\n"
            f"# Keys not set here come from the template, so `git pull` brings new settings in.\n")
    body = yaml.safe_dump({"base": str(TEMPLATES[which]), **overrides}, sort_keys=False, default_flow_style=False)
    path.write_text(head + body)
    return path


def check() -> int:
    """0 = fine; 1 = another machine's paths, or missing files."""
    from ava.config import AVAConfig
    from ava.lcodb.config import load_config

    bad = 0
    for which in ("ava", "lcodb"):
        src = LOCAL[which] if LOCAL[which].exists() else TEMPLATES[which]
        merged = load_layered(src)[0]
        for k, v in flatten(merged).items():
            # a path of another machine (the Mac's /Users/..., turgon's /data2/ /data3/) that does not exist here
            if isinstance(v, str) and v.startswith(FOREIGN) and not Path(v).expanduser().exists():
                print(f"FAIL  {which}: {k} = {v}  (another machine's path: it does not exist here)")
                bad = 1
    cfg = AVAConfig(LOCAL["ava"] if LOCAL["ava"].exists() else None)
    lcfg = load_config(cfg.lcodb_config_path)
    r = cfg._raw.get("spectroscopy", {}).get("reduction", {}) or {}
    checks = [("AVA database", cfg.db_path), ("lcodb databases folder", lcfg.db_dir),
              ("banzai-floyds checkout", cfg._resolve(r.get("package") or "")),
              ("banzai-floyds python", cfg._resolve(r.get("python") or "")),
              ("sky flats", cfg._resolve(r.get("skyflats_dir") or ""))]
    for label, p in checks:
        if Path(p).exists():
            print(f"OK    {label}: {p}")
        else:
            print(f"WARN  {label}: {p} does not exist (yet)")
    tok = lcfg.raw.get("token_file")
    print(("OK   " if tok and Path(tok).expanduser().exists() else "WARN ") +
          f" LCO token file: {tok} (read by cron jobs; never put the token itself in a config)")
    print(f"config in use: {cfg._path}  /  {lcfg.path}")
    return bad


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init", help="write data/config/{ava,lcodb}_config.yaml (overrides files)")
    i.add_argument("--token-file", default=None, help="the LCO token file (path only)")
    i.add_argument("--set", action="append", default=[], metavar="[ava:|lcodb:]KEY=VALUE",
                   help="any other override, e.g. pipeline.n_cores=2 or lcodb:daily.include_regex='^KEY2026'")
    i.add_argument("--no-production-defaults", action="store_true",
                   help="do not write the production layout (web.data_dir, the live LCO-usage log)")
    i.add_argument("--force", action="store_true", help="replace existing files")
    sub.add_parser("show", help="print the merged configs in use")
    d = sub.add_parser("diff", help="the keys a full copy changes relative to the template (to turn into overrides)")
    d.add_argument("copy", type=Path)
    d.add_argument("--which", choices=["ava", "lcodb"], default=None, help="default: from the file name")
    sub.add_parser("check", help="another machine's paths, or missing files?")
    a = p.parse_args(argv)

    if a.cmd == "init":
        sets = parse_set(a.set)
        ava = {} if a.no_production_defaults else dict(PRODUCTION["ava"])
        lcodb = {"db_dir": str(REPO / "data" / "lcodb"),
                 "ava": {"db": str(REPO / "data" / "ava.db"), "csv": str(REPO / "data" / "ava" / "ava.csv"),
                         "overrides_csv": str(REPO / "data" / "ava" / "ava_link_overrides.csv")}}
        if a.token_file:
            ava = deep_merge(ava, {"lco": {"token_file": a.token_file}})
            lcodb["token_file"] = a.token_file
        ava, lcodb = deep_merge(ava, sets["ava"]), deep_merge(lcodb, sets["lcodb"])
        for which, ov in (("ava", ava), ("lcodb", lcodb)):
            print(f"wrote {write(which, ov, a.force)}")
        return check()
    if a.cmd == "show":
        for which in ("ava", "lcodb"):
            src = LOCAL[which] if LOCAL[which].exists() else TEMPLATES[which]
            print(f"# ===== {which}: {src}")
            print(yaml.safe_dump(load_layered(src)[0], sort_keys=False))
        return 0
    if a.cmd == "diff":
        which = a.which or ("lcodb" if "lcodb" in a.copy.name else "ava")
        tmpl = flatten(load_layered(TEMPLATES[which])[0])
        copy = flatten(load_layered(a.copy)[0])
        changed = {k: v for k, v in copy.items() if tmpl.get(k, object()) != v}
        missing = [k for k in tmpl if k not in copy]
        print(f"# {a.copy} against {TEMPLATES[which]}")
        print(f"# {len(changed)} key(s) differ (the overrides of this machine, plus any stale value):")
        for k, v in changed.items():
            print(f"{k}: {v!r}    # template: {tmpl.get(k, '(not in template)')!r}")
        print(f"# {len(missing)} template key(s) missing from the copy (added since it was made):")
        for k in missing:
            print(f"#   {k}: {tmpl[k]!r}")
        return 0
    return check()


if __name__ == "__main__":
    sys.exit(main())
