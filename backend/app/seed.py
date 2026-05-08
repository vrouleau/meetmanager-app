"""Parse a Lenex entries .lxf and seed clubs + athletes into the DB."""
from __future__ import annotations

import zipfile
from datetime import date
from io import BytesIO
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session
from .models import Club, Athlete, Gender


def parse_lxf(file_bytes: bytes) -> list[dict]:
    """Parse .lxf zip -> list of {club, athletes} dicts."""
    with zipfile.ZipFile(BytesIO(file_bytes)) as z:
        lef_name = [n for n in z.namelist() if n.endswith(".lef")][0]
        xml_bytes = z.read(lef_name)

    root = ET.fromstring(xml_bytes)
    ns = ""  # Lenex 3.0 has no namespace typically
    clubs_data = []

    for meet in root.iter("MEET"):
        for clubs_el in meet.iter("CLUBS"):
            for club_el in clubs_el.findall("CLUB"):
                club_info = {
                    "name": club_el.get("name", ""),
                    "code": club_el.get("code", ""),
                    "nation": club_el.get("nation", ""),
                    "athletes": [],
                }
                for ath_el in club_el.iter("ATHLETE"):
                    bd_str = ath_el.get("birthdate", "")
                    birthdate = None
                    if bd_str:
                        try:
                            birthdate = date.fromisoformat(bd_str)
                        except ValueError:
                            pass
                    club_info["athletes"].append({
                        "first_name": ath_el.get("firstname", ""),
                        "last_name": ath_el.get("lastname", ""),
                        "gender": ath_el.get("gender", "M"),
                        "birthdate": birthdate,
                        "license": ath_el.get("license", ""),
                    })
                clubs_data.append(club_info)
    return clubs_data


def seed_from_lxf(db: Session, file_bytes: bytes) -> dict:
    """Parse .lxf and upsert clubs + athletes. Returns counts."""
    clubs_data = parse_lxf(file_bytes)
    clubs_added = 0
    athletes_added = 0

    for cd in clubs_data:
        club = db.query(Club).filter(Club.name == cd["name"]).first()
        if not club:
            club = Club(name=cd["name"], code=cd["code"], nation=cd["nation"])
            db.add(club)
            db.flush()
            clubs_added += 1

        for ad in cd["athletes"]:
            existing = db.query(Athlete).filter(
                Athlete.first_name == ad["first_name"],
                Athlete.last_name == ad["last_name"],
                Athlete.club_id == club.id,
            ).first()
            if not existing:
                gender = Gender.F if ad["gender"] == "F" else Gender.M
                ath = Athlete(
                    first_name=ad["first_name"],
                    last_name=ad["last_name"],
                    gender=gender,
                    birthdate=ad["birthdate"],
                    license=ad["license"],
                    club_id=club.id,
                )
                db.add(ath)
                athletes_added += 1

    db.commit()
    return {"clubs_added": clubs_added, "athletes_added": athletes_added}
