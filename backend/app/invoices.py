"""Create Stripe draft invoices summarising registration fees, one per club."""
from __future__ import annotations

import json
import os

import stripe
from sqlalchemy.orm import Session, joinedload

from .models import Athlete, AppConfig, Club, Event, Registration


MEET_FEE_LABELS = {
    "CLUB": "Frais de club",
    "ATHLETE": "Frais par athlète",
    "RELAY": "Frais par relais",
    "TEAM": "Frais d'équipe",
    "LATEFEE": "Inscription tardive",
    "LSCMEETFEE": "Frais LSC",
}


def _meet_fees(db: Session) -> dict[str, int]:
    cfg = db.query(AppConfig).get("meet_fees_json")
    if not cfg or not cfg.value:
        return {}
    try:
        data = json.loads(cfg.value)
    except ValueError:
        return {}
    return {k: int(v) for k, v in data.items() if isinstance(v, (int, float))}


def _stripe_client() -> None:
    key = os.environ.get("STRIPE_API_KEY")
    if not key:
        raise RuntimeError("STRIPE_API_KEY not configured")
    stripe.api_key = key


def _club_line_items(db: Session, club: Club, meet_fees: dict[str, int]) -> list[dict]:
    """Build flat line items for a club: per-event fees (individual events bill
    per athlete, relay events bill once per team) plus meet-level fees (CLUB,
    ATHLETE × distinct registered athletes, RELAY × distinct relay events,
    TEAM/LATEFEE/LSCMEETFEE qty 1)."""
    rows = (
        db.query(Registration, Event, Athlete)
        .join(Event, Registration.event_id == Event.id)
        .join(Athlete, Registration.athlete_id == Athlete.id)
        .filter(Athlete.club_id == club.id, Event.fee_cents > 0)
        .all()
    )

    event_items: list[dict] = []
    relay_seen: dict[int, dict] = {}

    for reg, ev, ath in rows:
        if ev.relay_count == 1:
            event_items.append({
                "event_number": ev.event_number,
                "event_name": ev.style_name or "",
                "description": f"{ath.last_name.upper()}, {ath.first_name}",
                "qty": 1,
                "unit_cents": ev.fee_cents,
                "_sort": (ev.event_number or 0, ath.last_name.lower(), ath.first_name.lower()),
            })
        else:
            line = relay_seen.get(ev.id)
            if line is None:
                line = {
                    "event_number": ev.event_number,
                    "event_name": ev.style_name or "",
                    "description": "",
                    "members": [],
                    "qty": 1,
                    "unit_cents": ev.fee_cents,
                    "_sort": (ev.event_number or 0, "", ""),
                }
                relay_seen[ev.id] = line
                event_items.append(line)
            line["members"].append(f"{ath.last_name.upper()}, {ath.first_name}")

    for line in relay_seen.values():
        members = sorted(set(line.pop("members")))
        line["description"] = "Relais — " + ", ".join(members) if members else "Relais"

    event_items.sort(key=lambda x: x["_sort"])
    for it in event_items:
        it.pop("_sort", None)

    # Meet-level fee lines, sorted before event lines
    meet_items: list[dict] = []
    if meet_fees:
        # Quantities derived from this club's registrations
        athlete_count = (
            db.query(Athlete.id)
            .join(Registration, Registration.athlete_id == Athlete.id)
            .filter(Athlete.club_id == club.id)
            .distinct()
            .count()
        )
        relay_event_count = (
            db.query(Event.id)
            .join(Registration, Registration.event_id == Event.id)
            .join(Athlete, Registration.athlete_id == Athlete.id)
            .filter(Athlete.club_id == club.id, Event.relay_count > 1)
            .distinct()
            .count()
        )
        qty_for = {
            "CLUB": 1,
            "ATHLETE": athlete_count,
            "RELAY": relay_event_count,
            "TEAM": 1,
            "LATEFEE": 1,
            "LSCMEETFEE": 1,
        }
        for ftype, cents in meet_fees.items():
            if not cents:
                continue
            qty = qty_for.get(ftype, 1)
            if qty <= 0:
                continue
            meet_items.append({
                "event_number": None,
                "event_name": MEET_FEE_LABELS.get(ftype, ftype),
                "description": "",
                "qty": qty,
                "unit_cents": cents,
            })

    return meet_items + event_items


def _find_or_create_customer(club: Club) -> stripe.Customer:
    email = (club.admin_email or "").strip()
    if email:
        existing = stripe.Customer.list(email=email, limit=1)
        if existing.data:
            return existing.data[0]
    return stripe.Customer.create(
        name=club.name,
        email=email or None,
        metadata={"meetmanager_club_id": str(club.id)},
    )


def _create_draft_for_club(club: Club, items: list[dict], meet_name: str) -> dict:
    customer = _find_or_create_customer(club)
    invoice = stripe.Invoice.create(
        customer=customer.id,
        auto_advance=False,
        currency="cad",
        collection_method="send_invoice",
        days_until_due=30,
        description=f"{meet_name} — Inscriptions",
        metadata={
            "meetmanager_club_id": str(club.id),
            "meetmanager_meet": meet_name,
        },
        pending_invoice_items_behavior="exclude",
    )
    for it in items:
        desc_parts = []
        if it["event_number"]:
            desc_parts.append(f"#{it['event_number']}")
        if it["event_name"]:
            desc_parts.append(it["event_name"])
        if it["description"]:
            desc_parts.append(it["description"])
        stripe.InvoiceItem.create(
            customer=customer.id,
            invoice=invoice.id,
            currency="cad",
            amount=it["unit_cents"] * it["qty"],
            description=" — ".join(desc_parts) or "Inscription",
        )
    return {
        "club": club.name,
        "invoice_id": invoice.id,
        "url": f"https://dashboard.stripe.com/invoices/{invoice.id}",
    }


def _meet_name(db: Session) -> str:
    cfg = db.query(AppConfig).get("meet_name")
    return cfg.value if cfg else "Compétition"


def create_invoice_for_club(db: Session, club_id: int) -> dict:
    """Create a single Stripe draft invoice for one club."""
    _stripe_client()
    club = db.query(Club).options(joinedload(Club.athletes)).get(club_id)
    if not club:
        raise ValueError(f"Club {club_id} not found")
    items = _club_line_items(db, club, _meet_fees(db))
    if not items:
        raise ValueError("No billable items for this club")
    return _create_draft_for_club(club, items, _meet_name(db))


def create_invoices_for_all_clubs(db: Session) -> dict:
    """Create Stripe draft invoices for every club with billable items."""
    _stripe_client()
    meet_name = _meet_name(db)
    meet_fees = _meet_fees(db)
    clubs = (
        db.query(Club)
        .options(joinedload(Club.athletes))
        .order_by(Club.name)
        .all()
    )
    created: list[dict] = []
    skipped: list[str] = []
    errors: list[dict] = []
    for club in clubs:
        items = _club_line_items(db, club, meet_fees)
        if not items:
            skipped.append(club.name)
            continue
        try:
            created.append(_create_draft_for_club(club, items, meet_name))
        except stripe.StripeError as e:
            errors.append({"club": club.name, "error": str(e)})
    return {"created": created, "skipped": skipped, "errors": errors}
