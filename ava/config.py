"""
AVA configuration loader.

Priority (highest first):
  1. Environment variable AVA_CONFIG pointing to a YAML file
  2. config/ava_config.yaml relative to the repository root
  3. FileNotFoundError — no silent defaults for path-sensitive settings

Usage
-----
    from ava.config import cfg

    # Raw dot-access to any section
    cfg.paths.photometry_root     # -> "/data3/jvhs1/agn"
    cfg.photometry.seeing_limit_arcsec  # -> 9.0

    # Convenience resolved-path helpers
    cfg.phot_root              # pathlib.Path  (photometry_root, absolute)
    cfg.spec_root              # pathlib.Path  (spectra_root, absolute)
    cfg.phot_raw(target)       # Path to raw frames for one target
    cfg.spec_raw(target)       # Path to raw FLOYDS frames for one target
    cfg.phot_dir(target)       # Working directory for a target (photometry)
    cfg.spec_dir(target)       # Working directory for a target (spectroscopy)
    cfg.db_path                # Path to the AVA SQLite database
    cfg.target_plots_dir(t)    # Per-target plot folder: <photometry_root>/<target>/plots
    cfg.lco_token              # LCO API token (from file or env var)
    cfg.lco_headers()          # {"Authorization": "Token ..."} for LCO requests
    cfg.lco_username           # LCO account name (lco.username)

Environment variables
---------------------
  AVA_CONFIG       Path to a YAML config file (overrides default location)
  LCO_API_TOKEN    LCO archive API token (overrides config token_file)
  AVA_DB_PASSWORD  PostgreSQL password for the AVA database
  AVA_SECRET_KEY   Flask secret key for the web application
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _pkg_root() -> Path:
    """Repository root: two levels above this file (ava/config.py)."""
    return Path(__file__).parent.parent.resolve()


def _find_config() -> Path:
    env = os.environ.get("AVA_CONFIG")
    if env:
        p = Path(env).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(
                f"AVA_CONFIG points to a missing file: {p}"
            )
        return p
    default = _pkg_root() / "config" / "ava_config.yaml"
    if default.exists():
        return default
    raise FileNotFoundError(
        f"No AVA config found. Create {default} or set AVA_CONFIG."
    )


def _load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


class _NS:
    """Lightweight dot-access wrapper around a dict."""
    def __init__(self, d: dict):
        for k, v in d.items():
            setattr(self, k, _NS(v) if isinstance(v, dict) else v)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __repr__(self):
        return f"_NS({vars(self)})"


# ---------------------------------------------------------------------------
# Main config class
# ---------------------------------------------------------------------------

class AVAConfig:
    """
    Loaded configuration, available as ``cfg.<section>.<key>``.

    All paths are resolved to absolute ``pathlib.Path`` objects by the
    convenience properties below.  Relative paths in the YAML are resolved
    relative to ``ava_root``.
    """

    def __init__(self, path: Optional[Path] = None):
        self._path = path or _find_config()
        self._raw = _load_yaml(self._path)

        # Expose every top-level section as a dot-access namespace.
        for section, data in self._raw.items():
            setattr(self, section, _NS(data) if isinstance(data, dict) else data)

        # Resolve ava_root
        root_str = self._raw.get("paths", {}).get("ava_root", "")
        if root_str:
            self.root = Path(root_str).expanduser().resolve()
        else:
            # Auto-detect: parent of the config file's parent (repo root)
            self.root = _pkg_root()

    # -------------------------------------------------------------------
    # Internal path resolver
    # -------------------------------------------------------------------
    def _resolve(self, p: str) -> Path:
        """Return absolute Path, resolving relative paths from ava_root."""
        q = Path(p).expanduser()
        return q if q.is_absolute() else (self.root / q).resolve()

    def _path_key(self, *keys: str) -> str:
        """Walk the raw dict by dot-separated keys."""
        d = self._raw
        for k in keys:
            d = d[k]
        return str(d)

    # -------------------------------------------------------------------
    # Data root paths (absolute)
    # -------------------------------------------------------------------

    @property
    def phot_root(self) -> Path:
        """Root of the photometry data tree: /data3/jvhs1/agn on production."""
        return self._resolve(self._path_key("paths", "photometry_root"))

    @property
    def spec_root(self) -> Path:
        """Root of the spectroscopy data tree: /data2/jvhs1/agn on production."""
        return self._resolve(self._path_key("paths", "spectra_root"))

    @property
    def template_dir(self) -> Path:
        """Template directory (SExtractor configs etc.)."""
        return self._resolve(self._path_key("paths", "template_dir"))

    @property
    def swift_db(self) -> Path:
        """Swift/UVOT merged database CSV."""
        return self._resolve(self._path_key("paths", "swift_db"))

    # -------------------------------------------------------------------
    # Per-target path helpers
    # -------------------------------------------------------------------

    def phot_dir(self, target: str) -> Path:
        """Working directory for a target's photometry products.

        Layout: <photometry_root>/<target>/
        """
        return self.phot_root / target

    def target_plots_dir(self, target: str) -> Path:
        """Folder for every figure the pipeline makes for one target.

        Layout: <photometry_root>/<target>/<paths.target_plots_subdir> (default ``plots``).
        """
        sub = self._raw.get("paths", {}).get("target_plots_subdir") or "plots"
        return self.phot_dir(target) / sub

    def phot_raw(self, target: str) -> Path:
        """Directory of raw photometric FITS frames for a target.

        Layout: <photometry_root>/raw_data/<target>/
        """
        raw_subdir = self._path_key("paths", "photometry_raw")
        raw_root = (self.phot_root / raw_subdir) if not Path(raw_subdir).is_absolute() \
                    else Path(raw_subdir)
        return raw_root / target

    def spec_dir(self, target: str) -> Path:
        """Working directory for a target's spectroscopy products.

        Layout: <spectra_root>/<target>/
        """
        return self.spec_root / target

    def spec_raw(self, target: str) -> Path:
        """Directory of raw FLOYDS FITS frames for a target.

        Layout: <spectra_root>/raw_data/<target>/
        """
        raw_subdir = self._path_key("paths", "spectra_raw")
        raw_root = (self.spec_root / raw_subdir) if not Path(raw_subdir).is_absolute() \
                    else Path(raw_subdir)
        return raw_root / target

    def sextractor_dir(self, target: str) -> Path:
        """SExtractor catalogue directory for a target."""
        return self.phot_dir(target) / "sextractor_ava"

    def merging_dir(self, target: str) -> Path:
        """CALI inter-calibration workspace for a target."""
        return self.phot_dir(target) / "ava_merging"

    # -------------------------------------------------------------------
    # Database and pipeline paths
    # -------------------------------------------------------------------

    @property
    def db_path(self) -> Path:
        """Path to the AVA SQLite master database."""
        return self._resolve(self._path_key("paths", "database"))

    @property
    def ava_csv(self) -> Path:
        """Path to the AVA master CSV (read by lcodb link)."""
        return self._resolve(self._path_key("paths", "ava_csv"))

    @property
    def floyds_path(self) -> Path:
        """Path to the banzai-floyds working copy."""
        return self._resolve(self._path_key("paths", "floyds_pipeline"))

    @property
    def lcodb_config_path(self) -> Path:
        """Path to the lcodb config.yaml."""
        raw = self._path_key("paths", "lcodb_config")
        if raw:
            return self._resolve(raw)
        # Auto-derive as sibling of banzai-floyds
        return self.floyds_path.parent / "lco_archive_db" / "config.yaml"

    @property
    def log_dir(self) -> Path:
        return self._resolve(self._path_key("paths", "logs"))

    @property
    def target_list_path(self) -> Path:
        """Pipeline target list YAML (pipeline.target_list)."""
        return self._resolve(self._path_key("pipeline", "target_list"))

    # -------------------------------------------------------------------
    # LCO API token
    # -------------------------------------------------------------------

    @property
    def lco_token(self) -> Optional[str]:
        """LCO API token: env var LCO_API_TOKEN takes precedence, then
        the file named by paths.lco.token_file, then lco.api_token."""
        env = os.environ.get("LCO_API_TOKEN")
        if env:
            return env.strip()
        token_file_str = self._raw.get("lco", {}).get("token_file", "~/.lco_token")
        tf = Path(token_file_str).expanduser()
        if tf.exists():
            tok = tf.read_text().strip()
            if tok:
                return tok
        fallback = self._raw.get("lco", {}).get("api_token", "")
        return fallback.strip() or None

    @property
    def lco_username(self) -> Optional[str]:
        """LCO account name (lco.username).  Identification only — API
        access always authenticates with :attr:`lco_token`."""
        return (self._raw.get("lco", {}).get("username") or "").strip() or None

    def lco_headers(self) -> dict:
        """HTTP headers for authenticated LCO archive / portal requests.

        Raises ``RuntimeError`` if no token is configured.
        """
        token = self.lco_token
        if not token:
            raise RuntimeError(
                "No LCO API token: put it in the file named by lco.token_file "
                "(default ~/.lco_token, chmod 600) or set LCO_API_TOKEN."
            )
        return {"Authorization": f"Token {token}"}

    # -------------------------------------------------------------------
    # Aperture helpers
    # -------------------------------------------------------------------

    def science_aperture_index(self, camera: str, mjd: float,
                              target_radius_arcsec: float | None = None) -> int:
        """Return the science aperture index for a frame.

        Looks up the camera's known pixel scale (no FITS header needed) and
        finds the aperture index whose physical diameter is closest to the
        configured science aperture.

        Parameters
        ----------
        camera : str
            LCO instrument_id (e.g. 'fa14', 'fs01', 'ep05') or family name
            ('sinistro', 'spectral', 'muscat3').
        mjd : float
            Mid-exposure MJD.  Determines which aperture series applies:
            old 10-aperture series before MJD 60909; new 12-aperture series
            from MJD 60909 onward.
        target_radius_arcsec : float, optional
            Target aperture radius in arcsec.  Defaults to
            photometry.science_aperture_radius_arcsec in the config (5.0").
        """
        if target_radius_arcsec is None:
            target_radius_arcsec = float(
                self._raw.get("photometry", {})
                         .get("science_aperture_radius_arcsec", 5.0)
            )
        from ava.photometry.apertures import science_aperture_index as _sai
        return _sai(camera, mjd, target_radius_arcsec)


    # -------------------------------------------------------------------
    # Target list helpers
    # -------------------------------------------------------------------

    def load_targets(self) -> list[dict]:
        """Load the targets the pipeline knows about.

        Source (``pipeline.target_source``):
          * ``"database"`` (default) — the AVA database (``paths.database``),
            via :mod:`ava.database.query`.  The DB is the source of truth.
            ``ra_deg``/``dec_deg`` are the nucleus; per-OBJECT pointings are
            in ``pointings``.  Restricted to ``pipeline.only_targets`` if set.
          * ``"yaml"`` — ``pipeline.target_list`` (reference copy only).

        Each dict has at least: name, data_id, ra_deg, dec_deg, lco_active,
        lt_active, lco_names (list of str).
        """
        pipeline_cfg = self._raw.get("pipeline", {})
        source = pipeline_cfg.get("target_source", "database")
        if source == "database":
            from ava.database import query
            targets = query.targets(self.db_path)
        elif source == "yaml":
            import yaml
            list_key = pipeline_cfg.get("target_list", "")
            targets_path = self._resolve(list_key) if list_key else (self.root / "config" / "targets.yaml")
            with open(targets_path) as f:
                targets = (yaml.safe_load(f) or {}).get("targets", [])
        else:
            raise ValueError(f"pipeline.target_source must be 'database' or 'yaml', not {source!r}")
        only = pipeline_cfg.get("only_targets")
        if only:
            targets = [t for t in targets if t["data_id"] in set(only)]
        return targets

    def target_by_data_id(self, data_id: str) -> dict | None:
        """Return the targets.yaml entry for a given data_id, or None."""
        for t in self.load_targets():
            if t["data_id"] == data_id:
                return t
        return None

    @staticmethod
    def agn_position(entry: dict) -> tuple[float, float]:
        """Nucleus (ra, dec) of a target entry, in degrees.

        Uses ``agn_ra_deg`` / ``agn_dec_deg`` when the pointing is offset from
        the AGN (e.g. NGC 4395), otherwise ``ra_deg`` / ``dec_deg``.
        """
        if entry.get("agn_ra_deg") is not None and entry.get("agn_dec_deg") is not None:
            return float(entry["agn_ra_deg"]), float(entry["agn_dec_deg"])
        return float(entry["ra_deg"]), float(entry["dec_deg"])

    def target_by_lco_name(self, lco_name: str) -> dict | None:
        """Return the targets.yaml entry whose lco_names list includes
        lco_name (case-insensitive, whitespace-normalised).

        Used to route an incoming FITS frame (OBJECT keyword) to the
        correct AVA target.
        """
        norm = lco_name.upper().replace(" ", "").replace("_", "")
        for t in self.load_targets():
            for alias in t.get("lco_names", []):
                if alias.upper().replace(" ", "").replace("_", "") == norm:
                    return t
        return None

    # -------------------------------------------------------------------
    # Repr
    # -------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"AVAConfig(\n"
            f"  config  = {self._path}\n"
            f"  root    = {self.root}\n"
            f"  phot    = {self.phot_root}\n"
            f"  spec    = {self.spec_root}\n"
            f"  db      = {self.db_path}\n"
            f")"
        )


# ---------------------------------------------------------------------------
# Singleton — import this everywhere
# ---------------------------------------------------------------------------
cfg = AVAConfig()
