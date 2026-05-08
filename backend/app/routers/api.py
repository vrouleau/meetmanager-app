"""API endpoints."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Club, Athlete, Event, Registration, BestTime, AppConfig, Gender
from ..seed import seed_from_lxf
from ..best_times import load_best_times
from ..export import generate_lxf

router = APIRouter(prefix="/api")

MEET_STORAGE = Path(os.environ.get("MEET_STORAGE", "/app/data/meet.lxf"))
ADMIN_PIN = os.environ.get("ADMIN_PIN", "000000")


def get_club_from_pin(db: Session, pin: str) -> Club | None:
    """Validate PIN and return club (or None for admin)."""
    if pin == ADMIN_PIN:
        return None  # admin — no club filter
    return db.query(Club).filter(Club.pin == pin).first()


def require_pin(request, db: Session):
    """Extract pin from header, validate. Returns (club_id or None for admin)."""
    pin = request.headers.get("X-Club-Pin", "")
    if not pin:
        raise HTTPException(401, "PIN required")
    if pin == ADMIN_PIN:
        return None  # admin
    club = db.query(Club).filter(Club.pin == pin).first()
    if not club:
        raise HTTPException(401, "Invalid PIN")
    return club.id


@router.get("/auth")
def auth(pin: str, db: Session = Depends(get_db)):
    """Validate PIN, return club info."""
    if pin == ADMIN_PIN:
        return {"role": "admin", "club_id": None, "club_name": "Admin"}
    club = db.query(Club).filter(Club.pin == pin).first()
    if not club:
        raise HTTPException(401, "Invalid PIN")
    return {"role": "coach", "club_id": club.id, "club_name": club.name}


@router.post("/upload/meet")
async def upload_meet(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload meet .lxf — sets event structure."""
    content = await file.read()
    from ..meet_parser import parse_meet_lxf
    try:
        meet = parse_meet_lxf(content)
    except Exception as e:
        raise HTTPException(400, f"Invalid meet .lxf: {e}")

    MEET_STORAGE.parent.mkdir(parents=True, exist_ok=True)
    MEET_STORAGE.write_bytes(content)

    # Reload events
    db.query(Event).delete()
    from ..events import _load_from_parsed
    count = _load_from_parsed(db, meet)

    # Track metadata
    for key, val in [("meet_filename", file.filename or "meet.lxf"),
                     ("meet_uploaded_at", datetime.utcnow().isoformat())]:
        cfg = db.query(AppConfig).get(key)
        if cfg:
            cfg.value = val
        else:
            db.add(AppConfig(key=key, value=val))
    db.commit()
    return {"events_loaded": count, "filename": file.filename}


@router.get("/meet-info")
def meet_info(db: Session = Depends(get_db)):
    filename = db.query(AppConfig).get("meet_filename")
    uploaded = db.query(AppConfig).get("meet_uploaded_at")
    return {
        "filename": filename.value if filename else None,
        "uploaded_at": uploaded.value if uploaded else None,
        "events": db.query(Event).count(),
    }

@router.get("/clubs")
def list_clubs(db: Session = Depends(get_db)):
    clubs = db.query(Club).order_by(Club.name).all()
    return [{"id": c.id, "name": c.name, "code": c.code,
             "pin": c.pin, "athlete_count": len(c.athletes)} for c in clubs]


@router.post("/clubs")
def create_club(data: dict, db: Session = Depends(get_db)):
    import random
    pin = data.get("pin") or f"{random.randint(100000, 999999)}"
    club = Club(name=data["name"], code=data.get("code", ""), nation=data.get("nation", "CAN"), pin=pin)
    db.add(club)
    db.commit()
    return {"id": club.id, "pin": club.pin}


@router.delete("/clubs/{club_id}")
def delete_club(club_id: int, db: Session = Depends(get_db)):
    club = db.query(Club).get(club_id)
    if not club:
        raise HTTPException(404)
    if club.athletes:
        raise HTTPException(400, "Club has athletes — remove them first")
    db.delete(club)
    db.commit()
    return {"deleted": True}


@router.get("/athletes")
def list_athletes(club_id: int = None, db: Session = Depends(get_db)):
    q = db.query(Athlete).options(joinedload(Athlete.club))
    if club_id:
        q = q.filter(Athlete.club_id == club_id)
    athletes = q.order_by(Athlete.last_name, Athlete.first_name).all()
    return [{
        "id": a.id, "first_name": a.first_name, "last_name": a.last_name,
        "gender": a.gender.value, "birthdate": str(a.birthdate) if a.birthdate else None,
        "license": a.license, "club": a.club.name,
        "club_id": a.club_id,
    } for a in athletes]


