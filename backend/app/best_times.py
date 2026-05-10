"""Parse a Lenex results .lxf and populate best times."""
from __future__ import annotations

import re
import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session
from .models import Athlete, BestTime, Club, Gender


def _lenex_time_to_ms(t: str) -> int | None:
    """Convert Lenex time 'HH:MM:SS.hh' or 'MM:SS.hh' to ms."""
    if not t or t == "NT":
        return None
    m = re.match(r"(\d+):(\d+):(\d+)\.(\d+)", t)
    if m:
        return (int(m.group(1)) * 3600000 + int(m.group(2)) * 60000
                + int(m.group(3)) * 1000 + int(m.group(4)) * 10)
    m = re.match(r"(\d+):(\d+)\.(\d+)", t)
    if m:
        return (int(m.group(1)) * 60000 + int(m.group(2)) * 1000
                + int(m.group(3)) * 10)
    m = re.match(r"(\d+)\.(\d+)", t)
    if m:
        return int(m.group(1)) * 1000 + int(m.group(2)) * 10
    return None


def _find_or_create_athlete(db: Session, first: str, last: str, license: str, club=None) -> Athlete | None:
    """Match athlete by license first, then name. Create if not found and club provided."""
    if license:
        ath = db.query(Athlete).filter(Athlete.license == license).first()
        if ath:
            return ath
    ath = db.query(Athlete).filter(
        Athlete.first_name == first, Athlete.last_name == last
    ).first()
    if ath:
        return ath
    if not club:
        return None
    from .models import Gender
    ath = Athlete(first_name=first, last_name=last, gender=Gender.M, club_id=club.id, license=license)
    db.add(ath)
    db.flush()
    return ath


def load_best_times(db: Session, file_bytes: bytes, source: str = "") -> dict:
    """Parse results .lxf and upsert best times. Returns counts."""
    with zipfile.ZipFile(BytesIO(file_bytes)) as z:
        lef_name = [n for n in z.namelist() if n.endswith(".lef")][0]
        xml_bytes = z.read(lef_name)

    root = ET.fromstring(xml_bytes)

    # Get course from MEET element
    meet_el = root.find(".//MEET")
    course = meet_el.get("course", "LCM") if meet_el is not None else "LCM"
    if course not in ("LCM", "SCM"):
        course = "LCM"  # treat SCY etc. as LCM

    # Build eventid -> style_uid map from the Lenex events
    event_style: dict[str, int] = {}
    for event_el in root.iter("EVENT"):
        eid = event_el.get("eventid", "")
        for ss in event_el.iter("SWIMSTYLE"):
            uid = ss.get("swimstyleid") or ss.get("stroke", "")
            try:
                event_style[eid] = int(uid)
            except (ValueError, TypeError):
                pass

    updated = 0
    skipped = 0
    athletes_created = 0

    for club_el in root.iter("CLUB"):
        club_name = club_el.get("name", "")
        club = db.query(Club).filter(Club.name == club_name).first()
        for ath_el in club_el.iter("ATHLETE"):
            first = ath_el.get("firstname", "")
            last = ath_el.get("lastname", "")
            license = ath_el.get("license", "")
            gender_str = ath_el.get("gender", "M")
            bd_str = ath_el.get("birthdate", "")

            athlete = _find_or_create_athlete(db, first, last, license, club)
            if not athlete:
                skipped += 1
                continue
            # Update gender/birthdate if newly created
            if athlete.id is None or (not athlete.birthdate and bd_str):
                athlete.gender = Gender.F if gender_str == "F" else Gender.M
                if bd_str:
                    try:
                        from datetime import date as _date
                        athlete.birthdate = _date.fromisoformat(bd_str)
                    except ValueError:
                        pass
                athletes_created += 1

            # Collect best candidate times per event: entry time and result time
            event_times: dict[str, list[int]] = {}
            for entry_el in ath_el.iter("ENTRY"):
                eid = entry_el.get("eventid", "")
                t = _lenex_time_to_ms(entry_el.get("entrytime", ""))
                if t and eid:
                    event_times.setdefault(eid, []).append(t)
            for result_el in ath_el.iter("RESULT"):
                eid = result_el.get("eventid", "")
                t = _lenex_time_to_ms(result_el.get("swimtime", ""))
                if t and eid:
                    event_times.setdefault(eid, []).append(t)

            for eid, times in event_times.items():
                style_uid = event_style.get(eid)
                if not style_uid:
                    continue
                best_candidate = min(times)

                existing = db.query(BestTime).filter(
                    BestTime.athlete_id == athlete.id,
                    BestTime.style_uid == style_uid,
                    BestTime.course == course,
                ).first()

                if existing:
                    if best_candidate < existing.time_ms:
                        existing.time_ms = best_candidate
                        existing.source = source
                        updated += 1
                else:
                    db.add(BestTime(
                        athlete_id=athlete.id,
                        style_uid=style_uid,
                        time_ms=best_candidate,
                        course=course,
                        source=source,
                    ))
                    updated += 1

    db.commit()
    return {"times_updated": updated, "athletes_skipped": skipped, "athletes_created": athletes_created}
