"""Offline tests: SBIG (kb, 1 m, 2014-16) and Spectral (fs, 2 m, 2014-20) frames: download selection,
extraction and a science aperture that is the same for old (10-aperture) and new catalogues."""
from datetime import datetime

from ava.lco.download import Query
from ava.photometry import apertures
from ava.photometry.process import imaging_frame_ok

RULE = {"kb": ("1m0",)}
PREFIXES = ("fa", "fl", "fs", "ep", "kb")


def test_imaging_frame_ok_sbig_1m_only():
    ok = lambda n, t=None: imaging_frame_ok(n, t, prefixes=PREFIXES, telescopes=RULE)  # noqa: E731
    assert ok("elp1m008-kb74-20140608-0035-e91")
    assert not ok("ogg0m406-kb82-20140608-0001-e91")          # 0.4 m SBIG: other pixel scale
    assert ok("lsc1m005-fa15-20250101-0001-e91") and ok("ogg2m001-ep05-20250101-0001-e91")
    assert not ok("ogg2m001-en06-20250101-0003-e91")          # FLOYDS
    assert ok("kb74", "1m0a") and not ok("kb82", "0m4a")      # instrument id + archive telescope_id


def test_download_query_keeps_1m_sbig_and_filters():
    q = Query(names=["NGC5548"], proposals=["KEY2014A-002"], start=datetime(2014, 5, 1), end=datetime(2014, 8, 7),
              kind="phot", filters=["up", "B", "V", "gp", "rp", "ip", "zs", "Y"], cameras=list(PREFIXES),
              camera_telescopes={"kb": ["1m0"]})
    f = dict(filename="elp1m008-kb74-20140608-0035-e91.fits.fz", configuration_type="EXPOSE",
             primary_optical_element="zs", instrument_id="kb74", telescope_id="1m0a")
    assert q.keep(f)
    assert not q.keep({**f, "instrument_id": "kb82", "telescope_id": "0m4a"})
    assert not q.keep({**f, "primary_optical_element": "R"})
    assert not q.keep({**f, "instrument_id": "sq01"})
    assert q.keep({**f, "instrument_id": None, "telescope_id": None})   # listing without them: filter only


def test_sbig_old_and_new_catalogues_pick_the_same_aperture(monkeypatch):
    """Old-pipeline SBIG catalogues (10 apertures, 8 … 33 px, no APERDIAM) and new ones (default series, 16)
    must use the same physical aperture: 21 px (9.81" at 0.467"/px). No kb override, kb not extended."""
    monkeypatch.setitem(apertures.PIXEL_SCALES, "kb", 0.467)
    monkeypatch.setattr(apertures, "_uses_extended_apertures", lambda cam: cam[:2] == "ep")
    old = apertures.OLD_DIAMETERS_PX
    new = (3, 5, 8, 11, 13, 15, 18, 21, 24, 27, 30, 33, 36, 39, 43, 48)
    i_old = apertures.science_aperture_index_for_catalog("kb69", len(old), 5.25, diameters_px=old)
    i_new = apertures.science_aperture_index_for_catalog("kb74", len(new), 5.25, diameters_px=new)
    assert old[i_old] == new[i_new] == 21


def test_spectral_old_and_new_catalogues_pick_the_same_aperture(monkeypatch):
    """Spectral (0.304"/px): 10.5" = 34.5 px; old (10), 12 and 16-aperture catalogues all pick 33 px (10.03")."""
    monkeypatch.setitem(apertures.PIXEL_SCALES, "fs", 0.304)
    monkeypatch.setattr(apertures, "_uses_extended_apertures", lambda cam: cam[:2] == "ep")
    picks = set()
    for ser in (apertures.OLD_DIAMETERS_PX, apertures.NEW_DIAMETERS_PX,
                (3, 5, 8, 11, 13, 15, 18, 21, 24, 27, 30, 33, 36, 39, 43, 48)):
        picks.add(ser[apertures.science_aperture_index_for_catalog("fs02", len(ser), 5.25, diameters_px=ser)])
    assert picks == {33}
