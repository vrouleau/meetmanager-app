"""Generate Lenex XML from database registrations."""
from __future__ import annotations

import datetime as dt
from xml.dom import minidom
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session
from .models import Meet, Event, Registration, Athlete, Club


def ms_to_lenex(ms: int | None) -> str:
    if ms is None or ms <= 0:
        return ""
    h = ms // 3_600_000
    rem = ms % 3_600_000
    m = rem // 60_000
    rem = rem % 60_000
    s = rem // 1000
    cs = (rem % 1000) // 10
    return f"{h:02d}:{m:02d}:{s:02d}.{cs:02d}"


def generate_lenex(db: Session, meet_id: int) -> str:
    """Generate Lenex 3.0 XML for all registrations in a meet."""
    meet = db.query(Meet).get(meet_id)
    if not meet:
        raise ValueError("Meet not found")

    events = db.query(Event).filter(Event.meet_id == meet_id).all()
    registrations = db.query(Registration).filter(
        Registration.event_id.in_([e.id for e in events])
    ).all()

    # Group registrations by athlete, then by club
    athlete_ids = set(r.athlete_id for r in registrations)
    athletes = {a.id: a for a in db.query(Athlete).filter(Athlete.id.in_(athlete_ids)).all()}
    club_ids = set(a.club_id for a in athletes.values())
    clubs = {c.id: c for c in db.query(Club).filter(Club.id.in_(club_ids)).all()}

    event_map = {e.id: e for e in events}

    # Build XML
    root = ET.Element("LENEX", {"version": "3.0"})
    meets_xml = ET.SubElement(root, "MEETS")
    meet_xml = ET.SubElement(meets_xml, "MEET", {
        "name": meet.name,
        "city": meet.city or "",
        "nation": "CAN",
        "course": meet.course or "LCM",
        "timing": "AUTOMATIC",
    })
    ET.SubElement(meet_xml, "AGEDATE", {
        "value": meet.age_date.isoformat(),
        "type": "CAN.FNQ",
    })

    clubs_xml = ET.SubElement(meet_xml, "CLUBS")

    for club_id in sorted(club_ids):
        club = clubs[club_id]
        club_xml = ET.SubElement(clubs_xml, "CLUB", {
            "name": club.name,
            "code": club.code or club.name[:10],
            "nation": "CAN",
        })

        # Athletes in this club with registrations
        club_athletes = [a for a in athletes.values() if a.club_id == club_id]
        if not club_athletes:
            continue

        aths_xml = ET.SubElement(club_xml, "ATHLETES")
        for ath in sorted(club_athletes, key=lambda a: (a.last_name, a.first_name)):
            ath_regs = [r for r in registrations if r.athlete_id == ath.id]
            if not ath_regs:
                continue

            gender = {"M": "M", "F": "F"}.get(ath.gender.value if hasattr(ath.gender, 'value') else ath.gender, "M")
            attrs = {
                "athleteid": str(ath.id),
                "firstname": ath.first_name,
                "lastname": ath.last_name,
                "gender": gender,
                "birthdate": ath.birthdate.isoformat() if ath.birthdate else "",
            }
            if ath.nran:
                attrs["license"] = ath.nran
            ath_xml = ET.SubElement(aths_xml, "ATHLETE", attrs)

            entries_xml = ET.SubElement(ath_xml, "ENTRIES")
            for reg in ath_regs:
                ev = event_map.get(reg.event_id)
                if not ev or ev.is_relay:
                    continue
                entry_attrs = {"eventid": str(ev.id)}
                et = ms_to_lenex(reg.best_time_ms)
                if et:
                    entry_attrs["entrytime"] = et
                    entry_attrs["entrycourse"] = meet.course or "LCM"
                ET.SubElement(entries_xml, "ENTRY", entry_attrs)

    xml_str = minidom.parseString(
        ET.tostring(root, encoding="unicode")
    ).toprettyxml(indent="  ", encoding=None)
    xml_str = "\n".join(l for l in xml_str.splitlines() if l.strip())
    return xml_str
