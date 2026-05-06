"""SQLAlchemy models for Meet Manager."""
from __future__ import annotations

from datetime import date, datetime
from sqlalchemy import (
    Column, Integer, String, Date, DateTime, ForeignKey, Boolean, Text, Float,
    UniqueConstraint, Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


class Base(DeclarativeBase):
    pass


class Gender(enum.Enum):
    M = "M"
    F = "F"


class AgeCode(enum.Enum):
    U1518 = "1518"
    OPEN = "OPEN"
    MASTERS = "MASTERS"


class Club(Base):
    __tablename__ = "clubs"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    code = Column(String(10))
    city = Column(String(100))
    contact_email = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)

    athletes = relationship("Athlete", back_populates="club")
    coaches = relationship("Coach", back_populates="club")


class Coach(Base):
    __tablename__ = "coaches"
    id = Column(Integer, primary_key=True)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    email = Column(String(200), unique=True, nullable=False)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    club = relationship("Club", back_populates="coaches")


class Athlete(Base):
    __tablename__ = "athletes"
    id = Column(Integer, primary_key=True)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    gender = Column(SAEnum(Gender), nullable=False)
    birthdate = Column(Date, nullable=False)
    nran = Column(String(20))
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    email = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)

    club = relationship("Club", back_populates="athletes")
    registrations = relationship("Registration", back_populates="athlete")

    __table_args__ = (
        UniqueConstraint("first_name", "last_name", "birthdate", name="uq_athlete_identity"),
    )


class Meet(Base):
    __tablename__ = "meets"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    city = Column(String(100))
    date_start = Column(Date, nullable=False)
    date_end = Column(Date)
    age_date = Column(Date, nullable=False)
    course = Column(String(3), default="LCM")  # LCM or SCM
    created_at = Column(DateTime, default=datetime.utcnow)

    events = relationship("Event", back_populates="meet")


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    meet_id = Column(Integer, ForeignKey("meets.id"), nullable=False)
    style_name = Column(String(50), nullable=False)  # Obstacle, Remorquage, etc.
    style_uid = Column(Integer, nullable=False)       # SPLASH UNIQUEID
    age_code = Column(String(10), nullable=False)
    gender = Column(String(1), nullable=True)    # M, F, or None=mixed
    is_relay = Column(Boolean, default=False)
    relay_count = Column(Integer, default=1)          # 1=individual, 2=corde, 4=relay
    distance = Column(Integer)

    meet = relationship("Meet", back_populates="events")
    registrations = relationship("Registration", back_populates="event")

    __table_args__ = (
        UniqueConstraint("meet_id", "style_uid", "age_code", "gender", "is_relay",
                         name="uq_event"),
    )


class Registration(Base):
    __tablename__ = "registrations"
    id = Column(Integer, primary_key=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    best_time_ms = Column(Integer)  # None = NT
    created_at = Column(DateTime, default=datetime.utcnow)

    athlete = relationship("Athlete", back_populates="registrations")
    event = relationship("Event", back_populates="registrations")
    relay_team = relationship("RelayTeam", back_populates="registration", uselist=False)

    __table_args__ = (
        UniqueConstraint("athlete_id", "event_id", name="uq_registration"),
    )


class RelayTeam(Base):
    __tablename__ = "relay_teams"
    id = Column(Integer, primary_key=True)
    registration_id = Column(Integer, ForeignKey("registrations.id"), nullable=False)

    registration = relationship("Registration", back_populates="relay_team")
    members = relationship("RelayMember", back_populates="team", order_by="RelayMember.position")


class RelayMember(Base):
    __tablename__ = "relay_members"
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("relay_teams.id"), nullable=False)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    position = Column(Integer, nullable=False)  # 1-4

    team = relationship("RelayTeam", back_populates="members")
    athlete = relationship("Athlete")

    __table_args__ = (
        UniqueConstraint("team_id", "position", name="uq_relay_position"),
    )


class BestTime(Base):
    """Historical best times per athlete per style."""
    __tablename__ = "best_times"
    id = Column(Integer, primary_key=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    style_uid = Column(Integer, nullable=False)
    time_ms = Column(Integer, nullable=False)
    source = Column(String(100))  # e.g. "Invitation Laval 2025"
    recorded_at = Column(Date)

    athlete = relationship("Athlete")

    __table_args__ = (
        UniqueConstraint("athlete_id", "style_uid", name="uq_best_time"),
    )
