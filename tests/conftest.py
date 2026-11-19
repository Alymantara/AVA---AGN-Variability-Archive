"""Test-wide settings.

pandas 3 always uses copy-on-write: ``Series.to_numpy()`` / ``.values`` can return a READ-ONLY view, and an in-place
update of it (``&=``, ``+=``, ``a[i] = ...``, ``out=``) raises "output array is read-only" (production VM, 19 Nov
2026: catalogs.measurements).  pandas 2.x allows it unless copy-on-write is switched on, so it is switched on here:
the tests then catch this class of bug on pandas-2 machines too.  (In pandas 3 the option is always on.)
"""
import pandas as pd

if int(pd.__version__.split(".")[0]) < 3:
    pd.options.mode.copy_on_write = True
