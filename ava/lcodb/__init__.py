"""lcodb: SQLite databases of LCO key-project spectra and photometry, built from the archive API.

Part of the AGN Variability Archive (AVA). For analysis, use the query interface:

    from ava.archive import get_archive  # or: Archive = get_archive()
    a = Archive()
"""
__version__ = '0.2.0'


def __getattr__(name):   # lazy, so the CLI does not import pandas
    if name in ('Archive', 'Summary', 'Target', 'to_mjd', 'mjd_to_date'):
        from . import query
        return getattr(query, name)
    raise AttributeError(name)
