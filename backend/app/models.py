"""SQLAlchemy models — Splash Meet Manager compatible schema."""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import (
    Column, Integer, SmallInteger, String, Text, Date, DateTime,
    Float, ForeignKey, Boolean, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Splash-native tables
# ---------------------------------------------------------------------------

class SwimStyle(Base):
    """swimstyle — stroke/distance definitions."""
    __tablename__ = "swimstyle"
    swimstyleid = Column(Integer, primary_key=True)
    code = Column(String(10))
    distance = Column(Integer, nullable=False, default=0)
    name = Column(String(100))
    relaycount = Column(Integer, default=1)
    stroke = Column(String(20))
    sortcode = Column(Integer)
    technique = Column(String(20))
    uniqueid = Column(Integer)


class Club(Base):
    """club — team/club."""
    __tablename__ = "club"
    clubid = Column(Integer, primary_key=True)
    code = Column(String(20), unique=True)
    name = Column(String(100), nullable=False)
    nation = Column(String(3))
    shortname = Column(String(50))
    region = Column(String(50))
    # Team-specific extra columns (not in Splash)
    pin = Column(String(20))
    email = Column(String(200))
    stripe_account_id = Column(String(100))
    invite_send_count = Column(Integer, default=0, nullable=False, server_default="0")
    stripe_send_count = Column(Integer, default=0, nullable=False, server_default="0")

    athletes = relationship("Athlete", back_populates="club")


class Athlete(Base):
    """athlete — individual competitor."""
    __tablename__ = "athlete"
    athleteid = Column(Integer, primary_key=True)
    clubid = Column(Integer, ForeignKey("club.clubid"), nullable=False)
    firstname = Column(String(50), nullable=False)
    lastname = Column(String(50), nullable=False)
    gender = Column(SmallInteger, nullable=False)  # 1=M, 2=F
    birthdate = Column(Date)
    license = Column(String(20))
    nation = Column(String(3))
    exception = Column(String(1))  # 'X' for Masters

    club = relationship("Club", back_populates="athletes")
    results = relationship("SwimResult", back_populates="athlete")

    __table_args__ = (
        UniqueConstraint("firstname", "lastname", "clubid", name="uq_athlete"),
    )


class SwimSession(Base):
    """swimsession — competition session."""
    __tablename__ = "swimsession"
    swimsessionid = Column(Integer, primary_key=True)
    sessionnumber = Column(Integer)
    name = Column(String(100))
    course = Column(SmallInteger)  # 1=LCM, 2=SCY, 3=SCM
    daytime = Column(DateTime)

    events = relationship("SwimEvent", back_populates="session")


class SwimEvent(Base):
    """swimevent — a single event in a session."""
    __tablename__ = "swimevent"
    swimeventid = Column(Integer, primary_key=True)
    swimsessionid = Column(Integer, ForeignKey("swimsession.swimsessionid"))
    swimstyleid = Column(Integer, ForeignKey("swimstyle.swimstyleid"), nullable=False)
    eventnumber = Column(Integer)
    gender = Column(SmallInteger)  # 1=M, 2=F, 3=Mixed, 0=All
    round = Column(SmallInteger)  # 1=PRE, 2=SEM, 4=FIN, 5=TIM
    masters = Column(String(1), default="F")  # 'T'/'F'
    fee = Column(Float, default=0.0)  # dollars
    internalevent = Column(String(1), default="F")

    session = relationship("SwimSession", back_populates="events")
    swimstyle = relationship("SwimStyle")
    agegroups = relationship("AgeGroup", back_populates="event",
                             cascade="all, delete-orphan")
    results = relationship("SwimResult", back_populates="event")


class AgeGroup(Base):
    """agegroup — age category for an event."""
    __tablename__ = "agegroup"
    agegroupid = Column(Integer, primary_key=True)
    swimeventid = Column(Integer, ForeignKey("swimevent.swimeventid", ondelete="CASCADE"),
                         nullable=False)
    name = Column(String(50))
    agemin = Column(Integer, nullable=False)
    agemax = Column(Integer, nullable=False)  # -1 = no upper bound
    gender = Column(SmallInteger)

    event = relationship("SwimEvent", back_populates="agegroups")


class SwimResult(Base):
    """swimresult — entry/result row.

    A registration is a swimresult with entrytime set and swimtime=NULL.
    Best times are stored as qttime/qtcourse/qtdate on the same row.
    """
    __tablename__ = "swimresult"
    swimresultid = Column(Integer, primary_key=True)
    athleteid = Column(Integer, ForeignKey("athlete.athleteid"), nullable=False)
    swimeventid = Column(Integer, ForeignKey("swimevent.swimeventid"), nullable=False)
    agegroupid = Column(Integer, ForeignKey("agegroup.agegroupid"))
    heatid = Column(Integer)
    lane = Column(Integer)
    entrytime = Column(Integer)  # ms, NULL = NT
    swimtime = Column(Integer)  # ms, NULL = not swum yet
    # Qualification time fields (best time)
    qttime = Column(Integer)  # ms
    qtcourse = Column(SmallInteger)  # 1=LCM, 2=SCY, 3=SCM
    qtdate = Column(Date)
    qtname = Column(String(100))  # source meet name
    # Team-specific: age_code for category tracking
    age_code = Column(String(10), default="Open")
    created_at = Column(DateTime, default=datetime.utcnow)

    athlete = relationship("Athlete", back_populates="results")
    event = relationship("SwimEvent", back_populates="results")
    agegroup = relationship("AgeGroup")

    __table_args__ = (
        UniqueConstraint("athleteid", "swimeventid", "age_code",
                         name="uq_swimresult_entry"),
    )


class BsGlobal(Base):
    """bsglobal — key-value config (replaces app_config)."""
    __tablename__ = "bsglobal"
    name = Column(String(100), primary_key=True)
    data = Column(Text)


class SecretLink(Base):
    """secret_links — one-time PIN reveal links (team-specific)."""
    __tablename__ = "secret_links"
    id = Column(Integer, primary_key=True)
    token = Column(String(36), unique=True, nullable=False)
    club_id = Column(Integer, ForeignKey("club.clubid"), nullable=False)
    pin_encrypted = Column(String(200), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    viewed = Column(Boolean, default=False)
    lang = Column(String(2), default="fr")
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Helper constants for gender/course/round encoding
# ---------------------------------------------------------------------------

GENDER_M = 1
GENDER_F = 2
GENDER_MIXED = 3

COURSE_LCM = 1
COURSE_SCY = 2
COURSE_SCM = 3

ROUND_PRE = 1
ROUND_SEM = 2
ROUND_FIN = 4
ROUND_TIM = 5


def gender_to_str(g: int) -> str:
    """Convert integer gender to M/F string for API responses."""
    return "M" if g == GENDER_M else "F"


def gender_from_str(s: str) -> int:
    """Convert M/F string to integer gender."""
    return GENDER_M if s == "M" else GENDER_F


def course_to_str(c: int | None) -> str:
    """Convert integer course to LCM/SCM/SCY string."""
    if c == COURSE_SCM:
        return "SCM"
    if c == COURSE_SCY:
        return "SCY"
    return "LCM"


def course_from_str(s: str) -> int:
    """Convert LCM/SCM/SCY string to integer."""
    if s == "SCM":
        return COURSE_SCM
    if s == "SCY":
        return COURSE_SCY
    return COURSE_LCM


def fee_dollars_to_cents(fee: float | None) -> int:
    """Convert fee in dollars (float) to cents (int)."""
    if fee is None:
        return 0
    return round(fee * 100)


def fee_cents_to_dollars(cents: int | None) -> float:
    """Convert fee in cents to dollars."""
    if cents is None:
        return 0.0
    return cents / 100.0
