"""Read event structure from template.mdb using access_parser."""
from __future__ import annotations

import os
from access_parser import AccessParser


def read_template_structure() -> dict:
    """Parse the template MDB and return sessions, styles, events, agegroups."""
    mdb_path = os.environ.get("TEMPLATE_MDB", "/app/template.mdb")
    db = AccessParser(mdb_path)

    # SWIMSTYLE
    st = db.parse_table("SWIMSTYLE")
    styles = {}
    for i in range(len(st["SWIMSTYLEID"])):
        uid = st["UNIQUEID"][i]
        if uid is None:
            continue
        styles[int(st["SWIMSTYLEID"][i])] = {
            "uid": int(uid),
            "name": st["NAME"][i] or None,
            "distance": int(st["DISTANCE"][i]) if st["DISTANCE"][i] else 0,
            "relay_count": int(st["RELAYCOUNT"][i]) if st["RELAYCOUNT"][i] else 1,
            "stroke": int(st["STROKE"][i]) if st["STROKE"][i] else 0,
        }

    # SWIMSESSION
    ss = db.parse_table("SWIMSESSION")
    sessions = []
    for i in range(len(ss["SWIMSESSIONID"])):
        sessions.append({
            "id": int(ss["SWIMSESSIONID"][i]),
            "number": int(ss["SESSIONNUMBER"][i]) if ss["SESSIONNUMBER"][i] else 1,
            "name": ss["NAME"][i] or f"Session {ss['SESSIONNUMBER'][i]}",
            "lane_min": int(ss["LANEMIN"][i]) if ss["LANEMIN"][i] else 1,
            "lane_max": int(ss["LANEMAX"][i]) if ss["LANEMAX"][i] else 8,
        })

    # AGEGROUP
    ag = db.parse_table("AGEGROUP")
    agegroups = {}
    for i in range(len(ag["AGEGROUPID"])):
        agegroups[int(ag["AGEGROUPID"][i])] = {
            "id": int(ag["AGEGROUPID"][i]),
            "event_id": int(ag["SWIMEVENTID"][i]) if ag["SWIMEVENTID"][i] else None,
            "amin": int(ag["AGEMIN"][i]) if ag["AGEMIN"][i] is not None else None,
            "amax": int(ag["AGEMAX"][i]) if ag["AGEMAX"][i] is not None else None,
            "gender": int(ag["GENDER"][i]) if ag["GENDER"][i] is not None else 0,
        }

    # SWIMEVENT
    ev = db.parse_table("SWIMEVENT")
    events = []
    for i in range(len(ev["SWIMEVENTID"])):
        eid = ev["SWIMEVENTID"][i]
        sid = ev["SWIMSTYLEID"][i]
        if eid is None or sid is None:
            continue
        eid = int(eid)
        sid = int(sid)
        style = styles.get(sid)
        if style is None:
            continue
        gender_int = int(ev["GENDER"][i]) if ev["GENDER"][i] is not None else 0
        round_int = int(ev["ROUND"][i]) if ev["ROUND"][i] is not None else 0
        masters = ev["MASTERS"][i] == "T" if ev["MASTERS"][i] else False
        event_number = int(ev["EVENTNUMBER"][i]) if ev["EVENTNUMBER"][i] else None
        session_id = int(ev["SWIMSESSIONID"][i]) if ev["SWIMSESSIONID"][i] else None

        # Collect agegroups for this event
        event_ags = [a for a in agegroups.values() if a["event_id"] == eid]

        # Determine age_code from agegroups
        if masters:
            age_code = "MASTERS"
        elif any(a["amin"] == 15 and a["amax"] == 18 for a in event_ags):
            age_code = "1518"
        elif any(a["amin"] == 19 for a in event_ags):
            age_code = "OPEN"
        else:
            age_code = "OPEN"

        events.append({
            "event_id": eid,
            "event_number": event_number,
            "style_uid": style["uid"],
            "style_name": style["name"] or f"UID {style['uid']}",
            "distance": style["distance"],
            "relay_count": style["relay_count"],
            "gender": gender_int,  # 0=all, 1=M, 2=F, 3=mixed
            "round": round_int,
            "masters": masters,
            "age_code": age_code,
            "session_id": session_id,
            "agegroups": event_ags,
        })

    return {
        "sessions": sessions,
        "events": events,
        "styles": styles,
    }


def read_template_structure_from_bytes(mdb_bytes: bytes) -> dict:
    """Same as read_template_structure but from bytes (uploaded file)."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".mdb", delete=False) as f:
        f.write(mdb_bytes)
        tmp_path = f.name
    try:
        old_env = os.environ.get("TEMPLATE_MDB")
        os.environ["TEMPLATE_MDB"] = tmp_path
        result = read_template_structure()
        if old_env:
            os.environ["TEMPLATE_MDB"] = old_env
        return result
    finally:
        os.unlink(tmp_path)
