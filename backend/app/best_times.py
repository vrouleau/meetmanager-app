"""Parse a Lenex results .lxf and populate best times."""
from __future__ import annotations

import re
import zipfile
from datetime import date as _date
from io import BytesIO
from xml.etree import ElementTree as ET

import json as _json

from sqlalchemy.orm import Session
from .models import AppConfig, Athlete, BestTime, Club, Gender


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
    ath = Athlete(first_name=first, last_name=last, gender=Gender.M, club_id=club.id, license=license)
    db.add(ath)
    db.flush()
    return ath


def _upsert_best_time(db: Session, athlete_id: int, style_uid: int,
                      time_ms: int, course: str, source: str,
                      recorded_on: _date | None = None) -> bool:
    """Upsert a BT row, only overwriting if the new time is faster.
    Returns True when a row was inserted or improved.
    recorded_on is synced to the sibling course row so both LCM/SCM share one date."""
    existing = db.query(BestTime).filter(
        BestTime.athlete_id == athlete_id,
        BestTime.style_uid == style_uid,
        BestTime.course == course,
    ).first()
    if existing:
        if time_ms < existing.time_ms:
            existing.time_ms = time_ms
            existing.source = source
            if recorded_on is not None:
                existing.recorded_on = recorded_on
            improved = True
        else:
            improved = False
    else:
        db.add(BestTime(
            athlete_id=athlete_id,
            style_uid=style_uid,
            time_ms=time_ms,
            course=course,
            source=source,
            recorded_on=recorded_on,
        ))
        improved = True

    # Sync recorded_on to the sibling course row so LCM and SCM share one date
    if recorded_on is not None:
        sibling_course = "SCM" if course == "LCM" else "LCM"
        sibling = db.query(BestTime).filter(
            BestTime.athlete_id == athlete_id,
            BestTime.style_uid == style_uid,
            BestTime.course == sibling_course,
        ).first()
        if sibling:
            sibling.recorded_on = recorded_on

    return improved


