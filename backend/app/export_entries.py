"""Export all athletes and best times as a Lenex .lxf entries file."""
from __future__ import annotations

import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session, joinedload
from .models import Club, Athlete, BestTime, Event


def _ms_to_lenex(ms: int | None) -> str:
    if not ms:
        return "NT"
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    cs = (ms % 1000) // 10
    return f"{h:02d}:{m:02d}:{s:02d}.{cs:02d}"


def generate_entries_lxf(db: Session) -> bytes:
    """Generate Lenex .lxf with all clubs, athletes, and best times as entry times."""
    clubs = db.query(Club).options(
        joinedload(Club.athletes).joinedload(Athlete.best_times)
    ).all()

    # Collect all unique style_uids and their names from events table
    style_uids: set[int] = set()
    for club in clubs:
        for ath in club.athletes:
            for bt in ath.best_times:
                style_uids.add(bt.style_uid)

    style_names: dict[int, str] = {}
    for uid in style_uids:
        ev = db.query(Event).filter(Event.style_uid == uid).first()
        style_names[uid] = ev.style_name if ev else ""

    root = ET.Element("LENEX", version="3.0")
    meets = ET.SubElement(root, "MEETS")
    meet = ET.SubElement(meets, "MEET", {
        "name": "Entries Export",
        "city": "",
        "course": "LCM",
    })

    # One SESSION with one EVENT per style_uid so re-import maps correctly
    sessions = ET.SubElement(meet, "SESSIONS")
    session = ET.SubElement(sessions, "SESSION", {"number": "1", "course": "LCM"})
    events_xml = ET.SubElement(session, "EVENTS")
    for uid in sorted(style_uids):
        ev_xml = ET.SubElement(events_xml, "EVENT", {
            "eventid": str(uid),
            "number": str(uid),
            "gender": "X",
            "round": "TIM",
        })
        ET.SubElement(ev_xml, "SWIMSTYLE", {
            "swimstyleid": str(uid),
            "name": style_names.get(uid, ""),
            "distance": "0",
            "relaycount": "1",
            "stroke": "FREE",
        })

    clubs_xml = ET.SubElement(meet, "CLUBS")
    for club in clubs:
        if not club.athletes:
            continue
        club_xml = ET.SubElement(clubs_xml, "CLUB", {
            "name": club.name,
            "code": club.code or "",
            "nation": club.nation or "",
        })
        if club.admin_email:
            ET.SubElement(club_xml, "CONTACT", {"email": club.admin_email})
        athletes_xml = ET.SubElement(club_xml, "ATHLETES")
        for ath in club.athletes:
            ath_xml = ET.SubElement(athletes_xml, "ATHLETE", {
                "athleteid": str(ath.id),
                "firstname": ath.first_name,
                "lastname": ath.last_name,
                "gender": ath.gender.value,
                "birthdate": str(ath.birthdate) if ath.birthdate else "",
                "license": ath.license or "",
                **({"exception": ath.exception} if ath.exception else {}),
            })
            if ath.best_times:
                entries_xml = ET.SubElement(ath_xml, "ENTRIES")
                for bt in ath.best_times:
                    entry_xml = ET.SubElement(entries_xml, "ENTRY", {
                        "eventid": str(bt.style_uid),
                        "entrycourse": bt.course,
                        "entrytime": _ms_to_lenex(bt.time_ms),
                    })
                    meetinfo_attrs = {
                        "qualificationtime": _ms_to_lenex(bt.time_ms),
                        "course": bt.course,
                    }
                    if bt.recorded_on:
                        meetinfo_attrs["date"] = str(bt.recorded_on)
                    ET.SubElement(entry_xml, "MEETINFO", meetinfo_attrs)

    xml_bytes = ET.tostring(root, encoding="unicode", xml_declaration=True).encode("utf-8")

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("entries.lef", xml_bytes)
    return buf.getvalue()
