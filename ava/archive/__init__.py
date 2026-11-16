"""
ava.archive — LCO archive database interface.

The lcodb code lives natively at ava/lcodb/ (copied from lco_archive_db).
This module provides the AVA-configured entry point.

Usage:
    from ava.archive import get_archive, Archive
    a = get_archive()                    # uses config/ava_config.yaml for paths
    a.summary('Fairall 9')
    a.overview()
    a.phot('Mrk 817', filters='g')
    a.spectra('NGC 5548', start='2024-01-01')

CLI (equivalent to `lcodb` commands):
    python -m ava.lcodb sync
    python -m ava.lcodb daily
    python -m ava.lcodb status
"""
from __future__ import annotations
from pathlib import Path

from ava.lcodb.query import Archive, Summary, Target, to_mjd, mjd_to_date  # noqa: F401


def get_archive(config: str | Path | None = None) -> Archive:
    """
    Return an Archive instance configured from ava_config.yaml.

    The lcodb config.yaml path is taken from paths.lcodb_config in
    ava_config.yaml. If that key is blank, it is auto-derived as
    ``<floyds_pipeline>/../lco_archive_db/config.yaml``.

    Parameters
    ----------
    config : str or Path, optional
        Explicit path to a lcodb config.yaml; overrides ava_config.yaml.
    """
    if config is None:
        from ava.config import cfg as _ava_cfg
        lcodb_cfg = getattr(_ava_cfg.paths, 'lcodb_config', None)
        if not lcodb_cfg:
            floyds = Path(_ava_cfg.floyds_path)
            lcodb_cfg = floyds.parent / 'lco_archive_db' / 'config.yaml'
        config = str(lcodb_cfg)
    return Archive(config=config)


AVA = Archive  # alias used in some notebooks
__all__ = ['Archive', 'AVA', 'Summary', 'Target', 'to_mjd', 'mjd_to_date', 'get_archive']
