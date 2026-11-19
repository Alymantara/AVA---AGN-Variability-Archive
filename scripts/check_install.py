#!/usr/bin/env python
"""
Check that this machine is ready to run the AVA pipeline.  Read-only, offline (no archive request), safe to run
any time.

    python scripts/check_install.py            # all checks
    python scripts/check_install.py --tests    # + the offline test suite (pytest)

Each line is OK, WARN (works, but look at it) or FAIL (must be fixed before running the pipeline).
Exit code 1 if anything FAILs.
"""

from __future__ import annotations

import importlib
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PACKAGES = [("astropy", "6.0"), ("astroquery", "0.4.7"), ("astroalign", "2.5"), ("numpy", "1.26"),
            ("scipy", "1.11"), ("pandas", "2.1"), ("pyarrow", "14.0"), ("numba", "0.58"), ("lmfit", "1.2"),
            ("sqlalchemy", "2.0"), ("matplotlib", "3.8"), ("yaml", "6.0"), ("click", "8.1"), ("requests", "2.31"),
            ("prefect", "3.9"), ("pytest", "7.4")]

results: list[tuple[str, str, str]] = []


def report(status: str, what: str, detail: str = "") -> None:
    results.append((status, what, detail))
    print(f"[{status:4s}] {what}" + (f" — {detail}" if detail else ""))


def _version(mod: str) -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version({"yaml": "pyyaml"}.get(mod, mod))
    except PackageNotFoundError:
        return getattr(sys.modules[mod], "__version__", "?")


def ver_ok(have: str, need: str) -> bool:
    def t(v):
        return tuple(int(x) for x in "".join(c if c.isdigit() or c == "." else " " for c in v).split()[0].split(".")[:2])
    try:
        return t(have) >= t(need)
    except Exception:  # noqa: BLE001
        return True