def load_best_times(db: Session, file_bytes: bytes, source: str = "") -> dict:
    """Parse results .lxf and upsert best times. Returns counts."""
    with zipfile.ZipFile(BytesIO(file_bytes)) as z:
        lef_name = [n for n in z.namelist() if n.endswith(".lef")][0]
        xml_bytes = z.read(lef_name)

    root = ET.fromstring(xml_bytes)

    # Get course and date from MEET element
    meet_el = root.find(".//MEET")
    course = meet_el.get("course", "LCM") if meet_el is not None else "LCM"
    if course not in ("LCM", "SCM"):
        course = "LCM"  # treat SCY etc. as LCM
    recorded_on: _date | None = None
    if meet_el is not None:
        for date_attr in ("startdate", "date"):
            raw = meet_el.get(date_attr, "")
            if raw:
                try:
                    recorded_on = _date.fromisoformat(raw[:10])
                except ValueError:
                    pass
                if recorded_on:
                    break

    # Build eventid -> style_uid map and uid -> name from the Lenex events
    event_style: dict[str, int] = {}
    style_names: dict[int, str] = {}
    for event_el in root.iter("EVENT"):
        eid = event_el.get("eventid", "")
        for ss in event_el.iter("SWIMSTYLE"):
            uid_raw = ss.get("swimstyleid") or ss.get("stroke", "")
            try:
                uid_int = int(uid_raw)
            except (ValueError, TypeError):
                continue
            event_style[eid] = uid_int
            name = ss.get("name", "")
            if name and uid_int not in style_names:
                style_names[uid_int] = name

    updated = 0
    skipped = 0
    athletes_created = 0
    # Map Lenex athleteid -> DB Athlete, used later to attribute relay times.
    athlete_by_lenex_id: dict[str, Athlete] = {}

    for club_el in root.iter("CLUB"):
        club_name = club_el.get("name", "")
        club = db.query(Club).filter(Club.name == club_name).first()
        for ath_el in club_el.iter("ATHLETE"):
            first = ath_el.get("firstname", "")
            last = ath_el.get("lastname", "")
            license = ath_el.get("license", "")
            gender_str = ath_el.get("gender", "M")
            bd_str = ath_el.get("birthdate", "")
            lenex_aid = ath_el.get("athleteid", "")

            athlete = _find_or_create_athlete(db, first, last, license, club)
            if not athlete:
                skipped += 1
                continue
            if lenex_aid:
                athlete_by_lenex_id[lenex_aid] = athlete
            # Update gender/birthdate if newly created
            if athlete.id is None or (not athlete.birthdate and bd_str):
                athlete.gender = Gender.F if gender_str == "F" else Gender.M
                if bd_str:
                    try:
                        athlete.birthdate = _date.fromisoformat(bd_str)
                    except ValueError:
                        pass
                athletes_created += 1

            # Collect best candidate times per (event, course) pair.
            # entrycourse on individual ENTRY elements overrides the meet-level course
            # so that a multi-course export/backup round-trips correctly.
            event_times: dict[tuple[str, str], list[int]] = {}
            for entry_el in ath_el.iter("ENTRY"):
                eid = entry_el.get("eventid", "")
                t = _lenex_time_to_ms(entry_el.get("entrytime", ""))
                if t and eid:
                    ec = entry_el.get("entrycourse", "") or course
                    if ec not in ("LCM", "SCM"):
                        ec = course
                    event_times.setdefault((eid, ec), []).append(t)
            for result_el in ath_el.iter("RESULT"):
                eid = result_el.get("eventid", "")
                t = _lenex_time_to_ms(result_el.get("swimtime", ""))
                if t and eid:
                    event_times.setdefault((eid, course), []).append(t)

            for (eid, ev_course), times in event_times.items():
                style_uid = event_style.get(eid)
                if not style_uid:
                    continue
                if _upsert_best_time(db, athlete.id, style_uid,
                                     min(times), ev_course, source, recorded_on):
                    updated += 1

    # Relay BT: each member of a team gets the team time recorded against the
    # relay's style_uid, mirroring how individual times update each athlete's BT.
    for relay_el in root.iter("RELAY"):
        # The roster (RELAYPOSITIONS) is shared across all entries/results
        # of a given <RELAY>. SPLASH only writes it on the first one and
        # omits it from siblings, so fall back to the first list we find.
        roster: list[Athlete] = []
        for pos_el in relay_el.iter("RELAYPOSITION"):
            ath = athlete_by_lenex_id.get(pos_el.get("athleteid", ""))
            if ath and ath not in roster:
                roster.append(ath)
        if not roster:
            continue

        relay_event_times: dict[str, list[int]] = {}
        for entry_el in relay_el.iter("ENTRY"):
            eid = entry_el.get("eventid", "")
            t = _lenex_time_to_ms(entry_el.get("entrytime", ""))
            if t and eid:
                relay_event_times.setdefault(eid, []).append(t)
        for result_el in relay_el.iter("RESULT"):
            eid = result_el.get("eventid", "")
            t = _lenex_time_to_ms(result_el.get("swimtime", ""))
            if t and eid:
                relay_event_times.setdefault(eid, []).append(t)

        for eid, times in relay_event_times.items():
            style_uid = event_style.get(eid)
            if not style_uid:
                continue
            best = min(times)
            for ath in roster:
                if _upsert_best_time(db, ath.id, style_uid, best, course, source, recorded_on):
                    updated += 1

    # Persist style uid→name so the Data Management page can show names even without a meet file.
    if style_names:
        cfg = db.query(AppConfig).get("style_names_json")
        existing: dict[int, str] = _json.loads(cfg.value) if cfg else {}
        # Convert keys to int for merge; new names win if uid not already known
        merged = {int(k): v for k, v in existing.items()}
        for uid, name in style_names.items():
            if uid not in merged:
                merged[uid] = name
        payload = _json.dumps({str(k): v for k, v in merged.items()})
        if cfg:
            cfg.value = payload
        else:
            db.add(AppConfig(key="style_names_json", value=payload))

    db.commit()
    return {"times_updated": updated, "athletes_skipped": skipped, "athletes_created": athletes_created}
