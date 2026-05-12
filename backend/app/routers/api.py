"""API endpoints."""
from __future__ import annotations

import os
import secrets
import string
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
from ..export_entries import generate_entries_lxf
from ..invoices import create_invoice_for_club

router = APIRouter(prefix="/api")

MEET_STORAGE = Path(os.environ.get("MEET_STORAGE", "/app/data/meet.lxf"))
_DEFAULT_ADMIN_PIN = os.environ.get("ADMIN_PIN", "000000")
_BEST_TIME_MAX_AGE_MONTHS = int(os.environ.get("BEST_TIME_MAX_AGE_MONTHS", "18"))


def _get_admin_pin(db: Session) -> str:
    cfg = db.query(AppConfig).get("admin_pin")
    return cfg.value if cfg else _DEFAULT_ADMIN_PIN


_AGE_CODE_ORDER = ("10-", "11-12", "13-14", "15-18", "Open", "Masters")


def _age_group_code(age_min: int, age_max: int) -> str | None:
    if age_min <= 10 and age_max == 10:
        return "10-"
    if age_min == 11 and age_max == 12:
        return "11-12"
    if age_min == 13 and age_max == 14:
        return "13-14"
    if age_min == 15 and age_max == 18:
        return "15-18"
    if age_min == 19 and age_max == -1:
        return "Open"
    return None

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


def _resolve_role(pin: str, db: Session) -> tuple[str, int | None]:
    """Return (role, club_id) for a given PIN."""
    if pin == _get_admin_pin(db):
        return "admin", None
    club = db.query(Club).filter(Club.pin == pin).first()
    if not club:
        return "none", None
    org_cfg = db.query(AppConfig).get("organizer_club_id")
    if org_cfg and org_cfg.value == str(club.id):
        return "organizer", club.id
    return "coach", club.id


def require_admin(request: Request, db: Session = Depends(get_db)):
    pin = request.headers.get("X-Club-Pin", "")
    if pin != _get_admin_pin(db):
        raise HTTPException(403, "Admin access required")


def require_organizer_or_admin(request: Request, db: Session = Depends(get_db)):
    pin = request.headers.get("X-Club-Pin", "")
    role, _ = _resolve_role(pin, db)
    if role not in ("admin", "organizer"):
        raise HTTPException(403, "Organizer or admin access required")


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
        print(f"[LOGIN] FAILED from {ip}")
        raise HTTPException(401, "Invalid PIN")
    # Check if this club is the designated organizer
    org_cfg = db.query(AppConfig).get("organizer_club_id")
    if org_cfg and org_cfg.value == str(club.id):
        print(f"[LOGIN] organizer club=\"{club.name}\" from {ip}")
        return {"role": "organizer", "club_id": club.id, "club_name": club.name}
    print(f"[LOGIN] coach club=\"{club.name}\" from {ip}")
    return {"role": "coach", "club_id": club.id, "club_name": club.name}


