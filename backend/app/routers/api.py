"""API routers."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from .. import crud, schemas
from ..database import get_db
from ..template_reader import read_template_structure

router = APIRouter()


# --- Template ---
@router.get("/template/events")
def get_template_events():
    """Return the event structure from the template MDB."""
    data = read_template_structure()
    return data


# --- Clubs ---
@router.get("/clubs", response_model=list[schemas.ClubOut])
def list_clubs(db: Session = Depends(get_db)):
    return crud.get_clubs(db)

@router.post("/clubs", response_model=schemas.ClubOut, status_code=201)
def create_club(data: schemas.ClubCreate, db: Session = Depends(get_db)):
    return crud.create_club(db, data)

@router.put("/clubs/{club_id}", response_model=schemas.ClubOut)
def update_club(club_id: int, data: schemas.ClubCreate, db: Session = Depends(get_db)):
    obj = crud.update_club(db, club_id, data)
    if not obj: raise HTTPException(404)
    return obj

@router.delete("/clubs/{club_id}", status_code=204)
def delete_club(club_id: int, db: Session = Depends(get_db)):
    crud.delete_club(db, club_id)


# --- Athletes ---
@router.get("/athletes", response_model=list[schemas.AthleteOut])
def list_athletes(club_id: int | None = None, db: Session = Depends(get_db)):
    return crud.get_athletes(db, club_id=club_id)

@router.post("/athletes", response_model=schemas.AthleteOut, status_code=201)
def create_athlete(data: schemas.AthleteCreate, db: Session = Depends(get_db)):
    return crud.create_athlete(db, data)

@router.put("/athletes/{athlete_id}", response_model=schemas.AthleteOut)
def update_athlete(athlete_id: int, data: schemas.AthleteCreate, db: Session = Depends(get_db)):
    obj = crud.update_athlete(db, athlete_id, data)
    if not obj: raise HTTPException(404)
    return obj

@router.delete("/athletes/{athlete_id}", status_code=204)
def delete_athlete(athlete_id: int, db: Session = Depends(get_db)):
    crud.delete_athlete(db, athlete_id)


# --- Meets ---
@router.get("/meets", response_model=list[schemas.MeetOut])
def list_meets(db: Session = Depends(get_db)):
    return crud.get_meets(db)

@router.post("/meets", status_code=201)
async def create_meet(
    name: str = Form(...),
    city: str = Form(""),
    date_start: str = Form(...),
    age_date: str = Form(...),
    course: str = Form("LCM"),
    mdb: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Create a meet and populate events from uploaded MDB."""
    from ..models import Meet as MeetModel, Event as EventModel
    from ..template_reader import read_template_structure_from_bytes
    from datetime import date as date_type

    try:
        meet = MeetModel(
            name=name, city=city,
            date_start=date_type.fromisoformat(date_start),
            age_date=date_type.fromisoformat(age_date),
            course=course,
        )
        db.add(meet); db.flush()

        # Read event structure from uploaded MDB
        mdb_bytes = await mdb.read()
        tmpl = read_template_structure_from_bytes(mdb_bytes)
        gender_map = {0: None, 1: "M", 2: "F", 3: None}
        count = 0
        for ev in tmpl["events"]:
            if ev["round"] not in (1, 2):
                continue
            db.add(EventModel(
                meet_id=meet.id,
                style_name=ev["style_name"] or f"UID {ev['style_uid']}",
                style_uid=ev["style_uid"],
                age_code=ev["age_code"],
                gender=gender_map.get(ev["gender"]),
                is_relay=ev["relay_count"] > 1,
                relay_count=ev["relay_count"],
                distance=ev["distance"],
            ))
            count += 1
        db.commit(); db.refresh(meet)
        return {"id": meet.id, "name": meet.name, "events_created": count}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, detail=str(e))

@router.get("/meets/{meet_id}", response_model=schemas.MeetOut)
def get_meet(meet_id: int, db: Session = Depends(get_db)):
    obj = crud.get_meet(db, meet_id)
    if not obj: raise HTTPException(404)
    return obj


# --- Events ---
@router.get("/meets/{meet_id}/events", response_model=list[schemas.EventOut])
def list_events(meet_id: int, db: Session = Depends(get_db)):
    return crud.get_events(db, meet_id)

@router.post("/events", response_model=schemas.EventOut, status_code=201)
def create_event(data: schemas.EventCreate, db: Session = Depends(get_db)):
    return crud.create_event(db, data)


# --- Registrations ---
@router.get("/registrations", response_model=list[schemas.RegistrationOut])
def list_registrations(meet_id: int | None = None, athlete_id: int | None = None,
                       db: Session = Depends(get_db)):
    return crud.get_registrations(db, meet_id=meet_id, athlete_id=athlete_id)

@router.post("/registrations", response_model=schemas.RegistrationOut, status_code=201)
def create_registration(data: schemas.RegistrationCreate, db: Session = Depends(get_db)):
    return crud.create_registration(db, data)

