"""Load events from template_struct.json into the Event table."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session
from .models import Event


def load_events(db: Session, json_path: Path) -> int:
    """Load events from template JSON if table is empty. Returns count."""
    if db.query(Event).first():
        return 0  # already loaded

    with open(json_path) as f:
        data = json.load(f)

    styles = data["styles"]  # {uid_str: {distance, relay_count, name}}
    count = 0

    for ev in data["events"]:
        uid = ev["uid"]
        style = styles.get(str(uid), {})
        event = Event(
            style_uid=uid,
            style_name=style.get("name") or f"UID {uid}",
            distance=style.get("distance"),
            relay_count=style.get("relay_count", 1),
            gender=ev["gender"],
            event_number=ev["enum"],
            round=ev["round"],
            masters=ev["masters"],
            session_id=ev["session"],
        )
        db.add(event)
        count += 1

    db.commit()
    return count