@router.post("/upload/meet", dependencies=[Depends(require_organizer_or_admin)])
async def upload_meet(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload meet .lxf — sets event structure."""
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 10MB)")
    from ..meet_parser import parse_meet_lxf
    try:
        meet = parse_meet_lxf(content)
    except Exception as e:
        raise HTTPException(400, f"Invalid meet .lxf: {e}")

    MEET_STORAGE.parent.mkdir(parents=True, exist_ok=True)
    MEET_STORAGE.write_bytes(content)

    # Reload events: wipe registrations first (FK -> events has no cascade),
    # then events. Replacing the meet erases the prior competition.
    db.query(Registration).delete()
    db.query(Event).delete()
    db.flush()
    from ..events import _load_from_parsed
    count = _load_from_parsed(db, meet)

    # Track metadata
    import json as _json
    for key, val in [("meet_filename", file.filename or "meet.lxf"),
                     ("meet_uploaded_at", datetime.utcnow().isoformat()),
                     ("meet_name", meet.meet_name),
                     ("meet_course", meet.course),
                     ("meet_masters", "T" if meet.masters else "F"),
                     ("meet_currency", meet.currency or "CAD"),
                     ("meet_fees_json", _json.dumps(meet.meet_fees))]:
        cfg = db.query(AppConfig).get(key)
        if cfg:
            cfg.value = val
        else:
            db.add(AppConfig(key=key, value=val))

    # Reset closure date
    closure = db.query(AppConfig).get("closure_date")
    if closure:
        closure.value = ""

    # Regenerate club PINs
    for club in db.query(Club).all():
        club.pin = ''.join(secrets.choice(string.digits) for _ in range(6))

    db.commit()
    return {"events_loaded": count, "filename": file.filename}


@router.get("/meet-info")
def meet_info(db: Session = Depends(get_db)):
    import json as _json
    filename = db.query(AppConfig).get("meet_filename")
    uploaded = db.query(AppConfig).get("meet_uploaded_at")
    name = db.query(AppConfig).get("meet_name")
    course = db.query(AppConfig).get("meet_course")
    masters = db.query(AppConfig).get("meet_masters")
    closure = db.query(AppConfig).get("closure_date")
    currency = db.query(AppConfig).get("meet_currency")
    fees_json = db.query(AppConfig).get("meet_fees_json")
    try:
        meet_fees = _json.loads(fees_json.value) if fees_json and fees_json.value else {}
    except ValueError:
        meet_fees = {}
    event_fees = [
        {
            "event_number": e.event_number,
            "style_name": e.style_name,
            "distance": e.distance,
            "relay_count": e.relay_count,
            "fee_cents": e.fee_cents or 0,
        }
        for e in db.query(Event).order_by(Event.event_number).all()
    ]
    return {
        "filename": filename.value if filename else None,
        "uploaded_at": uploaded.value if uploaded else None,
        "meet_name": name.value if name else None,
        "course": course.value if course else None,
        "masters": (masters.value == "T") if masters else False,
        "events": db.query(Event).count(),
        "closure_date": closure.value if closure else None,
        "currency": currency.value if currency else "CAD",
        "meet_fees": meet_fees,
        "event_fees": event_fees,
    }


@router.put("/closure-date", dependencies=[Depends(require_organizer_or_admin)])
def set_closure_date(data: dict, db: Session = Depends(get_db)):
    val = data.get("closure_date") or ""
    cfg = db.query(AppConfig).get("closure_date")
    if cfg:
        cfg.value = val
    else:
        db.add(AppConfig(key="closure_date", value=val))
    db.commit()
    return {"closure_date": val}

@router.get("/clubs")
def list_clubs(request: Request, db: Session = Depends(get_db)):
    pin = request.headers.get("X-Club-Pin", "")
    role, _ = _resolve_role(pin, db)
    clubs = db.query(Club).order_by(Club.name).all()
    result = []
    for c in clubs:
        item = {"id": c.id, "name": c.name, "code": c.code,
                "admin_email": c.admin_email or "",
                "athlete_count": len(c.athletes)}
        if role == "admin":
            item["pin"] = c.pin
        result.append(item)
    return result


@router.post("/clubs", dependencies=[Depends(require_admin)])
def create_club(data: dict, db: Session = Depends(get_db)):
    pin = data.get("pin") or ''.join(secrets.choice(string.digits) for _ in range(6))
    club = Club(name=data["name"], code=data.get("code", ""), nation=data.get("nation", "CAN"), pin=pin)
    db.add(club)
    db.commit()
    return {"id": club.id, "pin": club.pin}


@router.delete("/clubs/{club_id}", dependencies=[Depends(require_admin)])
def delete_club(club_id: int, db: Session = Depends(get_db)):
    if not db.query(Club.id).filter(Club.id == club_id).first():
        raise HTTPException(404)
    athlete_ids = [aid for (aid,) in db.query(Athlete.id).filter(Athlete.club_id == club_id).all()]
    if athlete_ids:
        db.query(Registration).filter(Registration.athlete_id.in_(athlete_ids)).delete(synchronize_session=False)
        db.query(BestTime).filter(BestTime.athlete_id.in_(athlete_ids)).delete(synchronize_session=False)
    db.query(Athlete).filter(Athlete.club_id == club_id).delete(synchronize_session=False)
    db.query(SecretLink).filter(SecretLink.club_id == club_id).delete(synchronize_session=False)
    db.query(Club).filter(Club.id == club_id).delete(synchronize_session=False)
    db.commit()
    return {"deleted": True, "athletes_deleted": len(athlete_ids)}


@router.post("/clubs/{club_id}/reset-pin", dependencies=[Depends(require_admin)])
def reset_club_pin(club_id: int, db: Session = Depends(get_db)):
    """Reset PIN for a single club."""
    club = db.query(Club).get(club_id)
    if not club:
        raise HTTPException(404)
    club.pin = ''.join(secrets.choice(string.digits) for _ in range(6))
    db.commit()
    return {"club": club.name, "pin": club.pin}


@router.put("/clubs/{club_id}", dependencies=[Depends(require_admin)])
def update_club(club_id: int, data: dict, db: Session = Depends(get_db)):
    club = db.query(Club).get(club_id)
    if not club:
        raise HTTPException(404)
    if "admin_email" in data:
        club.admin_email = data["admin_email"]
    db.commit()
    return {"ok": True}


@router.post("/clubs/{club_id}/send-pin", dependencies=[Depends(require_organizer_or_admin)])
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
                      pin_encrypted=pin_encrypted, expires_at=expires, lang=lang)
    db.add(link)
    db.flush()
    db.commit()
    db.refresh(link)
    print(f"[send_pin] SecretLink id={link.id} token={token[:8]}... committed")

    # Build URL
    base_url = os.environ.get("APP_BASE_URL", "http://localhost:8001")
    secret_url = f"{base_url}/secret/{token}"

    # Get meet name and closure date
    meet_cfg = db.query(AppConfig).get("meet_name")
    meet_name = meet_cfg.value if meet_cfg else "Meet"
    closure_cfg = db.query(AppConfig).get("closure_date")
    closure_date = closure_cfg.value if closure_cfg else None

    # Email content
    if lang == "fr":
        subject = f"Invitation — {meet_name}"
        deadline = (f"<p style=\"color:#c00;font-weight:bold\">⚠️ Date limite d'inscription : {closure_date}. "
                    f"Après cette date, vous ne pourrez plus accéder au portail d'inscription.</p>") if closure_date else ""
        html = (f"<p>Bonjour,</p>"
                f"<p>Vous êtes invité(e) à inscrire les athlètes de votre équipe "
                f"<strong>{club.name}</strong> à la compétition <strong>{meet_name}</strong>.</p>"
                f"{deadline}"
                f"<p><strong>Marche à suivre :</strong></p>"
                f"<ol>"
                f"<li><strong>Récupérer votre NIP.</strong> Cliquer sur le lien sécurisé ci-dessous "
                f"pour afficher votre NIP. <em>Le lien est à usage unique et expire dans 7 jours — "
                f"prenez le NIP en note immédiatement, il ne pourra plus être affiché par la suite.</em>"
                f"<br><a href=\"{secret_url}\">{secret_url}</a></li>"
                f"<li><strong>Ouvrir le portail d'inscription</strong> à l'adresse "
                f"<a href=\"{base_url}\">{base_url}</a> et se connecter avec le NIP de votre équipe.</li>"
                f"<li><strong>Inscrire vos athlètes.</strong> Sélectionner un athlète, "
                f"cocher les épreuves, choisir la catégorie (15-18 / Open / Masters) et "
                f"ajuster le temps d'inscription si nécessaire. Répéter pour chaque athlète à inscrire.</li>"
                f"</ol>"
                f"<p>Bonne compétition!</p>"
                f"<hr style=\"margin-top:20px\"><p style=\"font-size:11px;color:#888\">Ce courriel est envoyé automatiquement. Veuillez ne pas y répondre.</p>")
    else:
        subject = f"Invitation — {meet_name}"
        deadline = (f"<p style=\"color:#c00;font-weight:bold\">⚠️ Entry deadline: {closure_date}. "
                    f"After this date, you will no longer be able to access the registration portal.</p>") if closure_date else ""
        html = (f"<p>Hello,</p>"
                f"<p>You are invited to register the athletes of your team "
                f"<strong>{club.name}</strong> for <strong>{meet_name}</strong>.</p>"
                f"{deadline}"
                f"<p><strong>How to proceed:</strong></p>"
                f"<ol>"
                f"<li><strong>Get your PIN.</strong> Click the secure link below to reveal your PIN. "
                f"<em>The link can only be used once and expires in 7 days — write the PIN down "
                f"immediately, it will not be shown again.</em>"
                f"<br><a href=\"{secret_url}\">{secret_url}</a></li>"
                f"<li><strong>Open the registration portal</strong> at "
                f"<a href=\"{base_url}\">{base_url}</a> and log in with your team's PIN.</li>"
                f"<li><strong>Register your athletes.</strong> Pick an athlete, check the events, "
                f"select the category (15-18 / Open / Masters) and adjust the entry time if needed. "
                f"Repeat for every athlete you want to register.</li>"
                f"</ol>"
                f"<p>Good luck!</p>"
                f"<hr style=\"margin-top:20px\"><p style=\"font-size:11px;color:#888\">This is an automated email. Please do not reply.</p>")

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


@router.post("/secret/{token}")
def reveal_secret(token: str, db: Session = Depends(get_db)):
    """One-time reveal of encrypted PIN."""
    import hashlib, base64
    from cryptography.fernet import Fernet

    link = db.query(SecretLink).filter(SecretLink.token == token).first()
    if not link:
        raise HTTPException(404, "Lien introuvable. / Link not found.")
    if link.viewed:
        raise HTTPException(410, "Ce lien a déjà été utilisé. / This link has already been viewed.")
    if datetime.utcnow() > link.expires_at:
        raise HTTPException(410, "Ce lien est expiré. / This link has expired.")

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

    # Expire best times older than BEST_TIME_MAX_AGE_MONTHS (or with no date)
    if best:
        from datetime import date as _d
        import calendar as _cal
        today = _d.today()
        m = _BEST_TIME_MAX_AGE_MONTHS
        cutoff_month = today.month - (m % 12)
        cutoff_year = today.year - (m // 12)
        if cutoff_month <= 0:
            cutoff_month += 12
            cutoff_year -= 1
        cutoff = _d(cutoff_year, cutoff_month,
                    min(today.day, _cal.monthrange(cutoff_year, cutoff_month)[1]))

        from collections import defaultdict as _dd
        by_style: dict[int, list] = _dd(list)
        for b in best:
            by_style[b.style_uid].append(b)

        expired_styles = {
            uid for uid, rows in by_style.items()
            if any(r.recorded_on is None or r.recorded_on < cutoff for r in rows)
        }
        if expired_styles:
            best = [b for b in best if b.style_uid not in expired_styles]
            db.query(BestTime).filter(
                BestTime.athlete_id == athlete_id,
                BestTime.style_uid.in_(expired_styles),
            ).delete(synchronize_session=False)
            db.commit()

    best_map_lcm: dict[int, int] = {}
    best_map_scm: dict[int, int] = {}
    for b in best:
        if b.course == "SCM":
            best_map_scm[b.style_uid] = b.time_ms
        else:
            best_map_lcm[b.style_uid] = b.time_ms

    events = db.query(Event).options(joinedload(Event.age_groups)).order_by(Event.event_number).all()

    ath_gender_int = 1 if athlete.gender.value == "M" else 2

    # Build style groups; categories come from each event's age groups (or "Masters").
    # An event_id is referenced once per (style, age_code) — first event wins on duplicates
    # (e.g., a style with both PRE and TIM rounds for the same age group).
    styles: dict[int, dict] = {}

    for ev in events:
        if ev.round == 9:  # skip finals
            continue
        # Individual-event gender filter; gender=0 means "all" (e.g., 10-and-under combined)
        if ev.relay_count == 1 and ev.gender != 0 and ev.gender != ath_gender_int:
            continue

        if ev.masters:
            event_codes = ["Masters"]
        else:
            event_codes = []
            for ag in ev.age_groups:
                code = _age_group_code(ag.age_min, ag.age_max)
                if code and code not in event_codes:
                    event_codes.append(code)
        if not event_codes:
            continue

        if ev.style_uid not in styles:
            styles[ev.style_uid] = {
                "style_uid": ev.style_uid,
                "style_name": ev.style_name,
                "distance": ev.distance,
                "relay_count": ev.relay_count,
                "categories": [],
            }
        style = styles[ev.style_uid]

        for code in event_codes:
            if any(c["age_code"] == code for c in style["categories"]):
                continue
            reg = next((r for r in regs if r.event_id == ev.id and r.age_code == code), None)
            style["categories"].append({
                "event_id": ev.id,
                "age_code": code,
                "registered": reg is not None,
                "registration_id": reg.id if reg else None,
                "entry_time_ms": reg.entry_time_ms if reg else None,
            })

    # Sort each style's categories by canonical order
    order_idx = {c: i for i, c in enumerate(_AGE_CODE_ORDER)}
    for s in styles.values():
        s["categories"].sort(key=lambda c: order_idx.get(c["age_code"], 99))

    individual_events = [s for s in styles.values() if s["relay_count"] == 1]
    relay_events = [s for s in styles.values() if s["relay_count"] > 1]

    # Add best time to each style group
    for s in individual_events + relay_events:
        s["best_time_lcm_ms"] = best_map_lcm.get(s["style_uid"])
        s["best_time_scm_ms"] = best_map_scm.get(s["style_uid"])

    # Relay locks: a club fields one team per relay event, so if any other
    # athlete in the same club already has a registration on this style,
    # this athlete's edit page must show the relay locked.
    relay_uids = [s["style_uid"] for s in relay_events]
    locked_by: dict[int, str] = {}
    if relay_uids:
        other_relay_regs = (
            db.query(Athlete, Event)
            .join(Registration, Registration.athlete_id == Athlete.id)
            .join(Event, Registration.event_id == Event.id)
            .filter(
                Athlete.club_id == athlete.club_id,
                Athlete.id != athlete_id,
                Event.style_uid.in_(relay_uids),
                Event.relay_count > 1,
            )
            .all()
        )
        for ath, ev in other_relay_regs:
            locked_by.setdefault(ev.style_uid, f"{ath.first_name} {ath.last_name}")
    for s in relay_events:
        s["locked_by_name"] = locked_by.get(s["style_uid"])

    # Club athletes for relay teammate selection
    club_athletes = db.query(Athlete).filter(
        Athlete.club_id == athlete.club_id,
        Athlete.id != athlete_id,
    ).order_by(Athlete.last_name).all()

    # Determine suggested age_code from athlete DOB
    # Masters is never auto-suggested — coach selects it manually if applicable
    suggested_age_code = "Open"
    if athlete.birthdate:
        from datetime import date as d
        age = d(2026, 12, 31).year - athlete.birthdate.year
        if age <= 10:
            suggested_age_code = "10-"
        elif 11 <= age <= 12:
            suggested_age_code = "11-12"
        elif 13 <= age <= 14:
            suggested_age_code = "13-14"
        elif 15 <= age <= 18:
            suggested_age_code = "15-18"

    meet_course_cfg = db.query(AppConfig).get("meet_course")
    meet_course = meet_course_cfg.value if meet_course_cfg else "LCM"

    closure_cfg = db.query(AppConfig).get("closure_date")
    return {
        "athlete": {
            "id": athlete.id, "first_name": athlete.first_name,
            "last_name": athlete.last_name, "gender": athlete.gender.value,
            "birthdate": str(athlete.birthdate) if athlete.birthdate else "",
            "license": athlete.license or "",
            "club": athlete.club.name, "club_id": athlete.club_id,
        },
        "suggested_age_code": suggested_age_code,
        "meet_course": meet_course,
        "closure_date": closure_cfg.value if closure_cfg else None,
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


def _update_exception(db: Session, athlete_id: int):
    """Set exception='X' if athlete has any Masters registration, else clear it."""
    has_masters = db.query(Registration).filter(
        Registration.athlete_id == athlete_id,
        Registration.age_code == "Masters",
    ).first() is not None
    athlete = db.query(Athlete).get(athlete_id)
    if athlete:
        athlete.exception = "X" if has_masters else None


def _check_closure(db: Session, pin: str = ""):
    if pin == _get_admin_pin(db):
        return
    # Organizer also bypasses closure
    club = db.query(Club).filter(Club.pin == pin).first()
    if club:
        org_cfg = db.query(AppConfig).get("organizer_club_id")
        if org_cfg and org_cfg.value == str(club.id):
            return
    cfg = db.query(AppConfig).get("closure_date")
    if cfg and cfg.value:
        from datetime import date
        if date.today() > date.fromisoformat(cfg.value):
            raise HTTPException(403, "Inscriptions fermées / Entries closed")


def _caller_club_id(db: Session, pin: str) -> int | None:
    """Return the club_id of the caller, or None if admin."""
    if pin == _get_admin_pin(db):
        return None  # admin can edit anything
    club = db.query(Club).filter(Club.pin == pin).first()
    return club.id if club else None


@router.post("/registrations")
def create_registration(data: dict, request: Request, db: Session = Depends(get_db)):
    pin = request.headers.get("X-Club-Pin", "")
    _check_closure(db, pin)
    athlete_id = data["athlete_id"]
    event_id = data["event_id"]
    age_code = data.get("age_code", "OPEN")
    entry_time_ms = data.get("entry_time_ms")

    # Ownership check: non-admin can only register own club's athletes
    caller_club = _caller_club_id(db, pin)
    if caller_club is not None:
        athlete = db.query(Athlete).get(athlete_id)
        if not athlete or athlete.club_id != caller_club:
            raise HTTPException(403, "Cannot register athletes from another club")

    existing = db.query(Registration).filter(
        Registration.athlete_id == athlete_id,
        Registration.event_id == event_id,
        Registration.age_code == age_code,
    ).first()

    if existing:
        existing.entry_time_ms = entry_time_ms
        db.commit()
        _update_exception(db, athlete_id)
        db.commit()
        return {"id": existing.id, "updated": True}

    reg = Registration(
        athlete_id=athlete_id, event_id=event_id,
        age_code=age_code, entry_time_ms=entry_time_ms,
    )
    db.add(reg)
    db.commit()
    _update_exception(db, athlete_id)
    db.commit()
    return {"id": reg.id, "updated": False}


@router.delete("/registrations/{reg_id}")
def delete_registration(reg_id: int, request: Request, db: Session = Depends(get_db)):
    pin = request.headers.get("X-Club-Pin", "")
    _check_closure(db, pin)
    reg = db.query(Registration).get(reg_id)
    if not reg:
        raise HTTPException(404)
    # Ownership check
    caller_club = _caller_club_id(db, pin)
    if caller_club is not None:
        athlete = db.query(Athlete).get(reg.athlete_id)
        if not athlete or athlete.club_id != caller_club:
            raise HTTPException(403, "Cannot modify registrations from another club")
    athlete_id = reg.athlete_id
    db.delete(reg)
    db.commit()
    _update_exception(db, athlete_id)
    db.commit()
    return {"deleted": True}


@router.post("/upload/preview", dependencies=[Depends(require_admin)])
async def upload_preview(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Parse a Lenex .lxf and return the counts that would be created, without writing."""
    from ..seed import parse_lxf
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 10MB)")
    try:
        clubs_data = parse_lxf(content)
    except Exception as e:
        raise HTTPException(400, f"Invalid Lenex .lxf: {e}")

    clubs_new = 0
    athletes_new = 0
    for cd in clubs_data:
        club = db.query(Club).filter(Club.name == cd["name"]).first()
        if not club:
            clubs_new += 1
            athletes_new += len(cd["athletes"])
        else:
            for ad in cd["athletes"]:
                existing = db.query(Athlete).filter(
                    Athlete.first_name == ad["first_name"],
                    Athlete.last_name == ad["last_name"],
                    Athlete.club_id == club.id,
                ).first()
                if not existing:
                    athletes_new += 1
    return {
        "clubs_new": clubs_new,
        "athletes_new": athletes_new,
        "clubs_in_file": len(clubs_data),
        "athletes_in_file": sum(len(cd["athletes"]) for cd in clubs_data),
    }