@router.post("/athletes")
def create_athlete(data: dict, db: Session = Depends(get_db)):
    from datetime import date as d
    ath = Athlete(
        first_name=data["first_name"],
        last_name=data["last_name"],
        gender=Gender(data.get("gender", "M")),
        birthdate=d.fromisoformat(data["birthdate"]) if data.get("birthdate") else None,
        license=data.get("license", ""),
        club_id=data["club_id"],
    )
    db.add(ath)
    db.commit()
    return {"id": ath.id}


@router.delete("/athletes/{athlete_id}")
def delete_athlete(athlete_id: int, db: Session = Depends(get_db)):
    athlete = db.query(Athlete).get(athlete_id)
    if not athlete:
        raise HTTPException(404)
    # Delete registrations and best times first
    db.query(Registration).filter(Registration.athlete_id == athlete_id).delete()
    db.query(BestTime).filter(BestTime.athlete_id == athlete_id).delete()
    db.delete(athlete)
    db.commit()
    return {"deleted": True}


@router.get("/events")
def list_events(db: Session = Depends(get_db)):
    events = db.query(Event).order_by(Event.event_number).all()
    return [{
        "id": e.id, "style_uid": e.style_uid, "style_name": e.style_name,
        "distance": e.distance, "relay_count": e.relay_count,
        "gender": e.gender, "event_number": e.event_number,
        "round": e.round, "masters": e.masters,
    } for e in events]


@router.get("/athletes/{athlete_id}/registration")
def get_registration(athlete_id: int, db: Session = Depends(get_db)):
    athlete = db.query(Athlete).get(athlete_id)
    if not athlete:
        raise HTTPException(404, "Athlete not found")

    regs = db.query(Registration).filter(
        Registration.athlete_id == athlete_id
    ).all()
    reg_map = {r.event_id: r for r in regs}

    best = db.query(BestTime).filter(
        BestTime.athlete_id == athlete_id
    ).all()
    best_map = {b.style_uid: b.time_ms for b in best}

    events = db.query(Event).order_by(Event.event_number).all()

    # Filter events by athlete gender (individual only)
    ath_gender_int = 1 if athlete.gender.value == "M" else 2

    # Build style groups with fixed categories: 15-18, Open, Masters
    # Each style has a prelim event (non-masters) and optionally a masters event
    from collections import defaultdict
    styles: dict[int, dict] = {}
    event_lookup: dict[tuple, int] = {}  # (style_uid, masters) -> event_id

    for ev in events:
        if ev.round == 9:
            continue
        if not ev.masters and ev.round != 2:
            continue
        if ev.relay_count == 1 and ev.gender != ath_gender_int:
            continue
        # For relays (gender=3/mixed), include all
        if (ev.style_uid, ev.masters) not in event_lookup:
            event_lookup[(ev.style_uid, ev.masters)] = ev.id

        if ev.style_uid not in styles:
            styles[ev.style_uid] = {
                "style_uid": ev.style_uid,
                "style_name": ev.style_name,
                "distance": ev.distance,
                "relay_count": ev.relay_count,
                "categories": [],
            }

    # Build categories for each style
    for uid, style in styles.items():
        prelim_eid = event_lookup.get((uid, False))
        masters_eid = event_lookup.get((uid, True))

        # Fixed categories: 15-18, Open (both use prelim event), Masters (uses masters event)
        if prelim_eid:
            for age_code in ("15-18", "Open"):
                reg = next((r for r in regs if r.event_id == prelim_eid and r.age_code == age_code), None)
                style["categories"].append({
                    "event_id": prelim_eid,
                    "age_code": age_code,
                    "registered": reg is not None,
                    "registration_id": reg.id if reg else None,
                    "entry_time_ms": reg.entry_time_ms if reg else None,
                })
        if masters_eid:
            reg = next((r for r in regs if r.event_id == masters_eid and r.age_code == "Masters"), None)
            style["categories"].append({
                "event_id": masters_eid,
                "age_code": "Masters",
                "registered": reg is not None,
                "registration_id": reg.id if reg else None,
                "entry_time_ms": reg.entry_time_ms if reg else None,
            })

    individual_events = [s for s in styles.values() if s["relay_count"] == 1]
    relay_events = [s for s in styles.values() if s["relay_count"] > 1]

    # Add best time to each style group
    for s in individual_events + relay_events:
        s["best_time_ms"] = best_map.get(s["style_uid"])

    # Club athletes for relay teammate selection
    club_athletes = db.query(Athlete).filter(
        Athlete.club_id == athlete.club_id,
        Athlete.id != athlete_id,
    ).order_by(Athlete.last_name).all()

    # Determine suggested age_code from athlete DOB
    suggested_age_code = "Open"
    if athlete.birthdate:
        from datetime import date as d
        age = d(2026, 12, 31).year - athlete.birthdate.year
        if 15 <= age <= 18:
            suggested_age_code = "15-18"
        elif age >= 25:
            suggested_age_code = "Masters"

    return {
        "athlete": {
            "id": athlete.id, "first_name": athlete.first_name,
            "last_name": athlete.last_name, "gender": athlete.gender.value,
            "birthdate": str(athlete.birthdate) if athlete.birthdate else "",
            "license": athlete.license or "",
            "club": athlete.club.name, "club_id": athlete.club_id,
        },
        "suggested_age_code": suggested_age_code,
        "individual_events": individual_events,
        "relay_events": relay_events,
        "club_athletes": [{"id": a.id, "name": f"{a.last_name}, {a.first_name}"}
                          for a in club_athletes],
    }


