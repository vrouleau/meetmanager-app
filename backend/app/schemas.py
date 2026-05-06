"""Pydantic schemas for API request/response."""
from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, EmailStr
from enum import Enum


class Gender(str, Enum):
    M = "M"
    F = "F"


class AgeCode(str, Enum):
    U1518 = "1518"
    OPEN = "OPEN"
    MASTERS = "MASTERS"


# --- Club ---
class ClubCreate(BaseModel):
    name: str
    code: str | None = None
    city: str | None = None
    contact_email: str | None = None

class ClubOut(ClubCreate):
    id: int
    class Config:
        from_attributes = True


# --- Athlete ---
class AthleteCreate(BaseModel):
    first_name: str
    last_name: str
    gender: Gender
    birthdate: date
    nran: str | None = None
    club_id: int
    email: str | None = None

class AthleteOut(AthleteCreate):
    id: int
    class Config:
        from_attributes = True


# --- Meet ---
class MeetCreate(BaseModel):
    name: str
    city: str | None = None
    date_start: date
    date_end: date | None = None
    age_date: date
    course: str = "LCM"

class MeetOut(MeetCreate):
    id: int
    class Config:
        from_attributes = True


# --- Event ---
class EventCreate(BaseModel):
    meet_id: int
    style_name: str
    style_uid: int
    age_code: str
    gender: str | None = None
    is_relay: bool = False
    relay_count: int = 1
    distance: int | None = None

class EventOut(EventCreate):
    id: int
    class Config:
        from_attributes = True


# --- Registration ---
class RegistrationCreate(BaseModel):
    athlete_id: int
    event_id: int
    best_time_ms: int | None = None

class RegistrationOut(RegistrationCreate):
    id: int
    class Config:
        from_attributes = True


# --- Relay ---
class RelayMemberIn(BaseModel):
    athlete_id: int
    position: int

class RelayTeamCreate(BaseModel):
    registration_id: int
    members: list[RelayMemberIn]

class RelayTeamOut(BaseModel):
    id: int
    registration_id: int
    members: list[RelayMemberIn]
    class Config:
        from_attributes = True