@router.post("/upload/entries", dependencies=[Depends(require_admin)])
async def upload_entries(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload .lxf — seeds clubs + athletes and populates best times."""
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 10MB)")
    seed_result = seed_from_lxf(db, content)
    times_result = load_best_times(db, content, source=file.filename or "upload")
    return {**seed_result, **times_result}


@router.post("/upload/results", dependencies=[Depends(require_admin)])
async def upload_results(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload results .lxf to populate best times (alias for entries upload)."""
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 10MB)")
    seed_result = seed_from_lxf(db, content)
    times_result = load_best_times(db, content, source=file.filename or "upload")
    return {**seed_result, **times_result}


@router.get("/status")
def status(db: Session = Depends(get_db)):
    return {
        "clubs": db.query(Club).count(),
        "athletes": db.query(Athlete).count(),
        "events": db.query(Event).count(),
        "registrations": db.query(Registration).count(),
        "best_times": db.query(BestTime).count(),
    }


@router.delete("/registrations", dependencies=[Depends(require_admin)])
def flush_meet(db: Session = Depends(get_db)):
    """Flush meet: delete registrations, events, meet config, and organizer designation."""
    reg_count = db.query(Registration).delete()
    db.query(Event).delete()
    for key in ("meet_filename", "meet_uploaded_at", "meet_name", "meet_course",
                "meet_masters", "meet_currency", "meet_fees_json", "closure_date",
                "organizer_club_id"):
        cfg = db.query(AppConfig).get(key)
        if cfg:
            db.delete(cfg)
    db.commit()
    return {"deleted": reg_count}


