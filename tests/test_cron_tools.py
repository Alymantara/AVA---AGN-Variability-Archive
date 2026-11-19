"""O01 / O02: the cron wrapper, the crontab generator and the daily health check (offline)."""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import daily_check  # noqa: E402
import make_crontab  # noqa: E402


def _run(log_dir, name, *cmd):
    return subprocess.run([str(REPO / "scripts" / "cron_job.sh"), name, str(log_dir), "--", *cmd]).returncode


def test_wrapper_records_every_run(tmp_path):
    assert _run(tmp_path, "ok_job", "bash", "-c", "echo hello") == 0
    assert _run(tmp_path, "bad_job", "bash", "-c", "echo broken >&2; exit 3") == 3
    runs = daily_check.read_runs(tmp_path / "cron_runs.tsv")
    assert [(r["name"], r["rc"]) for r in runs] == [("ok_job", 0), ("bad_job", 3)]
    assert "hello" in (tmp_path / "ok_job.log").read_text() and "exit 3" in (tmp_path / "bad_job.log").read_text()


def test_daily_check_fails_on_missing_or_failed_jobs(tmp_path, capsys):
    _run(tmp_path, "a_test", "true")
    _run(tmp_path, "b_test", "false")
    rc = daily_check.main(["--log-dir", str(tmp_path), "--jobs", "a_test", "b_test", "c_test", "--no-data"])
    out = capsys.readouterr().out
    assert rc == 1 and "OK    a_test" in out and "FAIL  b_test" in out and "FAIL  c_test: no run recorded" in out
    assert daily_check.main(["--log-dir", str(tmp_path), "--jobs", "a_test", "--no-data"]) == 0


def test_crontab_flags_and_block_replacement():
    assert make_crontab.nightly_flags(["download_data", "pytics", "spec_products_data", "publish"]) == \
        ["-d", "-t", "-P", "-w"]
    assert make_crontab.nightly_flags(["extract", "publish"], publish=False) == ["-e"]
    old = ["MAILTO=x", make_crontab.BEGIN, "0 1 * * * old", make_crontab.END, "5 5 * * * other job"]
    assert make_crontab.without_ava_block(old) == ["MAILTO=x", "5 5 * * * other job"]


def test_prefect_env_defaults_and_home(monkeypatch, tmp_path):
    """C10: analytics off (they locked Prefect's SQLite at start-up), start-up timeout, PREFECT_HOME from config."""
    from ava.utils import prefect_env

    for k in (*prefect_env.DEFAULTS, "PREFECT_HOME"):
        monkeypatch.delenv(k, raising=False)

    class C:
        _raw = {"pipeline": {"prefect": {"home": "data/prefect"}}}

        def _resolve(self, p):
            return tmp_path / p
    env = prefect_env.apply(C())
    assert env["PREFECT_SERVER_ANALYTICS_ENABLED"] == "false" and env["DO_NOT_TRACK"] == "1"
    assert env["PREFECT_HOME"] == str(tmp_path / "data/prefect")
    monkeypatch.setenv("PREFECT_SERVER_ANALYTICS_ENABLED", "true")
    assert prefect_env.apply(C())["PREFECT_SERVER_ANALYTICS_ENABLED"] == "true"          # the machine's own wins


def test_production_cleanup_is_dry_until_asked():
    from types import SimpleNamespace
    cfg = SimpleNamespace(pipeline=SimpleNamespace(prefect=SimpleNamespace(nightly_steps=["extract"])))
    dry = "\n".join(make_crontab.production(cfg, Path("/tmp/logs"), None))
    live = "\n".join(make_crontab.production(cfg, Path("/tmp/logs"), None, cleanup_live=True))
    assert "scripts/cleanup.py\n" in dry + "\n" and "cleanup.py --live" in live and "CRON_TZ" not in dry
