"""Seed the database from a template/historical MDB on first boot."""
from __future__ import annotations

import os
from access_parser import AccessParser
from sqlalchemy.orm import Session
from .models import Club, Athlete, Base
from .database import engine, SessionLocal


def seed_if_empty():
    """If the DB has no clubs, seed from the MDB in TEMPLATE_MDB env var."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Club).count() > 0:
            return  # Already seeded

        mdb_path = os.environ.get("TEMPLATE_MDB", "/app/template.mdb")
        if not os.path.exists(mdb_path):
            print(f"[seed] No MDB at {mdb_path}, skipping seed")
            return

        print(f"[seed] Seeding from {mdb_path}...")
        mdb = AccessParser(mdb_path)

        # Clubs
        cl = mdb.parse_table("CLUB")
        club_map = {}  # mdb_clubid -> db Club
        for i in range(len(cl["CLUBID"])):
            name = cl["NAME"][i]
            if not name:
                continue
            club = Club(
                name=str(name).strip(),
                code=str(cl["CODE"][i] or "")[:10],
                city=str(cl["CONTACTCITY"][i] or "").strip() or None,
                contact_email=str(cl["CONTACTEMAIL"][i] or "").strip() or None,
            )
            db.add(club)
            db.flush()
            club_map[int(cl["CLUBID"][i])] = club

        # Athletes
        ath = mdb.parse_table("ATHLETE")
        athlete_map = {}  # mdb_athleteid -> db Athlete
        for i in range(len(ath["ATHLETEID"])):
            first = ath["FIRSTNAME"][i]
            last = ath["LASTNAME"][i]
            if not first or not last:
                continue
            mdb_club_id = int(ath["CLUBID"][i]) if ath["CLUBID"][i] else None
            club = club_map.get(mdb_club_id)
            if not club:
                continue

            gender_int = int(ath["GENDER"][i]) if ath["GENDER"][i] else 0
            gender_str = "M" if gender_int == 1 else "F" if gender_int == 2 else "M"

            bd = ath["BIRTHDATE"][i]
            birthdate = None
            if bd:
                try:
                    from datetime import datetime
                    if isinstance(bd, datetime):
                        birthdate = bd.date()
                    elif isinstance(bd, str):
                        birthdate = datetime.strptime(bd[:10], "%Y-%m-%d").date()
                    else:
                        birthdate = bd
                except Exception:
                    pass

            if birthdate is None:
                continue  # Can't create athlete without DOB

            athlete = Athlete(
                first_name=str(first).strip(),
                last_name=str(last).strip(),
                gender=gender_str,
                birthdate=birthdate,
                nran=str(ath["LICENSE"][i] or "").strip() or None,
                club_id=club.id,
            )
            db.add(athlete)
            db.flush()
            athlete_map[int(ath["ATHLETEID"][i])] = athlete

        db.commit()
        print(f"[seed] Imported {len(club_map)} clubs, {len(athlete_map)} athletes")

    finally:
        db.close()