def main(run_tests: bool) -> int:
    print(f"AVA install check — repository {ROOT}\nPython {sys.version.split()[0]} at {sys.executable}\n")
    if sys.version_info < (3, 10):
        report("FAIL", "Python >= 3.10 needed (3.12 recommended)")

    # 1. Python packages
    for mod, need in PACKAGES:
        try:
            importlib.import_module(mod)
            v = _version(mod)
            report("OK" if ver_ok(v, need) else "FAIL", f"package {mod} {v}", "" if ver_ok(v, need) else f"need >= {need}")
        except Exception as exc:  # noqa: BLE001
            report("FAIL", f"package {mod}", f"not importable ({type(exc).__name__}: {exc})")
    try:
        import ava  # noqa: F401
        report("OK", "the ava package imports")
    except Exception as exc:  # noqa: BLE001
        report("FAIL", "the ava package", f"{exc} (run `pip install -e .` in the repository)")
        return 1

    # 2. Configuration
    from ava.config import cfg

    report("OK", f"AVA config {os.environ.get('AVA_CONFIG') or ROOT / 'config/ava_config.yaml'}")
    for name, p in (("archive root (paths.archive_root)", cfg.phot_root.parent if hasattr(cfg, "phot_root") else None),
                    ("photometry root", cfg.phot_root), ("spectroscopy root", cfg.spec_root)):
        if p is None:
            continue
        if Path(p).is_dir():
            ok = os.access(p, os.W_OK)
            report("OK" if ok else "FAIL", f"{name} {p}", "" if ok else "not writable")
        else:
            report("WARN", f"{name} {p}", "does not exist yet (created by the initialise steps)")
    bad = [s for s in ("/Users/",) if s in (ROOT / "config/ava_config.yaml").read_text()] if not os.environ.get(
        "AVA_CONFIG") else []
    if bad:
        report("WARN", "config/ava_config.yaml contains /Users/... paths", "set the paths for this machine (setup step 6)")

    # 3. LCO token (presence only; never printed). Checked the way a CRON job finds it: from the token file, with the
    #    environment variables ignored (cron has none). A token only in $LCO_API_TOKEN / $LCO_TOKEN works in this
    #    shell but not in the scheduled jobs (production VM, 19 Nov 2026).
    try:
        from ava.lco.token import describe, find_token

        tok, src, tried = find_token(ava_cfg=cfg, use_env=False)
        if tok:
            report("OK", "LCO API token (as cron sees it)", f"from {src}")
            mode = Path(src).stat().st_mode
            if mode & 0o077:
                report("WARN", f"{src} is readable by other users", f"run: chmod 600 {src}")
        else:
            env_tok = find_token(ava_cfg=cfg)[0]
            report("FAIL", "LCO API token (as cron sees it)",
                   ("only in an environment variable, which cron jobs do not have; " if env_tok else "not found; ")
                   + "put it in the file lco.token_file names. Looked at: " + describe(tried))
    except Exception as exc:  # noqa: BLE001
        report("FAIL", "LCO API token", str(exc).splitlines()[0])

    # 4. Databases
    try:
        from ava.lcodb.config import load_config

        lc = load_config(cfg.lcodb_config_path)
        for kind in ("photometry", "spectra"):
            p = lc.db_path(kind)
            if not p.exists():
                report("FAIL", f"lcodb {kind} database {p}", "missing: copy it from the other machine (setup step 7)")
                continue
            with sqlite3.connect(f"file:{p}?mode=ro", uri=True) as con:
                n = con.execute("SELECT COUNT(*) FROM frames").fetchone()[0]
                last = con.execute("SELECT MAX(day_obs) FROM frames").fetchone()[0]
            report("OK", f"lcodb {kind} database", f"{p} — {n:,} frames, newest night {last}")
    except Exception as exc:  # noqa: BLE001
        report("FAIL", "lcodb databases", f"{type(exc).__name__}: {exc}")
    db = Path(cfg.db_path)
    if db.exists():
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as con:
            n = con.execute("SELECT COUNT(*) FROM agn").fetchone()[0]
        report("OK", f"AVA database {db}", f"{n} AGN")
    else:
        report("FAIL", f"AVA database {db}", "missing: copy ava.db from the other machine (setup step 7)")

    # 5. SExtractor
    sc = cfg.photometry.sextractor
    from ava.pipeline.tasks.sextract import sextractor_binary   # the configured one, else source-extractor / sex

    exe = sextractor_binary(sc.binary)
    if exe is None:
        report("FAIL", f"SExtractor binary {sc.binary!r} (photometry.sextractor.binary)",
               "not installed (neither source-extractor nor sex on PATH)")
    else:
        try:
            out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30)
            report("OK", f"SExtractor {exe}", (out.stdout or out.stderr).strip().splitlines()[0])
        except Exception as exc:  # noqa: BLE001
            report("WARN", f"SExtractor {exe}", f"--version failed: {exc}")
    conf = cfg._resolve(sc.config_dir)
    miss = [f for f in ("default.sex", "default.param", "default.conv", "default.nnw") if not (conf / f).exists()]
    report("FAIL" if miss else "OK", f"SExtractor configuration {conf}", f"missing {miss}" if miss else "")
    if exe and not miss:
        report(*_sextractor_smoke(exe, conf))

    # 6. banzai-floyds (FLOYDS reduction; separate environment)
    r = cfg._raw.get("spectroscopy", {}).get("reduction", {}) or {}
    py = r.get("python")
    if not py or not Path(py).exists():
        report("WARN", "banzai-floyds Python (spectroscopy.reduction.python)", f"{py!r} not found — needed for -R only")
    else:
        out = subprocess.run([py, "-c", "import banzai_floyds, sys; print(sys.version.split()[0])"],
                             capture_output=True, text=True, timeout=120)
        report("OK" if out.returncode == 0 else "FAIL", f"banzai-floyds environment {py}",
               f"Python {out.stdout.strip()}" if out.returncode == 0 else out.stderr.strip().splitlines()[-1])

    # 7. Tests
    if run_tests:
        out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(ROOT / "tests")],
                             capture_output=True, text=True, cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)})
        last = (out.stdout.strip().splitlines() or ["?"])[-1]
        report("OK" if out.returncode == 0 else "FAIL", "offline test suite", last)

    n_fail = sum(s == "FAIL" for s, _, _ in results)
    n_warn = sum(s == "WARN" for s, _, _ in results)
    print(f"\n{'READY' if not n_fail else 'NOT READY'}: {n_fail} FAIL, {n_warn} WARN")
    return 1 if n_fail else 0


def _sextractor_smoke(exe: str, conf: Path) -> tuple[str, str, str]:
    """Run SExtractor on a small synthetic image with the AVA configuration."""
    import tempfile

    import numpy as np
    from astropy.io import fits

    rng = np.random.default_rng(0)
    img = rng.normal(1000.0, 10.0, (256, 256)).astype(np.float32)
    yy, xx = np.mgrid[:256, :256]
    for x, y in ((60, 60), (180, 90), (120, 200)):
        img += 5e4 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * 2.0 ** 2))
    with tempfile.TemporaryDirectory() as d:
        im, cat = Path(d) / "t.fits", Path(d) / "t_cat.fits"
        fits.PrimaryHDU(img).writeto(im)
        cmd = [exe, str(im), "-c", str(conf / "default.sex"), "-PARAMETERS_NAME", str(conf / "default.param"),
               "-FILTER_NAME", str(conf / "default.conv"), "-STARNNW_NAME", str(conf / "default.nnw"),
               "-CATALOG_NAME", str(cat), "-CATALOG_TYPE", "FITS_1.0", "-CHECKIMAGE_TYPE", "NONE",
               "-WRITE_XML", "N", "-VERBOSE_TYPE", "QUIET"]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if out.returncode != 0 or not cat.exists():
            return "FAIL", "SExtractor test run", (out.stderr.strip().splitlines() or ["no catalogue"])[-1]
        with fits.open(cat) as h:
            n, k = len(h[1].data), h[1].data["MAG_APER"].shape[-1]
    return ("OK" if n >= 3 else "WARN"), "SExtractor test run", f"{n} sources, {k} apertures per source"


if __name__ == "__main__":
    sys.exit(main("--tests" in sys.argv))
