"""Parse a Lenex results .lxf and populate best times."""
from __future__ import annotations

import re
import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session
from .models import Athlete, BestTime


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


def _find_athlete(db: Session, first: str, last: str, license: str) -> Athlete | None:
    """Match athlete by license first, then name."""
    if license:
        ath = db.query(Athlete).filter(Athlete.license == license).first()
        if ath:
            return ath
    return db.query(Athlete).filter(
        Athlete.first_name == first, Athlete.last_name == last
    ).first()


def load_best_times(db: Session, file_bytes: bytes, source: str = "") -> dict:
    """Parse results .lxf and upsert best times. Returns counts."""
    with zipfile.ZipFile(BytesIO(file_bytes)) as z:
        lef_name = [n for n in z.namelist() if n.endswith(".lef")][0]
        xml_bytes = z.read(lef_name)

    root = ET.fromstring(xml_bytes)

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

    for club_el in root.iter("CLUB"):
        for ath_el in club_el.iter("ATHLETE"):
            first = ath_el.get("firstname", "")
            last = ath_el.get("lastname", "")
            license = ath_el.get("license", "")

            athlete = _find_athlete(db, first, last, license)
            if not athlete:
                skipped += 1
                continue

            for result_el in ath_el.iter("RESULT"):
                eid = result_el.get("eventid", "")
                time_str = result_el.get("swimtime", "")
                time_ms = _lenex_time_to_ms(time_str)
                style_uid = event_style.get(eid)

                if not time_ms or not style_uid:
                    continue

                existing = db.query(BestTime).filter(
                    BestTime.athlete_id == athlete.id,
                    BestTime.style_uid == style_uid,
                ).first()

                if existing:
                    if time_ms < existing.time_ms:
                        existing.time_ms = time_ms
                        existing.source = source
                        updated += 1
                else:
                    db.add(BestTime(
                        athlete_id=athlete.id,
                        style_uid=style_uid,
                        time_ms=time_ms,
                        source=source,
                    ))
                    updated += 1

    db.commit()
    return {"times_updated": updated, "athletes_skipped": skipped}
