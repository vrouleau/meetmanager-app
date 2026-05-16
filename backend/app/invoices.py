"""Create Stripe draft invoices summarising registration fees, one per club."""
from __future__ import annotations

import json
import os
from datetime import date
from io import BytesIO

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
    # Build a map of event_number -> fee_cents for fee lookup (includes paired events)
    all_events = db.query(Event).all()
    fee_by_number = {e.event_number: e.fee_cents for e in all_events if e.fee_cents > 0}

    rows = (
        db.query(Registration, Event, Athlete)
        .join(Event, Registration.event_id == Event.id)
        .join(Athlete, Registration.athlete_id == Athlete.id)
        .filter(Athlete.club_id == club.id)
        .all()
    )

    event_items: list[dict] = []
    relay_seen: dict[int, dict] = {}

    for reg, ev, ath in rows:
        # Fee is either on this event or on the preceding event (paired structure)
        fee = ev.fee_cents or fee_by_number.get(ev.event_number - 1, 0)
        if fee <= 0:
            continue
        if ev.relay_count == 1:
            event_items.append({
                "event_number": ev.event_number,
                "event_name": ev.style_name or "",
                "description": f"{ath.last_name.upper()}, {ath.first_name}",
                "qty": 1,
                "unit_cents": fee,
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
                    "unit_cents": fee,
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
    email = (club.email or "").strip()
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


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def generate_invoice_pdf(db: Session, club_id: int) -> bytes:
    """Generate a PDF invoice for a single club."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    club = db.query(Club).get(club_id)
    if not club:
        raise ValueError(f"Club {club_id} not found")
    items = _club_line_items(db, club, _meet_fees(db))
    if not items:
        raise ValueError("No billable items for this club")

    meet_name = _meet_name(db)
    issue_date = date.today()
    invoice_no = f"INV-{issue_date.strftime('%Y%m%d')}-{club.id:04d}"

    _BRAND = colors.HexColor("#1e3a8a")
    _BAND = colors.HexColor("#eef2ff")
    _MUTED = colors.HexColor("#6b7280")

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER,
        leftMargin=0.7*inch, rightMargin=0.7*inch,
        topMargin=0.6*inch, bottomMargin=0.6*inch)
    styles = getSampleStyleSheet()
    h_meet = ParagraphStyle("h_meet", parent=styles["Title"], fontSize=18, leading=22, textColor=_BRAND, alignment=TA_LEFT)
    h_inv = ParagraphStyle("h_inv", parent=styles["Title"], fontSize=26, leading=30, textColor=_BRAND, alignment=TA_RIGHT)
    label = ParagraphStyle("label", parent=styles["Normal"], fontSize=8, textColor=_MUTED, leading=10, spaceAfter=2)
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, leading=13)
    body_b = ParagraphStyle("body_b", parent=body, fontName="Helvetica-Bold")
    cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=9, leading=11)
    cell_r = ParagraphStyle("cell_r", parent=cell, alignment=TA_RIGHT)

    flow = []

    # Header
    head = Table([[Paragraph(meet_name or "Compétition", h_meet), Paragraph("FACTURE / INVOICE", h_inv)]],
                 colWidths=[4.0*inch, 3.0*inch])
    head.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("BOTTOMPADDING", (0,0), (-1,-1), 8)]))
    flow.append(head)
    flow.append(Table([[""]], colWidths=[7.0*inch], rowHeights=[2],
                      style=TableStyle([("BACKGROUND", (0,0), (-1,-1), _BRAND)])))
    flow.append(Spacer(1, 14))

    # Bill-to
    bill_to = [Paragraph("FACTURÉ À / BILLED TO", label), Paragraph(f"<b>{club.name}</b>", body_b)]
    if club.email:
        bill_to.append(Paragraph(club.email, body))
    meta = [Paragraph("N° / NO.", label), Paragraph(invoice_no, body), Spacer(1,4),
            Paragraph("DATE", label), Paragraph(issue_date.strftime("%Y-%m-%d"), body)]
    meta_block = Table([[bill_to, meta]], colWidths=[4.5*inch, 2.5*inch])
    meta_block.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 0)]))
    flow.append(meta_block)
    flow.append(Spacer(1, 18))

    # Line items table
    header_row = [Paragraph("<b>#</b>", cell), Paragraph("<b>ÉPREUVE / EVENT</b>", cell),
                  Paragraph("<b>DÉTAIL</b>", cell), Paragraph("<b>QTÉ</b>", cell_r),
                  Paragraph("<b>P.U.</b>", cell_r), Paragraph("<b>MONTANT</b>", cell_r)]
    data = [header_row]
    subtotal = 0
    for it in items:
        line_total = it["unit_cents"] * it["qty"]
        subtotal += line_total
        data.append([
            Paragraph(str(it.get("event_number") or ""), cell),
            Paragraph(it.get("event_name", ""), cell),
            Paragraph(it.get("description", ""), cell),
            Paragraph(str(it["qty"]), cell_r),
            Paragraph(_money(it["unit_cents"]), cell_r),
            Paragraph(_money(line_total), cell_r),
        ])

    line_table = Table(data, colWidths=[0.4*inch, 2.4*inch, 2.5*inch, 0.5*inch, 0.6*inch, 0.9*inch], repeatRows=1)
    style = [
        ("BACKGROUND", (0,0), (-1,0), _BRAND), ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6), ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0,i), (-1,i), _BAND))
    line_table.setStyle(TableStyle(style))
    flow.append(line_table)
    flow.append(Spacer(1, 10))

    # Total
    totals = Table([
        ["", Paragraph("<b>TOTAL</b>", body_b), Paragraph(f"<b>{_money(subtotal)}</b>", cell_r)],
    ], colWidths=[4.5*inch, 1.6*inch, 1.2*inch])
    totals.setStyle(TableStyle([("LINEABOVE", (1,0), (-1,0), 1.0, _BRAND),
                                ("TOPPADDING", (0,0), (-1,-1), 6), ("ALIGN", (-1,0), (-1,-1), "RIGHT")]))
    flow.append(totals)

    doc.build(flow)
    return buf.getvalue()
