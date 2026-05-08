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

    # Load meet structure for SPLASH event IDs
    from .meet_parser import parse_meet_lxf
    meet_path = Path(os.environ.get("MEET_LXF", "/app/meet.lxf"))
    meet_struct = parse_meet_lxf(meet_path)

    # Map: our DB event -> SPLASH eventid
    # Match by style_uid + gender + masters + round
    db_events = db.query(Event).all()
    db_to_splash_eid: dict[int, int] = {}
    for db_ev in db_events:
        gender_str = {1: "M", 2: "F", 3: "X"}.get(db_ev.gender, "")
        for m_ev in meet_struct.all_events:
            if (m_ev.swimstyleid == db_ev.style_uid and
                m_ev.gender == gender_str and
                m_ev.is_masters == db_ev.masters and
                ((db_ev.round == 2 and m_ev.is_prelim) or
                 (db_ev.round == 1 and m_ev.round == "TIM") or
                 (db_ev.round == 9 and m_ev.round == "FIN"))):
                db_to_splash_eid[db_ev.id] = m_ev.eventid
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

    # Sessions + Events from meet structure
    sessions_xml = ET.SubElement(meet, "SESSIONS")
    for ses in meet_struct.sessions:
        ses_xml = ET.SubElement(sessions_xml, "SESSION", {
            "number": str(ses.number), "date": "2026-12-31", "course": "LCM",
        })
        evts_xml = ET.SubElement(ses_xml, "EVENTS")
        for m_ev in ses.events:
            ev_xml = ET.SubElement(evts_xml, "EVENT", {
                "eventid": str(m_ev.eventid),
                "number": str(m_ev.number),
                "gender": m_ev.gender,
                "round": m_ev.round,
            })
            ET.SubElement(ev_xml, "SWIMSTYLE", {
                "stroke": "UNKNOWN",
                "distance": str(m_ev.distance),
                "relaycount": str(m_ev.relaycount),
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
