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

    def __getitem__(self, key):
        return self.raw[key]

    def get(self, key, default=None):
        return self.raw.get(key, default)

    @property
    def db_dir(self):
        d = Path(os.path.expanduser(self.raw.get('db_dir', './db')))
        if not d.is_absolute():
            d = self.path.parent / d
        d.mkdir(parents=True, exist_ok=True)
        return d

    def resolve(self, p):
        """Path relative to the config file (None stays None)."""
        if not p:
            return None
        q = Path(os.path.expanduser(p))
        return q if q.is_absolute() else (self.path.parent / q).resolve()

    def db_path(self, kind):
        return self.db_dir / self.raw[f'{kind}_db']


def load_config(path=None):
    path = Path(path or os.environ.get('LCODB_CONFIG', DEFAULT_CONFIG)).resolve()
    with open(path) as f:
        raw = yaml.safe_load(f)
    token = os.environ.get('LCO_TOKEN')
    if not token and raw.get('token_file'):
        tf = Path(os.path.expanduser(raw['token_file']))
        if tf.exists():
            token = tf.read_text().strip() or None
    return Config(raw=raw, path=path, token=token)