@router.post("/clubs/regenerate-pins", dependencies=[Depends(require_admin)])
def regenerate_pins(db: Session = Depends(get_db)):
    """Regenerate all club PINs."""
    clubs = db.query(Club).all()
    for club in clubs:
        club.pin = ''.join(secrets.choice(string.digits) for _ in range(6))
    db.commit()
    return {"regenerated": len(clubs)}


@router.post("/organizer/clubs/invite-all", dependencies=[Depends(require_organizer_or_admin)])
def invite_all_clubs(data: dict, request: Request, db: Session = Depends(get_db)):
    """Send PIN invitation email to all clubs that have an admin_email set."""
    lang = data.get("lang", "fr")
    clubs = db.query(Club).filter(Club.admin_email != None, Club.admin_email != "").all()
    sent = 0
    errors = []
    for club in clubs:
        try:
            send_pin(club.id, {"lang": lang}, db)
            sent += 1
        except Exception as e:
            errors.append({"club": club.name, "error": str(e)})
    return {"sent": sent, "errors": errors}


@router.get("/admin/organizer", dependencies=[Depends(require_admin)])
def get_organizer(db: Session = Depends(get_db)):
    """Return current organizer club info."""
    cfg = db.query(AppConfig).get("organizer_club_id")
    if not cfg:
        return {"club_id": None, "club_name": None}
    club = db.query(Club).get(int(cfg.value))
    if not club:
        return {"club_id": None, "club_name": None}
    return {"club_id": club.id, "club_name": club.name}


