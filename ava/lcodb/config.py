"""Configuration loading. Everything tunable lives in config.yaml."""
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent.parent / 'config' / 'lcodb_config.yaml'


@dataclass
class Config:
    raw: dict
    path: Path
    token: str = None
    _cache: dict = field(default_factory=dict)
    rel_dir: Path = None      # relative paths are taken from here: the template's folder for an overrides file

    @property
    def _base_dir(self):
        return self.rel_dir or self.path.parent

    def __getitem__(self, key):
        return self.raw[key]

    def get(self, key, default=None):
        return self.raw.get(key, default)

    @property
    def db_dir(self):
        d = Path(os.path.expanduser(self.raw.get('db_dir', './db')))
        if not d.is_absolute():
            d = self._base_dir / d
        d.mkdir(parents=True, exist_ok=True)
        return d

    def resolve(self, p):
        """Path relative to the config file (None stays None)."""
        if not p:
            return None
        q = Path(os.path.expanduser(p))
        return q if q.is_absolute() else (self._base_dir / q).resolve()

    def db_path(self, kind):
        return self.db_dir / self.raw[f'{kind}_db']


LOCAL_CONFIG = DEFAULT_CONFIG.parent.parent / 'data' / 'config' / 'lcodb_config.yaml'   # tools/make_config.py


def load_config(path=None):
    """``path``, else LCODB_CONFIG, else this machine's data/config/lcodb_config.yaml, else the template. A file with
    ``base:`` holds overrides on top of that template (ava.utils.layered_config); its relative paths, like the
    template's, are then relative to the template's folder."""
    from ava.utils.layered_config import load_layered

    path = Path(path or os.environ.get('LCODB_CONFIG') or (LOCAL_CONFIG if LOCAL_CONFIG.exists() else DEFAULT_CONFIG))
    path = path.resolve()
    raw, base = load_layered(path)
    rel_dir = base.parent if base is not None else path.parent
    from ava.lco.token import find_token, _ava_cfg     # the package's single lookup (env, AVA's, this file's token_file)

    token = find_token(ava_cfg=_ava_cfg(), lcodb_raw=raw, lcodb_dir=rel_dir)[0]
    if raw.get('archive_url') or raw.get('portal_url'):
        from . import api
        api.set_urls(raw.get('archive_url'), raw.get('portal_url'))
    return Config(raw=raw, path=path, token=token, rel_dir=rel_dir if base is not None else None)
