"""B53: a run that calibrates a target without a reference catalogue builds it first (or calibrate says why)."""
import importlib

import pytest

C = importlib.import_module("ava.pipeline.tasks.calibrate")


def test_needs_reference_catalog(tmp_path, monkeypatch):
    monkeypatch.setattr(C.cfg, "phot_dir", lambda t: tmp_path / t)
    assert C.needs_reference_catalog("J21368-6438", init=False, calibrate_data=True)     # missing: build first
    assert not C.needs_reference_catalog("J21368-6438", init=True, calibrate_data=True)  # -o builds it anyway
    assert not C.needs_reference_catalog("J21368-6438", init=False, calibrate_data=False)
    (tmp_path / "J21368-6438").mkdir()
    (tmp_path / "J21368-6438" / "reference_stars.csv").write_text("star_id\n")
    assert not C.needs_reference_catalog("J21368-6438", init=False, calibrate_data=True)


def test_calibrate_says_what_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(C.cfg, "phot_dir", lambda t: tmp_path / t)
    with pytest.raises(FileNotFoundError, match="no reference catalogue .* run -o"):
        C.calibrate.fn("J21368-6438")