@router.post("/admin/set-organizer", dependencies=[Depends(require_admin)])
def set_organizer(data: dict, db: Session = Depends(get_db)):
    """Designate a club as the meet organizer."""
    club_id = data.get("club_id")
    if club_id is None:
        raise HTTPException(400, "club_id required")
    if not db.query(Club).get(club_id):
        raise HTTPException(404, "Club not found")
    cfg = db.query(AppConfig).get("organizer_club_id")
    if cfg:
        cfg.value = str(club_id)
    else:
        db.add(AppConfig(key="organizer_club_id", value=str(club_id)))
    db.commit()
    return {"ok": True, "organizer_club_id": club_id}


@router.post("/admin/change-pin", dependencies=[Depends(require_admin)])
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


@router.post("/stripe/connect", dependencies=[Depends(require_organizer_or_admin)])
def stripe_connect_start(db: Session = Depends(get_db)):
    """Create a Stripe Account Link for the organizer club to onboard via Connect."""
    import stripe
    stripe.api_key = os.environ.get("STRIPE_API_KEY")
    if not stripe.api_key:
        raise HTTPException(500, "STRIPE_API_KEY not configured")

    org_cfg = db.query(AppConfig).get("organizer_club_id")
    if not org_cfg:
        raise HTTPException(400, "No organizer club set")
    club = db.query(Club).get(int(org_cfg.value))
    if not club:
        raise HTTPException(404, "Organizer club not found")

    # Create a new connected account if none exists
    if not club.stripe_account_id:
        account = stripe.Account.create(type="standard")
        club.stripe_account_id = account.id
        db.commit()

    base_url = os.environ.get("APP_BASE_URL", "http://localhost:8001")
    link = stripe.AccountLink.create(
        account=club.stripe_account_id,
        refresh_url=f"{base_url}/organizer?stripe=refresh",
        return_url=f"{base_url}/organizer?stripe=success",
        type="account_onboarding",
    )
    return {"url": link.url}


