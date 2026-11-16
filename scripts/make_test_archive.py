#!/usr/bin/env python
"""
Build a fresh, empty sandbox archive for testing the pipeline.

Writes into ``paths.test_archive`` (default ``data/test_archive``):

    ava_config.yaml   copy of the active config with every data path
                      (photometry, spectroscopy, plots, logs, database)
                      redirected into the sandbox, and pipeline.only_targets
                      set to the selected AGN
    ava.db            a fresh copy of the AVA database (SQLite backup API), so
                      pipeline writes never touch the real database
    photometry/  spectroscopy/  plots/  logs/   (created empty)

Everything else (LCO token, proposals, lcodb config) is inherited unchanged,
so downloads hit the real archive but land in the sandbox.

Usage:
    python scripts/make_test_archive.py                     # Fairall 9 only
    python scripts/make_test_archive.py -t fairall_9 -t IC_4329
    export AVA_CONFIG=data/test_archive/ava_config.yaml
    python scripts/run_pipeline.py -o --target fairall_9
"""

from __future__ import annotations

import copy
import shutil
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import click
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ava.config import cfg  # noqa: E402

DEFAULT_TARGETS = ("fairall_9",)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("-t", "--target", "targets", multiple=True, default=DEFAULT_TARGETS,
              show_default=True, help="data_id of an AGN to include (repeatable).")
@click.option("--dest", type=click.Path(path_type=Path), default=None,
              help="Sandbox directory [default: paths.test_archive from the config].")
@click.option("--apass-source", type=click.Choice(["aavso", "vizier"]), default=None,
              help="Override photometry.reference.apass_source in the sandbox "
                   "(vizier = APASS DR9, for machines AAVSO refuses).")
@click.option("--reset", is_flag=True,
              help="Delete the existing sandbox first (asks for confirmation).")
def main(targets, dest, apass_source, reset):
    """Create a fresh test archive containing only the selected AGN."""
    dest = (dest or cfg._resolve(cfg.paths.test_archive)).resolve()

    # Guard: never let the sandbox overlap real data roots.
    for real in (cfg.phot_root, cfg.spec_root, cfg.plots_dir):
        if dest == real or real.is_relative_to(dest) or dest.is_relative_to(real):
            raise click.ClickException(f"Sandbox {dest} overlaps a data root ({real}).")

    if reset and dest.exists():
        click.confirm(f"Delete {dest} and everything in it?", abort=True)
        shutil.rmtree(dest)

    entries = []
    for data_id in targets:
        entry = cfg.target_by_data_id(data_id)
        if entry is None:
            raise click.ClickException(f"{data_id!r} is not a usable target in {cfg.db_path}")
        entries.append(entry)

    dest.mkdir(parents=True, exist_ok=True)
    # Private copy of the database: the pipeline writes to it (e.g. agn_gaia_dr3_id).
    db_copy = dest / "ava.db"
    if db_copy.resolve() == cfg.db_path.resolve():
        raise click.ClickException("Sandbox database would be the real database.")
    with closing(sqlite3.connect(f"file:{cfg.db_path}?mode=ro", uri=True)) as src, \
            closing(sqlite3.connect(db_copy)) as dst:
        src.backup(dst)
    (dest / "targets.yaml").unlink(missing_ok=True)  # superseded by the DB copy

    raw = copy.deepcopy(cfg._raw)
    raw["paths"]["ava_root"] = str(cfg.root)
    raw["paths"].update(
        photometry_root=str(dest / "photometry"),
        spectra_root=str(dest / "spectroscopy"),
        plots_dir=str(dest / "plots"),
        logs=str(dest / "logs"),
        database=str(db_copy),
        web_server_host="",
    )
    raw["photometry"].setdefault("calibration", {})["frame_db"] = str(dest / "frame_qc.sqlite")
    raw["pipeline"]["target_source"] = "database"
    raw["pipeline"]["only_targets"] = [e["data_id"] for e in entries]
    if apass_source:
        raw["photometry"]["reference"]["apass_source"] = apass_source
    for sub in ("photometry", "spectroscopy", "plots", "logs"):
        (dest / sub).mkdir(exist_ok=True)

    config_file = dest / "ava_config.yaml"
    config_file.write_text(
        f"# Sandbox config — generated from {cfg._path}\n"
        "# Regenerate with scripts/make_test_archive.py rather than editing.\n"
        + yaml.safe_dump(raw, sort_keys=False)
    )
    config_file.chmod(0o600)

    click.echo(f"[AVA] sandbox archive: {dest}")
    click.echo(f"[AVA] targets: {', '.join(e['data_id'] for e in entries)}")
    click.echo(f"[AVA] use it with:\n  export AVA_CONFIG={config_file}")


if __name__ == "__main__":
    main()
