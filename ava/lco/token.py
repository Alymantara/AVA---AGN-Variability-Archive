"""The LCO API token: ONE lookup for the whole package (archive downloads, lcodb, LCO usage, install check).

Order (the first that gives a non-empty token wins):

1. environment variable ``LCO_API_TOKEN`` (the documented one), then ``LCO_TOKEN`` (accepted, older name);
2. the file named by ``lco.token_file`` in the AVA config (``~`` expanded; relative to ``paths.ava_root``);
3. the file named by ``token_file`` in the lcodb config (``~`` expanded; relative to the template's folder);
4. ``~/.lco_token`` (the old default location).

Cron jobs start with no environment, so on a server the FILE is the source that matters: the config templates point
both ``token_file`` keys at ``<install root>/.secrets/lco_token`` (``<ava_root>/../.secrets/lco_token``), the place the
production checklist (F1) puts it. The token itself is never written into a config, a script or a command line.
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_VARS = ("LCO_API_TOKEN", "LCO_TOKEN")
LEGACY_FILE = "~/.lco_token"


class TokenNotFound(RuntimeError):
    pass


def _ava_cfg():
    try:
        from ava.config import cfg
        return cfg
    except Exception:  # noqa: BLE001 - lcodb can run without an AVA config
        return None


def _lcodb_raw_and_dir(ava_cfg):
    """(raw lcodb config, folder its relative paths are taken from) without going through lcodb's loader."""
    try:
        from ava.utils.layered_config import load_layered
        path = ava_cfg.lcodb_config_path
        raw, base = load_layered(path)
        return raw, (base.parent if base is not None else Path(path).parent)
    except Exception:  # noqa: BLE001
        return {}, None


def places(ava_cfg=None, lcodb_raw=None, lcodb_dir=None) -> list[tuple[str, Path | None]]:
    """The token files to look at, in order: (label, absolute path or None when the key is not set)."""
    if ava_cfg is None:
        ava_cfg = _ava_cfg()
    if lcodb_raw is None and ava_cfg is not None:
        lcodb_raw, lcodb_dir = _lcodb_raw_and_dir(ava_cfg)
    out = []
    v = ((getattr(ava_cfg, "_raw", {}) or {}).get("lco", {}) or {}).get("token_file") if ava_cfg is not None else None
    out.append(("lco.token_file (AVA config)", ava_cfg._resolve(v) if v else None))
    v = (lcodb_raw or {}).get("token_file")
    p = Path(v).expanduser() if v else None
    if p is not None and not p.is_absolute() and lcodb_dir is not None:
        p = (Path(lcodb_dir) / p).resolve()
    out.append(("token_file (lcodb config)", p))
    out.append(("old default", Path(LEGACY_FILE).expanduser()))
    return out


def find_token(ava_cfg=None, lcodb_raw=None, lcodb_dir=None, env=None, use_env=True) -> tuple[str | None, str, list]:
    """(token or None, where it came from, every place looked at with what was found there).

    ``use_env=False`` ignores the environment variables: the token as a cron job sees it."""
    env = os.environ if env is None else env
    tried = []
    if use_env:
        for var in ENV_VARS:
            val = (env.get(var) or "").strip()
            tried.append((f"${var}", "set" if val else "not set"))
            if val:
                return val, f"${var}", tried
    seen = set()
    for label, path in places(ava_cfg, lcodb_raw, lcodb_dir):
        if path is None:
            tried.append((label, "not set"))
            continue
        if path in seen:
            continue
        seen.add(path)
        if not path.exists():
            tried.append((f"{label}: {path}", "no such file"))
            continue
        tok = path.read_text().strip()
        tried.append((f"{label}: {path}", "found" if tok else "empty"))
        if tok:
            return tok, str(path), tried
    return None, "", tried


def describe(tried) -> str:
    return "; ".join(f"{where} ({what})" for where, what in tried)


def require_token(**kw) -> str:
    """The token, or TokenNotFound listing every place looked at."""
    tok, _, tried = find_token(**kw)
    if not tok:
        raise TokenNotFound("No LCO API token. Looked at: " + describe(tried) + ". Put the token in the file "
                            "lco.token_file names (chmod 600), or set LCO_API_TOKEN.")
    return tok
