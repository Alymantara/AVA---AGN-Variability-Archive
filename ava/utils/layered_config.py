"""Machine config as overrides on top of the repository's template.

A machine's config file (``data/config/ava_config.yaml``, ``data/config/lcodb_config.yaml``, written by
``tools/make_config.py``) may start with

    base: /data/ava/AVA/config/ava_config.yaml      # absolute, or relative to this file

and then hold ONLY what differs on that machine (paths, token file, n_cores, ...). The template is loaded first and
the overrides are merged into it key by key (nested sections merge; any other value replaces the template's), so
keys added to the template later reach every machine with ``git pull`` and nothing has to be merged by hand.

A file without ``base`` is used as it is (a full copy), as before.
"""
from __future__ import annotations

from pathlib import Path

import yaml


def deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_layered(path: Path) -> tuple[dict, Path | None]:
    """(merged dict, template path or None) for the config file ``path``."""
    path = Path(path)
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    base = raw.pop("base", None)
    if not base:
        return raw, None
    bp = Path(str(base)).expanduser()
    if not bp.is_absolute():
        bp = (path.parent / bp).resolve()
    with open(bp) as f:
        template = yaml.safe_load(f) or {}
    if template.get("base"):
        raise ValueError(f"{bp}: a template cannot itself have a base")
    return deep_merge(template, raw), bp


def flatten(d: dict, prefix: str = "") -> dict:
    """{"a.b.c": value} for every leaf (lists are leaves)."""
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict) and v:
            out.update(flatten(v, key + "."))
        else:
            out[key] = v
    return out
