"""The single LCO-token lookup (ava.lco.token). Production VM, 19 Nov 2026: the cron pipeline found no token because
only $LCO_TOKEN (set in .bashrc) held it and ava's lookup read a different file than lcodb's."""
import pytest

from ava.lco import token as T


class Cfg:
    """Minimal AVA config: lco.token_file relative to ava_root."""
    def __init__(self, root, token_file):
        self.root, self._raw = root, {"lco": {"token_file": token_file}}

    def _resolve(self, p):
        from pathlib import Path
        q = Path(p).expanduser()
        return q if q.is_absolute() else (self.root / q).resolve()


@pytest.fixture
def no_env(monkeypatch, tmp_path):
    for v in T.ENV_VARS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(T, "LEGACY_FILE", str(tmp_path / "no_legacy_token"))


def test_token_from_token_file_without_any_env(tmp_path, no_env):
    secrets = tmp_path / ".secrets"
    secrets.mkdir()
    (secrets / "lco_token").write_text("abc123\n")
    cfg = Cfg(tmp_path / "AVA", "../.secrets/lco_token")            # the template's default, relative to ava_root
    tok, src, _ = T.find_token(ava_cfg=cfg, lcodb_raw={}, env={})
    assert tok == "abc123" and src.endswith(".secrets/lco_token")


def test_lcodb_token_file_relative_to_its_folder(tmp_path, no_env):
    (tmp_path / "secret").write_text("xyz")
    cfg = Cfg(tmp_path, "missing_file")
    tok, src, tried = T.find_token(ava_cfg=cfg, lcodb_raw={"token_file": "../secret"}, lcodb_dir=tmp_path / "config",
                                   env={})
    assert tok == "xyz" and "no such file" in T.describe(tried)


def test_env_first_and_use_env_false_ignores_it(tmp_path, no_env):
    (tmp_path / "f").write_text("from-file")
    cfg = Cfg(tmp_path, "f")
    assert T.find_token(ava_cfg=cfg, lcodb_raw={}, env={"LCO_TOKEN": "from-env"})[0] == "from-env"
    assert T.find_token(ava_cfg=cfg, lcodb_raw={}, env={"LCO_API_TOKEN": "a", "LCO_TOKEN": "b"})[0] == "a"
    assert T.find_token(ava_cfg=cfg, lcodb_raw={}, env={"LCO_TOKEN": "from-env"}, use_env=False)[0] == "from-file"


def test_error_lists_every_place(tmp_path, no_env, monkeypatch):
    for v in T.ENV_VARS:
        monkeypatch.delenv(v, raising=False)
    cfg = Cfg(tmp_path, "nope")
    with pytest.raises(T.TokenNotFound) as e:
        T.require_token(ava_cfg=cfg, lcodb_raw={"token_file": "/also/nope"}, lcodb_dir=tmp_path)
    msg = str(e.value)
    for where in ("$LCO_API_TOKEN", "$LCO_TOKEN", "lco.token_file", "token_file (lcodb config)", "old default"):
        assert where in msg
