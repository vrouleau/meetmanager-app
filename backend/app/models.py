"""SQLAlchemy models for Meet Manager."""
from __future__ import annotations

from datetime import date, datetime
from sqlalchemy import (
    Column, Integer, String, Date, DateTime, ForeignKey, Boolean,
    UniqueConstraint, Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


class Base(DeclarativeBase):
    pass


class Gender(enum.Enum):
    M = "M"
    F = "F"


class Club(Base):
    __tablename__ = "clubs"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    code = Column(String(20))
    nation = Column(String(3))
    pin = Column(String(6))
    athletes = relationship("Athlete", back_populates="club")


class Athlete(Base):
    __tablename__ = "athletes"
    id = Column(Integer, primary_key=True)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    gender = Column(SAEnum(Gender), nullable=False)
    birthdate = Column(Date)
    license = Column(String(20))
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)

    club = relationship("Club", back_populates="athletes")
    registrations = relationship("Registration", back_populates="athlete")
    best_times = relationship("BestTime", back_populates="athlete")

    __table_args__ = (
        UniqueConstraint("first_name", "last_name", "club_id", name="uq_athlete"),
    )


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    style_uid = Column(Integer, nullable=False)
    style_name = Column(String(100))
    distance = Column(Integer)
    relay_count = Column(Integer, default=1)
    gender = Column(Integer)  # 1=M, 2=F, 3=Mixed
    event_number = Column(Integer)
    round = Column(Integer)  # 1=final, 2=prelim
    masters = Column(Boolean, default=False)
    session_id = Column(Integer)

    registrations = relationship("Registration", back_populates="event")

    __table_args__ = (
        UniqueConstraint("style_uid", "gender", "masters", "round", name="uq_event"),
    )


class Registration(Base):
    __tablename__ = "registrations"
    id = Column(Integer, primary_key=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    age_code = Column(String(10), nullable=False, default="OPEN")  # 1518, OPEN, MASTERS
    entry_time_ms = Column(Integer)  # None = NT
    created_at = Column(DateTime, default=datetime.utcnow)

    athlete = relationship("Athlete", back_populates="registrations")
    event = relationship("Event", back_populates="registrations")

    __table_args__ = (
        UniqueConstraint("athlete_id", "event_id", "age_code", name="uq_registration"),
    )


class BestTime(Base):
    __tablename__ = "best_times"
    id = Column(Integer, primary_key=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    style_uid = Column(Integer, nullable=False)
    time_ms = Column(Integer, nullable=False)
    course = Column(String(3), nullable=False, default="LCM")  # LCM or SCM
    source = Column(String(100))

    athlete = relationship("Athlete", back_populates="best_times")

    __table_args__ = (
        UniqueConstraint("athlete_id", "style_uid", "course", name="uq_best_time_course"),
    )


class AppConfig(Base):
    __tablename__ = "app_config"
    key = Column(String(50), primary_key=True)
    value = Column(String(500))
