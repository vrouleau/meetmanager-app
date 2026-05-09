"""Load events from meet .lxf into the Event + AgeGroup tables."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session
from .models import Event, AgeGroup
from .meet_parser import parse_meet_lxf, ParsedMeet


def _load_from_parsed(db: Session, meet: ParsedMeet) -> int:
    """Insert events + age groups from a parsed meet. Returns event count."""
    count = 0
    for ev in meet.all_events:
        event = Event(
            splash_event_id=ev.eventid,
            style_uid=ev.swimstyleid,
            style_name=ev.style_name or f"UID {ev.swimstyleid}",
            distance=ev.distance,
            relay_count=ev.relaycount,
            gender=ev.gender_int,
            event_number=ev.number,
            round=2 if ev.is_prelim else (1 if ev.round == "TIM" else 9),
            masters=ev.is_masters,
            session_id=None,
        )
        db.add(event)
        db.flush()
        for ag in ev.agegroups:
            db.add(AgeGroup(
                event_id=event.id,
                splash_agegroup_id=ag.agegroupid,
                age_min=ag.agemin,
                age_max=ag.agemax,
            ))
        count += 1
    db.commit()
    return count


def load_events(db: Session, lxf_path: Path) -> int:
    """Load events from meet .lxf if table is empty. Returns count."""
    if db.query(Event).first():
        return 0
    meet = parse_meet_lxf(lxf_path)
    return _load_from_parsed(db, meet)
