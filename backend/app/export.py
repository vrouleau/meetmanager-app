"""Generate Lenex .lxf from registrations."""
from __future__ import annotations

import os
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session, joinedload
from .models import Club, Athlete, Event, Registration, BestTime


def _ms_to_lenex(ms: int | None) -> str:
    if not ms:
        return "NT"
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    cs = (ms % 1000) // 10
    return f"{h:02d}:{m:02d}:{s:02d}.{cs:02d}"


def _agegroup_for_code(age_groups, age_code: str, masters: bool):
    """Pick the AgeGroup row matching the registration's age_code."""
    if masters:
        return age_groups[0] if age_groups else None
    for ag in age_groups:
        if age_code == "10-" and ag.age_max == 10:
            return ag
        if age_code == "11-12" and ag.age_min == 11 and ag.age_max == 12:
            return ag
        if age_code == "13-14" and ag.age_min == 13 and ag.age_max == 14:
            return ag
        if age_code == "15-18" and ag.age_min == 15 and ag.age_max == 18:
            return ag
        if age_code == "Open" and ag.age_min == 19 and ag.age_max == -1:
            return ag
    return None


def generate_lxf(db: Session) -> bytes:
    """Generate a Lenex 3.0 .lxf zip from all registrations."""
    from .meet_parser import parse_meet_lxf
    meet_path = Path(os.environ.get("MEET_STORAGE", "/app/data/meet.lxf"))
    meet_struct = parse_meet_lxf(meet_path)

    regs = db.query(Registration).options(
        joinedload(Registration.athlete).joinedload(Athlete.club),
        joinedload(Registration.event).joinedload(Event.age_groups),
    ).all()

    # Group by club -> athlete -> entries
    clubs_map: dict[int, dict] = {}
    for reg in regs:
        ath = reg.athlete
        club = ath.club
        clubs_map.setdefault(club.id, {"club": club, "athletes": {}})
        clubs_map[club.id]["athletes"].setdefault(ath.id, {"athlete": ath, "entries": []})
        clubs_map[club.id]["athletes"][ath.id]["entries"].append(reg)

    # Build XML
    root = ET.Element("LENEX", version="3.0")
    meets = ET.SubElement(root, "MEETS")
    meet = ET.SubElement(meets, "MEET", {
        "name": meet_struct.meet_name or "Inscription Export",
        "city": "Laval",
        "course": meet_struct.course or "LCM",
    })
    ET.SubElement(meet, "AGEDATE", value=date(2026, 12, 31).isoformat(), type="DATE")

    # Sessions + Events from meet structure (preserves original session/event ids + age groups)
    sessions_xml = ET.SubElement(meet, "SESSIONS")
    for ses in meet_struct.sessions:
        ses_xml = ET.SubElement(sessions_xml, "SESSION", {
            "number": str(ses.number),
            "date": "2026-12-31",
            "course": meet_struct.course or "LCM",
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
            if m_ev.agegroups:
                ags_xml = ET.SubElement(ev_xml, "AGEGROUPS")
                for ag in m_ev.agegroups:
                    ET.SubElement(ags_xml, "AGEGROUP", {
                        "agegroupid": str(ag.agegroupid),
                        "agemin": str(ag.agemin),
                        "agemax": str(ag.agemax),
                    })

    clubs_xml = ET.SubElement(meet, "CLUBS")

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
            if ath.exception:
                ET.SubElement(ath_xml, "HANDICAP", {"exception": ath.exception})
            entries_xml = ET.SubElement(ath_xml, "ENTRIES")
            for reg in ath_data["entries"]:
                ev = reg.event
                if not ev or not ev.splash_event_id:
                    continue
                entry_attrs = {
                    "eventid": str(ev.splash_event_id),
                    "entrycourse": meet_struct.course or "LCM",
                }
                ag = _agegroup_for_code(ev.age_groups, reg.age_code, ev.masters)
                if ag:
                    entry_attrs["agegroupid"] = str(ag.splash_agegroup_id)
                if reg.entry_time_ms:
                    entry_attrs["entrytime"] = _ms_to_lenex(reg.entry_time_ms)
                entry_xml = ET.SubElement(entries_xml, "ENTRY", entry_attrs)
                if reg.entry_time_ms:
                    # Look up best time date for this event's style
                    bt = db.query(BestTime).filter(
                        BestTime.athlete_id == ath.id,
                        BestTime.style_uid == ev.style_uid,
                        BestTime.course == (meet_struct.course or "LCM"),
                    ).first() if ev.style_uid else None
                    meetinfo_attrs = {
                        "qualificationtime": _ms_to_lenex(reg.entry_time_ms),
                        "course": meet_struct.course or "LCM",
                        "date": str(bt.recorded_on) if bt and bt.recorded_on else str(date.today()),
                    }
                    ET.SubElement(entry_xml, "MEETINFO", meetinfo_attrs)

    xml_bytes = ET.tostring(root, encoding="unicode", xml_declaration=True).encode("utf-8")

    # Wrap in zip
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("meet.lef", xml_bytes)
    return buf.getvalue()