@router.get("/stripe/status", dependencies=[Depends(require_organizer_or_admin)])
def stripe_connect_status(db: Session = Depends(get_db)):
    """Return whether the organizer club has a connected Stripe account."""
    import stripe
    org_cfg = db.query(AppConfig).get("organizer_club_id")
    if not org_cfg:
        return {"connected": False}
    club = db.query(Club).get(int(org_cfg.value))
    if not club or not club.stripe_account_id:
        return {"connected": False}

    # Verify account is fully onboarded
    stripe.api_key = os.environ.get("STRIPE_API_KEY")
    if not stripe.api_key:
        return {"connected": False}
    try:
        acct = stripe.Account.retrieve(club.stripe_account_id)
        return {"connected": acct.charges_enabled, "account_id": club.stripe_account_id}
    except Exception:
        return {"connected": False}


@router.post("/stripe/disconnect", dependencies=[Depends(require_organizer_or_admin)])
def stripe_disconnect(db: Session = Depends(get_db)):
    """Remove the Stripe account link from the organizer club."""
    org_cfg = db.query(AppConfig).get("organizer_club_id")
    if not org_cfg:
        raise HTTPException(400, "No organizer club set")
    club = db.query(Club).get(int(org_cfg.value))
    if not club:
        raise HTTPException(404, "Organizer club not found")
    club.stripe_account_id = None
    db.commit()
    return {"ok": True}


