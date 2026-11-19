"""B17: a frame whose calibration raised an exception was stored as error:<Type> with the current pipeline
version, so later runs counted it as done and never retried it (unless force)."""
import pandas as pd

from ava.photometry.process import PIPELINE_VERSION, done_frames


def test_error_frames_are_retried_others_skipped():
    fq = pd.DataFrame({"frame": ["a", "b", "c", "d"],
                       "pipeline_version": [PIPELINE_VERSION, PIPELINE_VERSION, "old", PIPELINE_VERSION],
                       "qc_flags": ["", "error:OSError", "", "zp_scatter"]})
    d = done_frames(fq)
    assert d["frames"] == {"a", "d"} and d["_retry"] == 1      # b: error -> retried; c: old version -> redone
    assert done_frames(fq, force=True)["frames"] == set()
    assert done_frames(pd.DataFrame(columns=fq.columns))["frames"] == set()
