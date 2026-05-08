"""Generate Lenex .lxf from registrations."""
from __future__ import annotations

import zipfile
from datetime import date
from io import BytesIO
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session, joinedload
from .models import Club, Athlete, Event, Registration


def _ms_to_lenex(ms: int | None) -> str:
    if not ms:
        return "NT"
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    cs = (ms % 1000) // 10
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}.{cs:02d}"
    return f"{m:02d}:{s:02d}.{cs:02d}"


def _gender_str(g: int) -> str:
    return {1: "M", 2: "F", 3: "X"}.get(g, "A")


def generate_lxf(db: Session) -> bytes:
    """Generate a Lenex 3.0 .lxf zip from all registrations."""
    import json, os
    from pathlib import Path

    # Load template for event structure
    template_path = Path(os.environ.get("TEMPLATE_JSON", "/app/template_struct.json"))
    with open(template_path) as f:
        template = json.load(f)

    # Build event_number -> eid mapping (need the SPLASH event IDs)
    # Our DB Event.id is internal; we need the template's eid for Lenex
    # Map: our DB event.id -> template eid
    db_events = db.query(Event).all()
    # Match by style_uid + gender + masters + round
    db_to_splash_eid: dict[int, int] = {}
    for db_ev in db_events:
        for t_ev in template["events"]:
            if (t_ev["uid"] == db_ev.style_uid and
                t_ev["gender"] == db_ev.gender and
                t_ev["masters"] == db_ev.masters and
                t_ev["round"] == db_ev.round):
                db_to_splash_eid[db_ev.id] = t_ev["eid"]
                break

    regs = db.query(Registration).options(
        joinedload(Registration.athlete).joinedload(Athlete.club),
        joinedload(Registration.event),
    ).all()

    # Group by club -> athlete -> entries
    clubs_map: dict[int, dict] = {}
    for reg in regs:
        ath = reg.athlete
        club = ath.club
        if club.id not in clubs_map:
            clubs_map[club.id] = {"club": club, "athletes": {}}
        if ath.id not in clubs_map[club.id]["athletes"]:
            clubs_map[club.id]["athletes"][ath.id] = {"athlete": ath, "entries": []}
        clubs_map[club.id]["athletes"][ath.id]["entries"].append(reg)

    # Build XML
    root = ET.Element("LENEX", version="3.0")
    meets = ET.SubElement(root, "MEETS")
    meet = ET.SubElement(meets, "MEET", {
        "name": "Inscription Export",
        "city": "Laval",
        "course": "LCM",
    })
    ET.SubElement(meet, "AGEDATE", value=date(2026, 12, 31).isoformat(), type="DATE")

    # Sessions + Events from template (so SPLASH can match eventids)
    sessions_xml = ET.SubElement(meet, "SESSIONS")
    from collections import defaultdict
    ses_events = defaultdict(list)
    for t_ev in template["events"]:
        ses_events[t_ev.get("session", 1)].append(t_ev)
    styles = template["styles"]
    for ses_id, tevents in sorted(ses_events.items()):
        ses_xml = ET.SubElement(sessions_xml, "SESSION", {
            "number": str(ses_id), "date": "2026-12-31", "course": "LCM",
        })
        evts_xml = ET.SubElement(ses_xml, "EVENTS")
        for t_ev in sorted(tevents, key=lambda e: e.get("enum", 0)):
            style = styles.get(str(t_ev["uid"]), {})
            ev_xml = ET.SubElement(evts_xml, "EVENT", {
                "eventid": str(t_ev["eid"]),
                "number": str(t_ev.get("enum", 0)),
                "gender": _gender_str(t_ev["gender"]),
                "round": "TIM" if t_ev["round"] == 1 else "PRE",
            })
            ET.SubElement(ev_xml, "SWIMSTYLE", {
                "stroke": "UNKNOWN",
                "distance": str(style.get("distance", 0)),
                "relaycount": str(style.get("relay_count", 1)),
            })

    clubs_xml = ET.SubElement(meet, "CLUBS")
    athlete_counter = 1

    for club_data in clubs_map.values():
        club = club_data["club"]
        club_xml = ET.SubElement(clubs_xml, "CLUB", {
            "name": club.name,
            "code": club.code or "",
            "nation": club.nation or "CAN",
            "clubid": str(club.id),
        })
        athletes_xml = ET.SubElement(club_xml, "ATHLETES")

        for ath_data in club_data["athletes"].values():
            ath = ath_data["athlete"]
            ath_xml = ET.SubElement(athletes_xml, "ATHLETE", {
                "athleteid": str(ath.id),
                "firstname": ath.first_name,
                "lastname": ath.last_name,
                "gender": ath.gender.value,
                "birthdate": str(ath.birthdate) if ath.birthdate else "",
                "license": ath.license or "",
            })
            entries_xml = ET.SubElement(ath_xml, "ENTRIES")
            for reg in ath_data["entries"]:
                splash_eid = db_to_splash_eid.get(reg.event_id)
                if not splash_eid:
                    continue
                entry_attrs = {
                    "eventid": str(splash_eid),
                    "entrycourse": "LCM",
                }
                if reg.entry_time_ms:
                    entry_attrs["entrytime"] = _ms_to_lenex(reg.entry_time_ms)
                ET.SubElement(entries_xml, "ENTRY", entry_attrs)

    xml_bytes = ET.tostring(root, encoding="unicode", xml_declaration=True).encode("utf-8")

    # Wrap in zip
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("meet.lef", xml_bytes)
    return buf.getvalue()