@router.put("/athletes/{athlete_id}")
def update_athlete(athlete_id: int, data: dict, db: Session = Depends(get_db)):
    athlete = db.query(Athlete).get(athlete_id)
    if not athlete:
        raise HTTPException(404)
    if "first_name" in data: athlete.first_name = data["first_name"]
    if "last_name" in data: athlete.last_name = data["last_name"]
    if "gender" in data: athlete.gender = Gender(data["gender"])
    if "birthdate" in data:
        from datetime import date as d
        athlete.birthdate = d.fromisoformat(data["birthdate"]) if data["birthdate"] else None
    if "license" in data: athlete.license = data["license"]
    db.commit()
    return {"ok": True}


@router.post("/registrations")
def create_registration(data: dict, db: Session = Depends(get_db)):
    athlete_id = data["athlete_id"]
    event_id = data["event_id"]
    age_code = data.get("age_code", "OPEN")
    entry_time_ms = data.get("entry_time_ms")

    existing = db.query(Registration).filter(
        Registration.athlete_id == athlete_id,
        Registration.event_id == event_id,
        Registration.age_code == age_code,
    ).first()

    if existing:
        existing.entry_time_ms = entry_time_ms
        db.commit()
        return {"id": existing.id, "updated": True}

    reg = Registration(
        athlete_id=athlete_id, event_id=event_id,
        age_code=age_code, entry_time_ms=entry_time_ms,
    )
    db.add(reg)
    db.commit()
    return {"id": reg.id, "updated": False}


@router.delete("/registrations/{reg_id}")
def delete_registration(reg_id: int, db: Session = Depends(get_db)):
    reg = db.query(Registration).get(reg_id)
    if not reg:
        raise HTTPException(404)
    db.delete(reg)
    db.commit()
    return {"deleted": True}


@router.post("/upload/entries")
async def upload_entries(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload entries .lxf to seed clubs + athletes."""
    content = await file.read()
    result = seed_from_lxf(db, content)
    return result


@router.post("/upload/results")
async def upload_results(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload results .lxf to populate best times."""
    content = await file.read()
    result = load_best_times(db, content, source=file.filename or "upload")
    return result


@router.get("/status")
def status(db: Session = Depends(get_db)):
    return {
        "clubs": db.query(Club).count(),
        "athletes": db.query(Athlete).count(),
        "events": db.query(Event).count(),
        "registrations": db.query(Registration).count(),
        "best_times": db.query(BestTime).count(),
    }


@router.delete("/registrations")
def flush_registrations(db: Session = Depends(get_db)):
    """Delete all registrations (keeps best times)."""
    count = db.query(Registration).delete()
    db.commit()
    return {"deleted": count}


@router.post("/clubs/regenerate-pins")
def regenerate_pins(db: Session = Depends(get_db)):
    """Regenerate all club PINs."""
    import random
    clubs = db.query(Club).all()
    for club in clubs:
        club.pin = f"{random.randint(100000, 999999)}"
    db.commit()
    return {"regenerated": len(clubs)}


@router.get("/export")
def export_lenex(db: Session = Depends(get_db)):
    """Generate and download Lenex .lxf."""
    from fastapi.responses import Response
    lxf_bytes = generate_lxf(db)
    return Response(
        content=lxf_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=inscriptions.lxf"},
    )