@router.put("/registrations/{reg_id}", response_model=schemas.RegistrationOut)
def update_registration(reg_id: int, data: schemas.RegistrationCreate, db: Session = Depends(get_db)):
    from ..models import Registration
    obj = db.query(Registration).get(reg_id)
    if not obj: raise HTTPException(404)
    obj.best_time_ms = data.best_time_ms
    db.commit(); db.refresh(obj)
    return obj

@router.delete("/registrations/{reg_id}", status_code=204)
def delete_registration(reg_id: int, db: Session = Depends(get_db)):
    crud.delete_registration(db, reg_id)


# --- Registration helper: events + suggested times for an athlete ---
@router.get("/meets/{meet_id}/register/{athlete_id}")
def get_registration_options(meet_id: int, athlete_id: int, db: Session = Depends(get_db)):
    """Return events for this meet with athlete's best times and current registrations."""
    from ..models import Event, Registration, BestTime, Athlete
    athlete = db.query(Athlete).get(athlete_id)
    if not athlete:
        raise HTTPException(404, "Athlete not found")

    events = db.query(Event).filter(Event.meet_id == meet_id).all()
    best_times = {bt.style_uid: bt.time_ms
                  for bt in db.query(BestTime).filter(BestTime.athlete_id == athlete_id).all()}
    current_regs = {r.event_id: r
                    for r in db.query(Registration).filter(
                        Registration.athlete_id == athlete_id,
                        Registration.event_id.in_([e.id for e in events])
                    ).all()}

    result = []
    for ev in events:
        # Filter by gender compatibility
        if ev.gender and ev.gender != athlete.gender.value:
            continue
        result.append({
            "event_id": ev.id,
            "style_name": ev.style_name,
            "style_uid": ev.style_uid,
            "age_code": ev.age_code,
            "is_relay": ev.is_relay,
            "relay_count": ev.relay_count,
            "suggested_time_ms": best_times.get(ev.style_uid),
            "registered": current_regs.get(ev.id) is not None,
            "registration_id": current_regs[ev.id].id if ev.id in current_regs else None,
            "entered_time_ms": current_regs[ev.id].best_time_ms if ev.id in current_regs else None,
        })

    # Group individual events by style (deduplicate, show age_code as options)
    ind_by_style: dict[int, dict] = {}
    relay_list = []
    for ev in result:
        if ev["is_relay"]:
            relay_list.append(ev)
        else:
            uid = ev["style_uid"]
            if uid not in ind_by_style:
                ind_by_style[uid] = {
                    "style_name": ev["style_name"],
                    "style_uid": uid,
                    "categories": [],
                }
            ind_by_style[uid]["categories"].append({
                "event_id": ev["event_id"],
                "age_code": ev["age_code"],
                "suggested_time_ms": ev["suggested_time_ms"],
                "registered": ev["registered"],
                "registration_id": ev["registration_id"],
                "entered_time_ms": ev["entered_time_ms"],
            })

    # Group relay events by style too
    relay_by_style: dict[int, dict] = {}
    for ev in relay_list:
        uid = ev["style_uid"]
        if uid not in relay_by_style:
            relay_by_style[uid] = {
                "style_name": ev["style_name"],
                "style_uid": uid,
                "relay_count": ev["relay_count"],
                "categories": [],
            }
        relay_by_style[uid]["categories"].append({
            "event_id": ev["event_id"],
            "age_code": ev["age_code"],
            "registered": ev["registered"],
            "registration_id": ev["registration_id"],
        })

    # Get club athletes for relay teammate selection
    club_athletes = [{"id": a.id, "name": f"{a.first_name} {a.last_name}"}
                     for a in db.query(Athlete).filter(
                         Athlete.club_id == athlete.club_id,
                         Athlete.id != athlete_id
                     ).order_by(Athlete.last_name).all()]

    return {
        "athlete": {"id": athlete.id, "name": f"{athlete.first_name} {athlete.last_name}",
                    "gender": athlete.gender.value, "club_id": athlete.club_id},
        "individual_events": list(ind_by_style.values()),
        "relay_events": list(relay_by_style.values()),
        "club_athletes": club_athletes,
    }


# --- Relay Teams ---
@router.post("/relay-teams", response_model=schemas.RelayTeamOut, status_code=201)
def create_relay_team(data: schemas.RelayTeamCreate, db: Session = Depends(get_db)):
    return crud.create_relay_team(db, data)


# --- Export ---
@router.get("/meets/{meet_id}/export")
def export_meet(meet_id: int, format: str = "lenex", db: Session = Depends(get_db)):
    from fastapi.responses import Response
    from ..export import generate_lenex
    if format == "lenex":
        xml = generate_lenex(db, meet_id)
        return Response(content=xml, media_type="application/xml",
                        headers={"Content-Disposition": "attachment; filename=meet.lef"})
    raise HTTPException(400, f"Unknown format: {format}")