@router.get("/clubs/{club_id}/invoice-pdf", dependencies=[Depends(require_organizer_or_admin)])
def club_invoice_pdf(club_id: int, db: Session = Depends(get_db)):
    """Download a PDF invoice for a single club."""
    from ..invoices import generate_invoice_pdf
    try:
        pdf = generate_invoice_pdf(db, club_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    club = db.query(Club).get(club_id)
    name = club.name.replace(" ", "_") if club else "club"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="invoice_{name}.pdf"'})


@router.get("/clubs/{club_id}/invoice-total", dependencies=[Depends(require_organizer_or_admin)])
def club_invoice_total(club_id: int, db: Session = Depends(get_db)):
    """Return the total billable amount in cents for a club."""
    from ..invoices import _club_line_items, _meet_fees
    club = db.query(Club).get(club_id)
    if not club:
        raise HTTPException(404)
    items = _club_line_items(db, club, _meet_fees(db))
    total = sum(it["unit_cents"] * it["qty"] for it in items)
    return {"club_id": club_id, "total_cents": total}


@router.post("/clubs/{club_id}/invoice", dependencies=[Depends(require_organizer_or_admin)])
def send_club_invoice(club_id: int, db: Session = Depends(get_db)):
    """Create and send a Stripe invoice for a club on the organizer's connected account."""
    import stripe
    stripe.api_key = os.environ.get("STRIPE_API_KEY")
    if not stripe.api_key:
        raise HTTPException(500, "STRIPE_API_KEY not configured")

    org_cfg = db.query(AppConfig).get("organizer_club_id")
    if not org_cfg:
        raise HTTPException(400, "No organizer club set")
    org_club = db.query(Club).get(int(org_cfg.value))
    if not org_club or not org_club.stripe_account_id:
        raise HTTPException(400, "Organizer has no connected Stripe account")

    club = db.query(Club).get(club_id)
    if not club:
        raise HTTPException(404, "Club not found")

    from ..invoices import _club_line_items, _meet_fees, _meet_name
    items = _club_line_items(db, club, _meet_fees(db))
    if not items:
        raise HTTPException(400, "No billable items for this club")

    acct = org_club.stripe_account_id
    meet_name = _meet_name(db)

    # Find or create customer on the connected account
    email = (club.admin_email or "").strip()
    customer = None
    if email:
        existing = stripe.Customer.list(email=email, limit=1, stripe_account=acct)
        if existing.data:
            customer = existing.data[0]
    if not customer:
        customer = stripe.Customer.create(
            name=club.name,
            email=email or None,
            metadata={"meetmanager_club_id": str(club.id)},
            stripe_account=acct,
        )

    invoice = stripe.Invoice.create(
        customer=customer.id,
        auto_advance=False,
        currency="cad",
        collection_method="send_invoice",
        days_until_due=30,
        description=f"{meet_name} — Inscriptions",
        metadata={"meetmanager_club_id": str(club.id), "meetmanager_meet": meet_name},
        pending_invoice_items_behavior="exclude",
        stripe_account=acct,
    )

    for it in items:
        desc_parts = []
        if it.get("event_number"):
            desc_parts.append(f"#{it['event_number']}")
        if it.get("event_name"):
            desc_parts.append(it["event_name"])
        if it.get("description"):
            desc_parts.append(it["description"])
        stripe.InvoiceItem.create(
            customer=customer.id,
            invoice=invoice.id,
            currency="cad",
            amount=it["unit_cents"] * it["qty"],
            description=" — ".join(desc_parts) or "Inscription",
            stripe_account=acct,
        )

    # Finalize and send
    stripe.Invoice.finalize_invoice(invoice.id, stripe_account=acct)
    stripe.Invoice.send_invoice(invoice.id, stripe_account=acct)

    return {
        "club": club.name,
        "invoice_id": invoice.id,
        "total_cents": sum(it["unit_cents"] * it["qty"] for it in items),
    }


@router.post("/clubs/{club_id}/create-invoice", dependencies=[Depends(require_organizer_or_admin)])
def create_club_invoice(club_id: int, db: Session = Depends(get_db)):
    """Create a Stripe draft invoice for a single club."""
    try:
        return create_invoice_for_club(db, club_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))


