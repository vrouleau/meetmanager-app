"""Load events from meet .lxf into the Event table."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session
from .models import Event
from .meet_parser import parse_meet_lxf


def load_events(db: Session, lxf_path: Path) -> int:
    """Load events from meet .lxf if table is empty. Returns count."""
    if db.query(Event).first():
        return 0

    meet = parse_meet_lxf(lxf_path)
    count = 0

    for ev in meet.all_events:
        event = Event(
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
        count += 1

    db.commit()
    return count
