"""API endpoints."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload
from collections import defaultdict
import time as _time

from ..database import get_db
from ..models import Club, Athlete, Event, Registration, BestTime, AppConfig, Gender, SecretLink
from ..seed import seed_from_lxf
from ..best_times import load_best_times
from ..export import generate_lxf

router = APIRouter(prefix="/api")

MEET_STORAGE = Path(os.environ.get("MEET_STORAGE", "/app/data/meet.lxf"))
_DEFAULT_ADMIN_PIN = os.environ.get("ADMIN_PIN", "000000")


def _get_admin_pin(db: Session) -> str:
    cfg = db.query(AppConfig).get("admin_pin")
    return cfg.value if cfg else _DEFAULT_ADMIN_PIN

# Rate limiting: max 5 attempts per IP per 60 seconds
_auth_attempts: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT = 5
_RATE_WINDOW = 60


def _check_rate_limit(ip: str):
    now = _time.time()
    attempts = _auth_attempts[ip]
    # Prune old attempts
    _auth_attempts[ip] = [t for t in attempts if now - t < _RATE_WINDOW]
    if len(_auth_attempts[ip]) >= _RATE_LIMIT:
        raise HTTPException(429, "Too many attempts. Try again later.")
    _auth_attempts[ip].append(now)


def get_club_from_pin(db: Session, pin: str) -> Club | None:
    """Validate PIN and return club (or None for admin)."""
    if pin == _get_admin_pin(db):
        return None  # admin — no club filter
    return db.query(Club).filter(Club.pin == pin).first()


def require_pin(request, db: Session):
    """Extract pin from header, validate. Returns (club_id or None for admin)."""
    pin = request.headers.get("X-Club-Pin", "")
    if not pin:
        raise HTTPException(401, "PIN required")
    if pin == _get_admin_pin(db):
        return None  # admin
    club = db.query(Club).filter(Club.pin == pin).first()
    if not club:
        raise HTTPException(401, "Invalid PIN")
    return club.id


@router.post("/auth")
def auth(data: dict, request: Request, db: Session = Depends(get_db)):
    """Validate PIN, return club info."""
    ip = request.client.host if request.client else "?"
    _check_rate_limit(ip)
    pin = data.get("pin", "")
    admin_pin = _get_admin_pin(db)
    if pin == admin_pin:
        print(f"[LOGIN] admin from {ip}")
        return {"role": "admin", "club_id": None, "club_name": "Admin"}
    club = db.query(Club).filter(Club.pin == pin).first()
    if not club:
        print(f"[LOGIN] FAILED pin={pin} from {ip}")
        raise HTTPException(401, "Invalid PIN")
    print(f"[LOGIN] coach club=\"{club.name}\" from {ip}")
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
                     ("meet_uploaded_at", datetime.utcnow().isoformat()),
                     ("meet_name", meet.meet_name)]:
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
    name = db.query(AppConfig).get("meet_name")
    return {
        "filename": filename.value if filename else None,
        "uploaded_at": uploaded.value if uploaded else None,
        "meet_name": name.value if name else None,
        "events": db.query(Event).count(),
    }

@router.get("/clubs")
def list_clubs(db: Session = Depends(get_db)):
    clubs = db.query(Club).order_by(Club.name).all()
    return [{"id": c.id, "name": c.name, "code": c.code,
             "pin": c.pin, "admin_email": c.admin_email or "",
             "athlete_count": len(c.athletes)} for c in clubs]


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


@router.post("/clubs/{club_id}/reset-pin")
def reset_club_pin(club_id: int, db: Session = Depends(get_db)):
    """Reset PIN for a single club."""
    import random
    club = db.query(Club).get(club_id)
    if not club:
        raise HTTPException(404)
    club.pin = f"{random.randint(100000, 999999)}"
    db.commit()
    return {"club": club.name, "pin": club.pin}


@router.put("/clubs/{club_id}")
def update_club(club_id: int, data: dict, db: Session = Depends(get_db)):
    club = db.query(Club).get(club_id)
    if not club:
        raise HTTPException(404)
    if "admin_email" in data:
        club.admin_email = data["admin_email"]
    db.commit()
    return {"ok": True}


@router.post("/clubs/{club_id}/send-pin")
def send_pin(club_id: int, data: dict, db: Session = Depends(get_db)):
    """Create one-time secret link with PIN, send invite email via Resend."""
    import uuid
    from datetime import timedelta
    from cryptography.fernet import Fernet
    import httpx

    club = db.query(Club).get(club_id)
    if not club:
        raise HTTPException(404)
    if not club.admin_email:
        raise HTTPException(400, "No admin email set for this club")

    lang = data.get("lang", "fr")
    resend_key = os.environ.get("RESEND_API_KEY")
    if not resend_key:
        raise HTTPException(500, "RESEND_API_KEY not configured")

    # Encrypt PIN
    fernet_key = os.environ.get("SECRET_KEY", "default-secret-key-change-me!!")
    # Derive a valid Fernet key from the secret
    import hashlib, base64
    key = base64.urlsafe_b64encode(hashlib.sha256(fernet_key.encode()).digest())
    f = Fernet(key)
    pin_encrypted = f.encrypt(club.pin.encode()).decode()

    # Create secret link
    token = str(uuid.uuid4())
    expires = datetime.utcnow() + timedelta(days=7)
    link = SecretLink(token=token, club_id=club.id,
                      pin_encrypted=pin_encrypted, expires_at=expires)
    db.add(link)
    db.commit()

    # Build URL
    base_url = os.environ.get("APP_BASE_URL", "http://localhost:8001")
    secret_url = f"{base_url}/secret/{token}"

    # Get meet name
    meet_cfg = db.query(AppConfig).get("meet_name")
    meet_name = meet_cfg.value if meet_cfg else "Meet"

    # Email content
    if lang == "fr":
        subject = f"Invitation — {meet_name}"
        html = (f"<p>Bonjour,</p>"
                f"<p>Vous êtes invité(e) à inscrire votre équipe <strong>{club.name}</strong> "
                f"pour <strong>{meet_name}</strong>.</p>"
                f"<p>Votre NIP sécurisé (lien à usage unique, expire dans 7 jours) :</p>"
                f"<p><a href=\"{secret_url}\">{secret_url}</a></p>"
                f"<p>Portail d'inscription : <a href=\"{base_url}\">{base_url}</a></p>"
                f"<p>Bonne compétition!</p>")
    else:
        subject = f"Invitation — {meet_name}"
        html = (f"<p>Hello,</p>"
                f"<p>You are invited to register your team <strong>{club.name}</strong> "
                f"for <strong>{meet_name}</strong>.</p>"
                f"<p>Your secure PIN (one-time link, expires in 7 days):</p>"
                f"<p><a href=\"{secret_url}\">{secret_url}</a></p>"
                f"<p>Registration portal: <a href=\"{base_url}\">{base_url}</a></p>"
                f"<p>Good luck!</p>")

    # Send via Resend
    from_email = os.environ.get("RESEND_FROM_EMAIL", "noreply@example.com")
    resp = httpx.post("https://api.resend.com/emails", json={
        "from": from_email,
        "to": [club.admin_email],
        "subject": subject,
        "html": html,
    }, headers={"Authorization": f"Bearer {resend_key}"}, timeout=10)

    if resp.status_code not in (200, 201):
        raise HTTPException(502, f"Resend error: {resp.text}")

    return {"message": f"Email sent to {club.admin_email}"}


@router.get("/secret/{token}")
def reveal_secret(token: str, db: Session = Depends(get_db)):
    """One-time reveal of encrypted PIN."""
    import hashlib, base64
    from cryptography.fernet import Fernet

    link = db.query(SecretLink).filter(SecretLink.token == token).first()
    if not link:
        raise HTTPException(404, "Link not found")
    if link.viewed:
        raise HTTPException(410, "This link has already been viewed")
    if datetime.utcnow() > link.expires_at:
        raise HTTPException(410, "This link has expired")

    # Decrypt PIN
    fernet_key = os.environ.get("SECRET_KEY", "default-secret-key-change-me!!")
    key = base64.urlsafe_b64encode(hashlib.sha256(fernet_key.encode()).digest())
    f = Fernet(key)
    pin = f.decrypt(link.pin_encrypted.encode()).decode()

    # Mark as viewed
    link.viewed = True
    db.commit()

    club = db.query(Club).get(link.club_id)
    return {"pin": pin, "club": club.name if club else ""}


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
    best_map_lcm: dict[int, int] = {}
    best_map_scm: dict[int, int] = {}
    for b in best:
        if b.course == "SCM":
            best_map_scm[b.style_uid] = b.time_ms
        else:
            best_map_lcm[b.style_uid] = b.time_ms

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
        s["best_time_lcm_ms"] = best_map_lcm.get(s["style_uid"])
        s["best_time_scm_ms"] = best_map_scm.get(s["style_uid"])

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


@router.post("/admin/change-pin")
def change_admin_pin(data: dict, db: Session = Depends(get_db)):
    """Change the admin PIN."""
    new_pin = data.get("pin", "")
    if len(new_pin) < 4:
        raise HTTPException(400, "PIN must be at least 4 characters")
    cfg = db.query(AppConfig).get("admin_pin")
    if cfg:
        cfg.value = new_pin
    else:
        db.add(AppConfig(key="admin_pin", value=new_pin))
    db.commit()
    return {"ok": True}


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