@router.get("/export", dependencies=[Depends(require_admin)])
def export_lenex(db: Session = Depends(get_db)):
    """Download a zip bundling the registrations .lxf with the simulate-results
    helper scripts so coaches can exercise SPLASH end-to-end without manually
    seeding swim times.
    """
    import zipfile
    from io import BytesIO

    lxf_bytes = generate_lxf(db)
    scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("inscriptions.lxf", lxf_bytes)
        for name in ("simulate_results.vbs", "simulate_results.bat"):
            p = scripts_dir / name
            if p.exists():
                z.writestr(name, p.read_bytes())

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=inscriptions_bundle.zip"},
    )


@router.get("/export/entries", dependencies=[Depends(require_admin)])
def export_entries_lxf(db: Session = Depends(get_db)):
    """Download a Lenex .lxf with all clubs, athletes, and best times (no registrations)."""
    data = generate_entries_lxf(db)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=entries.lxf"},
    )


@router.get("/export/meet-lxf", dependencies=[Depends(require_organizer_or_admin)])
def export_meet_lxf():
    """Download the currently uploaded meet .lxf file."""
    if not MEET_STORAGE.exists():
        raise HTTPException(404, "No meet uploaded")
    return Response(
        content=MEET_STORAGE.read_bytes(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=meet.lxf"},
    )


@router.get("/data-management/styles", dependencies=[Depends(require_admin)])
def get_styles(db: Session = Depends(get_db)):
    """List all unique style_uids present in best_times with display names."""
    from sqlalchemy import distinct as sq_distinct
    rows = db.query(sq_distinct(BestTime.style_uid)).all()
    result = []
    for (uid,) in rows:
        ev = db.query(Event).filter(Event.style_uid == uid).first()
        result.append({"uid": uid, "name": ev.style_name if ev else f"ID{uid}"})
    return sorted(result, key=lambda x: x["uid"])


@router.post("/data-management/merge-clubs", dependencies=[Depends(require_admin)])
def merge_clubs(data: dict, db: Session = Depends(get_db)):
    """Merge clubs: move all athletes to the target club, delete the source club."""
    merges = data.get("merges", [])
    merged = 0
    for m in merges:
        from_id = int(m["from_id"])
        to_id = int(m["to_id"])
        if from_id == to_id:
            continue
        from_club = db.query(Club).filter(Club.id == from_id).first()
        to_club = db.query(Club).filter(Club.id == to_id).first()
        if not from_club or not to_club:
            continue

        for ath in list(from_club.athletes):
            existing = db.query(Athlete).filter(
                Athlete.first_name == ath.first_name,
                Athlete.last_name == ath.last_name,
                Athlete.club_id == to_id,
            ).first()
            if not existing:
                ath.club_id = to_id
            else:
                # Merge best times into the existing athlete, keep the faster time
                for bt in list(ath.best_times):
                    existing_bt = db.query(BestTime).filter(
                        BestTime.athlete_id == existing.id,
                        BestTime.style_uid == bt.style_uid,
                        BestTime.course == bt.course,
                    ).first()
                    if not existing_bt:
                        bt.athlete_id = existing.id
                    else:
                        if bt.time_ms < existing_bt.time_ms:
                            existing_bt.time_ms = bt.time_ms
                        db.delete(bt)
                for reg in list(ath.registrations):
                    db.delete(reg)
                db.flush()
                db.delete(ath)

        db.flush()
        db.delete(from_club)
        merged += 1

    db.commit()
    return {"merged": merged}


@router.post("/data-management/merge-styles", dependencies=[Depends(require_admin)])
def merge_styles(data: dict, db: Session = Depends(get_db)):
    """Remap best_time rows from one style_uid to another, keeping the faster time."""
    merges = data.get("merges", [])
    merged_rows = 0
    for m in merges:
        from_uid = int(m["from_uid"])
        to_uid = int(m["to_uid"])
        if from_uid == to_uid:
            continue
        for bt in db.query(BestTime).filter(BestTime.style_uid == from_uid).all():
            existing = db.query(BestTime).filter(
                BestTime.athlete_id == bt.athlete_id,
                BestTime.style_uid == to_uid,
                BestTime.course == bt.course,
            ).first()
            if not existing:
                bt.style_uid = to_uid
                merged_rows += 1
            else:
                if bt.time_ms < existing.time_ms:
                    existing.time_ms = bt.time_ms
                db.delete(bt)
                merged_rows += 1

    db.commit()
    return {"merged_rows": merged_rows}
