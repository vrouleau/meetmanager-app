"""Create Stripe draft invoices summarising registration fees, one per club."""
from __future__ import annotations

import os

import stripe
from sqlalchemy.orm import Session, joinedload

from .models import Athlete, AppConfig, Club, Event, Registration


def _stripe_client() -> None:
    key = os.environ.get("STRIPE_API_KEY")
    if not key:
        raise RuntimeError("STRIPE_API_KEY not configured")
    stripe.api_key = key


def _club_line_items(db: Session, club: Club) -> list[dict]:
    """Build flat line items for a club. Individual events bill per athlete;
    relay events bill once per team (a club fields one team per relay event)."""
    rows = (
        db.query(Registration, Event, Athlete)
        .join(Event, Registration.event_id == Event.id)
        .join(Athlete, Registration.athlete_id == Athlete.id)
        .filter(Athlete.club_id == club.id, Event.fee_cents > 0)
        .all()
    )

    items: list[dict] = []
    relay_seen: dict[int, dict] = {}

    for reg, ev, ath in rows:
        if ev.relay_count == 1:
            items.append({
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
                items.append(line)
            line["members"].append(f"{ath.last_name.upper()}, {ath.first_name}")

    for line in relay_seen.values():
        members = sorted(set(line.pop("members")))
        line["description"] = "Relais — " + ", ".join(members) if members else "Relais"

    items.sort(key=lambda x: x["_sort"])
    for it in items:
        it.pop("_sort", None)
    return items


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
            unit_amount=it["unit_cents"],
            quantity=it["qty"],
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
    items = _club_line_items(db, club)
    if not items:
        raise ValueError("No billable items for this club")
    return _create_draft_for_club(club, items, _meet_name(db))


def create_invoices_for_all_clubs(db: Session) -> dict:
    """Create Stripe draft invoices for every club with billable items."""
    _stripe_client()
    meet_name = _meet_name(db)
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
        items = _club_line_items(db, club)
        if not items:
            skipped.append(club.name)
            continue
        try:
            created.append(_create_draft_for_club(club, items, meet_name))
        except stripe.StripeError as e:
            errors.append({"club": club.name, "error": str(e)})
    return {"created": created, "skipped": skipped, "errors": errors}
