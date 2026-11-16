"""Offline tests for ava.config path helpers."""

import yaml

from ava.config import AVAConfig


def _cfg(tmp_path, **paths):
    raw = {"paths": {"ava_root": str(tmp_path), "photometry_root": str(tmp_path / "phot"), **paths}}
    p = tmp_path / "ava_config.yaml"
    p.write_text(yaml.safe_dump(raw))
    return AVAConfig(p)


def test_target_plots_dir_is_inside_the_target_photometry_folder(tmp_path):
    cfg = _cfg(tmp_path)
    d = cfg.target_plots_dir("Mrk_817")
    assert d == cfg.phot_dir("Mrk_817") / "plots"
    assert d.parent.name == "Mrk_817" and d.parent.parent == cfg.phot_root


def test_target_plots_subdir_configurable(tmp_path):
    cfg = _cfg(tmp_path, target_plots_subdir="figures")
    assert cfg.target_plots_dir("fairall_9").name == "figures"
    assert cfg.target_plots_dir("fairall_9").parent == cfg.phot_dir("fairall_9")


def test_no_shared_plots_dir(tmp_path):
    assert not hasattr(AVAConfig, "plots_dir")
