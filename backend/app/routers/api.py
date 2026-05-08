"""API endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Club, Athlete, Event, Registration, BestTime
from ..seed import seed_from_lxf
from ..best_times import load_best_times
from ..export import generate_lxf

router = APIRouter(prefix="/api")


@router.get("/clubs")
def list_clubs(db: Session = Depends(get_db)):
    clubs = db.query(Club).order_by(Club.name).all()
    return [{"id": c.id, "name": c.name, "code": c.code,
             "athlete_count": len(c.athletes)} for c in clubs]


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
    entries = []
    for ev in events:
        reg = reg_map.get(ev.id)
        entries.append({
            "event_id": ev.id,
            "style_uid": ev.style_uid,
            "style_name": ev.style_name,
            "distance": ev.distance,
            "event_number": ev.event_number,
            "gender": ev.gender,
            "masters": ev.masters,
            "relay_count": ev.relay_count,
            "registered": reg is not None,
            "registration_id": reg.id if reg else None,
            "entry_time_ms": reg.entry_time_ms if reg else None,
            "best_time_ms": best_map.get(ev.style_uid),
        })

    return {
        "athlete": {
            "id": athlete.id, "first_name": athlete.first_name,
            "last_name": athlete.last_name, "gender": athlete.gender.value,
            "club": athlete.club.name,
        },
        "entries": entries,
    }


@router.post("/registrations")
def create_registration(data: dict, db: Session = Depends(get_db)):
    athlete_id = data["athlete_id"]
    event_id = data["event_id"]
    entry_time_ms = data.get("entry_time_ms")

    existing = db.query(Registration).filter(
        Registration.athlete_id == athlete_id,
        Registration.event_id == event_id,
    ).first()

    if existing:
        existing.entry_time_ms = entry_time_ms
        db.commit()
        return {"id": existing.id, "updated": True}

    reg = Registration(
        athlete_id=athlete_id, event_id=event_id,
        entry_time_ms=entry_time_ms,
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
