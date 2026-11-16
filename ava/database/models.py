"""
AVA database models (SQLAlchemy ORM).

Table design
------------
AGN             — one row per target; the master catalogue
  ↳ AGNLCOStats   — LCO + FLOYDS observing statistics (updated daily)
  ↳ LCOTarget     — LCO archive name aliases (many per AGN)

Key design decisions vs the legacy database_all_targets.txt
------------------------------------------------------------
* data_id      replaces the legacy `directory` column (filesystem slug,
               e.g. "fairall_9") and is equivalent to what ava_id indexes.
* lco_active   replaces legacy `LCO` flag
* lt_active    replaces legacy `LT` flag
* agn_field_id replaces legacy `agn_id` — the 1-based row index of the AGN
               in the per-target APASS field-star catalogue (apass_pytics.csv).
               The calibration task uses this to identify which SExtractor
               source is the AGN among the many stars in the image.
* ra_deg / dec_deg  — coordinates always stored in decimal degrees.
               The legacy ra/dec sexagesimal columns are dropped.
* LCOTarget holds all LCO archive name spellings for one AGN (many-to-one).
  The pipeline assigns incoming daily images to the correct AGN by matching
  the FITS OBJECT keyword against LCOTarget.object, resolved via ava_id.
"""

from sqlalchemy import (
    Boolean, Column, Float, ForeignKey, Integer, Text,
    UniqueConstraint, create_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship, Session


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
class AGN(Base):
    """
    Master AGN table.  One row per unique astrophysical source.
    """
    __tablename__ = "agn"

    # --- Identity -----------------------------------------------------------
    id          = Column(Integer, primary_key=True)

    # Human-readable name, as used in publications.
    name        = Column(Text, nullable=False, unique=True)

    # Filesystem slug — used as the per-target working directory name and
    # as the data_id key throughout the pipeline.  Replaces legacy `directory`.
    # Examples: "fairall_9", "mrk_817", "ngc_5548"
    data_id     = Column(Text, unique=True, nullable=False)

    # SIMBAD canonical name (for cross-matching and URL construction).
    simbad_name = Column(Text)

    # --- Monitoring status --------------------------------------------------
    # Pipeline activity flags
    lco_active  = Column(Boolean, default=True, nullable=False)
    # True = target is currently being observed by LCO.
    # Replaces legacy `LCO` column.

    lt_active   = Column(Boolean, default=False, nullable=False)
    # True = target also has Liverpool Telescope photometry.
    # Replaces legacy `LT` column.

    # Archive visibility: 0 = candidate, 1 = monitored, 2 = published
    ava         = Column(Integer, default=0)
    public      = Column(Integer, default=0)

    # --- Coordinates (decimal degrees, J2000) --------------------------------
    # Replaces legacy ra/dec sexagesimal + ra_deg/dec_deg pair.
    # Store decimal degrees only — convert at import time.
    ra_deg      = Column(Float, nullable=False)
    dec_deg     = Column(Float, nullable=False)

    # --- Field-star catalogue identifier ------------------------------------
    # The 1-based row index of the AGN in the per-target APASS field-star
    # catalogue (apass_pytics.csv), as matched by SExtractor.
    # This is how the calibration step identifies WHICH source in the image
    # is the AGN, among all detected stars.
    # Replaces legacy `agn_id` column.
    # NULL = not yet determined or not applicable.
    agn_field_id = Column(Integer, nullable=True)

    # --- Physical properties ------------------------------------------------
    Vmag        = Column(Float)
    AGN_type    = Column(Text)
    redshift    = Column(Float)
    red_cite    = Column(Text)
    ebv         = Column(Float)         # Galactic E(B-V)
    logl        = Column(Float)         # log bolometric luminosity (erg/s)
    l_5100      = Column(Float)         # log lambda*L_lambda at 5100 Å
    logm        = Column(Float)         # log BH mass (M_sun)
    ledd        = Column(Float)         # Eddington ratio

    # --- Literature / metadata ----------------------------------------------
    cite_name   = Column(Text)          # pipe-separated citation strings
    cite_url    = Column(Text)          # pipe-separated ADS bibcodes
    bentz_id    = Column(Integer)       # Bentz & Katz (2015) catalogue index
    PI          = Column(Text)          # Principal Investigator
    Comments    = Column(Text)
    last_update = Column(Text)          # ISO date of last manual edit

    # --- Relationships -------------------------------------------------------
    lco_stats   = relationship("AGNLCOStats", back_populates="agn",
                               uselist=False, cascade="all, delete-orphan")
    lco_targets = relationship("LCOTarget", back_populates="agn",
                               cascade="all, delete-orphan")

    def __repr__(self):
        return (
            f"<AGN id={self.id} name={self.name!r} "
            f"data_id={self.data_id!r} z={self.redshift}>"
        )


# ---------------------------------------------------------------------------
class AGNLCOStats(Base):
    """
    LCO and FLOYDS observing statistics per AGN.
    Updated daily by the ingest / daily-update task.
    One row per AGN (1:1 with AGN table).
    """
    __tablename__ = "agn_lco"

    db_ava_id           = Column(Integer, ForeignKey("agn.id"), primary_key=True)
    agn                 = relationship("AGN", back_populates="lco_stats")

    # --- Photometry frame counts per filter ---------------------------------
    db_lco_B            = Column(Integer, default=0)
    db_lco_V            = Column(Integer, default=0)
    db_lco_u            = Column(Integer, default=0)
    db_lco_g            = Column(Integer, default=0)
    db_lco_r            = Column(Integer, default=0)
    db_lco_i            = Column(Integer, default=0)
    db_lco_z            = Column(Integer, default=0)

    # Pipe-separated list of all LCO target-name strings for this AGN.
    db_lco_names        = Column(Text)
    db_lco_start        = Column(Text)   # ISO date of first LCO observation
    db_lco_end          = Column(Text)   # ISO date of most recent LCO obs
    db_lco_cadence      = Column(Float)  # median inter-visit gap (days)
    db_lco_visits       = Column(Integer, default=0)
    db_lco_images       = Column(Integer, default=0)
    db_lco_exp_h        = Column(Float,   default=0)  # total exposure hours
    db_lco_proposals    = Column(Text)   # semicolon-separated proposal IDs

    # --- FLOYDS spectroscopy stats ------------------------------------------
    db_floyds_epochs    = Column(Integer, default=0)
    db_floyds_cadence   = Column(Float)
    db_floyds_start     = Column(Text)
    db_floyds_end       = Column(Text)
    db_floyds_frames    = Column(Integer, default=0)
    db_floyds_exp_h     = Column(Float,   default=0)
    db_floyds_proposals = Column(Text)

    db_updated          = Column(Text)   # ISO timestamp of last stats refresh

    def __repr__(self):
        return (
            f"<AGNLCOStats ava_id={self.db_ava_id} "
            f"phot={self.db_lco_images} spec={self.db_floyds_frames}>"
        )


# ---------------------------------------------------------------------------
class LCOTarget(Base):
    """
    LCO archive name aliases.

    One AGN is typically observed under several name spellings in the LCO
    archive (e.g. "Mrk 817", "Mrk817", "Mrk_817").  Each spelling is a
    separate row here, all pointing to the same AGN via ava_id.

    The pipeline assigns incoming daily photometry images to the correct AGN
    by matching the FITS OBJECT keyword against LCOTarget.object and resolving
    via ava_id — this is the authoritative lookup table for that routing.
    """
    __tablename__ = "lco_targets"
    __table_args__ = (
        UniqueConstraint("object", name="uq_lco_object"),
    )

    id               = Column(Integer, primary_key=True, autoincrement=True)

    # LCO archive OBJECT keyword value (exactly as it appears in FITS headers).
    object           = Column(Text, nullable=False)

    # Foreign key → AGN.id
    ava_id           = Column(Integer, ForeignKey("agn.id"), nullable=True)
    agn              = relationship("AGN", back_populates="lco_targets")

    # Convenience denormalised fields (redundant with AGN, kept for fast lookups)
    ava_data_id      = Column(Text)   # mirrors AGN.data_id
    ava_name         = Column(Text)   # mirrors AGN.name

    # Match provenance
    sep_arcsec       = Column(Float)   # separation between LCO pos and AVA pos
    matched_by       = Column(Text)    # "position (header)+name", "name", "override"
    pos_source       = Column(Text)    # "header" | "footprint"
    obj_ra           = Column(Float)   # median requested RA from LCO headers (deg)
    obj_dec          = Column(Float)   # median requested Dec from LCO headers (deg)

    # Frame counts
    n_phot           = Column(Integer, default=0)
    n_spec           = Column(Integer, default=0)

    # Review flag: set when automatic matching was ambiguous
    review           = Column(Text)
    candidate_ava_id = Column(Integer, nullable=True)

    updated          = Column(Text)    # ISO timestamp of last rebuild

    def __repr__(self):
        return f"<LCOTarget {self.object!r} -> AGN id={self.ava_id}>"


# ---------------------------------------------------------------------------
# Engine helpers
# ---------------------------------------------------------------------------

def get_engine(db_path: str, echo: bool = False):
    """Create a SQLAlchemy engine for SQLite."""
    return create_engine(f"sqlite:///{db_path}", echo=echo)


def init_db(db_path: str, echo: bool = False):
    """Create all tables (safe to call on an existing DB)."""
    engine = get_engine(db_path, echo=echo)
    Base.metadata.create_all(engine)
    return engine
