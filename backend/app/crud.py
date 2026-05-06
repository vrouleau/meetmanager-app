"""CRUD operations."""
from sqlalchemy.orm import Session
from . import models, schemas


# --- Club ---
def get_clubs(db: Session):
    return db.query(models.Club).order_by(models.Club.name).all()

def get_club(db: Session, club_id: int):
    return db.query(models.Club).get(club_id)

def create_club(db: Session, data: schemas.ClubCreate):
    obj = models.Club(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

def update_club(db: Session, club_id: int, data: schemas.ClubCreate):
    obj = db.query(models.Club).get(club_id)
    if not obj: return None
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return obj

def delete_club(db: Session, club_id: int):
    obj = db.query(models.Club).get(club_id)
    if obj: db.delete(obj); db.commit()
    return obj


# --- Athlete ---
def get_athletes(db: Session, club_id: int | None = None):
    q = db.query(models.Athlete)
    if club_id: q = q.filter(models.Athlete.club_id == club_id)
    return q.order_by(models.Athlete.last_name, models.Athlete.first_name).all()

def get_athlete(db: Session, athlete_id: int):
    return db.query(models.Athlete).get(athlete_id)

def create_athlete(db: Session, data: schemas.AthleteCreate):
    obj = models.Athlete(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

def update_athlete(db: Session, athlete_id: int, data: schemas.AthleteCreate):
    obj = db.query(models.Athlete).get(athlete_id)
    if not obj: return None
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return obj

def delete_athlete(db: Session, athlete_id: int):
    obj = db.query(models.Athlete).get(athlete_id)
    if obj: db.delete(obj); db.commit()
    return obj


# --- Meet ---
def get_meets(db: Session):
    return db.query(models.Meet).order_by(models.Meet.date_start.desc()).all()

def get_meet(db: Session, meet_id: int):
    return db.query(models.Meet).get(meet_id)

def create_meet(db: Session, data: schemas.MeetCreate):
    obj = models.Meet(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj


# --- Event ---
def get_events(db: Session, meet_id: int):
    return db.query(models.Event).filter(models.Event.meet_id == meet_id).all()

def create_event(db: Session, data: schemas.EventCreate):
    obj = models.Event(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj


# --- Registration ---
def get_registrations(db: Session, meet_id: int | None = None,
                      athlete_id: int | None = None):
    q = db.query(models.Registration)
    if meet_id:
        q = q.join(models.Event).filter(models.Event.meet_id == meet_id)
    if athlete_id:
        q = q.filter(models.Registration.athlete_id == athlete_id)
    return q.all()

def create_registration(db: Session, data: schemas.RegistrationCreate):
    obj = models.Registration(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

def delete_registration(db: Session, reg_id: int):
    obj = db.query(models.Registration).get(reg_id)
    if obj: db.delete(obj); db.commit()
    return obj


# --- Relay ---
def create_relay_team(db: Session, data: schemas.RelayTeamCreate):
    team = models.RelayTeam(registration_id=data.registration_id)
    db.add(team); db.flush()
    for m in data.members:
        db.add(models.RelayMember(team_id=team.id, athlete_id=m.athlete_id,
                                   position=m.position))
    db.commit(); db.refresh(team)
    return team
