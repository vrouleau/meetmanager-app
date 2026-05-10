"""Generate per-club PDF invoices summarising registration fees."""
from __future__ import annotations

import zipfile
from datetime import date
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)
from sqlalchemy.orm import Session, joinedload

from .models import Athlete, AppConfig, Club, Event, Registration


_BRAND = colors.HexColor("#1e3a8a")  # deep blue
_BAND = colors.HexColor("#eef2ff")   # very pale indigo
_MUTED = colors.HexColor("#6b7280")  # gray-500


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _slug(s: str) -> str:
    out = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_"):
            out.append("_")
    return ("".join(out).strip("_") or "club")[:60]


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
                "total_cents": ev.fee_cents,
                "_sort": (ev.event_number or 0, ath.last_name.lower(), ath.first_name.lower()),
            })
        else:
            line = relay_seen.get(ev.id)
            if line is None:
                line = {
                    "event_number": ev.event_number,
                    "event_name": ev.style_name or "",
                    "description": "",  # filled below
                    "members": [],
                    "qty": 1,
                    "unit_cents": ev.fee_cents,
                    "total_cents": ev.fee_cents,
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


def _invoice_pdf(meet_name: str, club: Club, items: list[dict],
                 invoice_no: str, issue_date: date) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=LETTER,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        title=f"Facture {club.name}",
    )
    styles = getSampleStyleSheet()
    h_meet = ParagraphStyle("h_meet", parent=styles["Title"],
                            fontSize=18, leading=22, textColor=_BRAND, alignment=TA_LEFT)
    h_inv = ParagraphStyle("h_inv", parent=styles["Title"],
                           fontSize=26, leading=30, textColor=_BRAND, alignment=TA_RIGHT)
    label = ParagraphStyle("label", parent=styles["Normal"],
                           fontSize=8, textColor=_MUTED, leading=10, spaceAfter=2)
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, leading=13)
    body_b = ParagraphStyle("body_b", parent=body, fontName="Helvetica-Bold")
    cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=9, leading=11)
    cell_r = ParagraphStyle("cell_r", parent=cell, alignment=TA_RIGHT)
    foot = ParagraphStyle("foot", parent=styles["Normal"], fontSize=8,
                          textColor=_MUTED, alignment=TA_CENTER)

    flow: list = []

    # Header band
    head = Table(
        [[Paragraph(meet_name or "Compétition", h_meet),
          Paragraph("FACTURE / INVOICE", h_inv)]],
        colWidths=[4.0 * inch, 3.0 * inch],
    )
    head.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
    ]))
    flow.append(head)
    flow.append(Table([[""]], colWidths=[7.0 * inch], rowHeights=[2],
                      style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), _BRAND)])))
    flow.append(Spacer(1, 14))

    # Bill-to / meta block
    bill_to = [
        Paragraph("FACTURÉ À / BILLED TO", label),
        Paragraph(f"<b>{club.name}</b>", body_b),
    ]
    if club.code:
        bill_to.append(Paragraph(club.code, body))
    if club.admin_email:
        bill_to.append(Paragraph(club.admin_email, body))

    meta = [
        Paragraph("N° / NO.", label),
        Paragraph(invoice_no, body),
        Spacer(1, 4),
        Paragraph("DATE", label),
        Paragraph(issue_date.strftime("%Y-%m-%d"), body),
    ]
    meta_block = Table([[bill_to, meta]], colWidths=[4.5 * inch, 2.5 * inch])
    meta_block.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    flow.append(meta_block)
    flow.append(Spacer(1, 18))

    # Line items
    header_row = [
        Paragraph("<b>#</b>", cell),
        Paragraph("<b>ÉPREUVE / EVENT</b>", cell),
        Paragraph("<b>DÉTAIL</b>", cell),
        Paragraph("<b>QTÉ</b>", cell_r),
        Paragraph("<b>P.U.</b>", cell_r),
        Paragraph("<b>MONTANT</b>", cell_r),
    ]
    data = [header_row]
    subtotal = 0
    for it in items:
        subtotal += it["total_cents"]
        data.append([
            Paragraph(str(it["event_number"] or ""), cell),
            Paragraph(it["event_name"], cell),
            Paragraph(it["description"], cell),
            Paragraph(str(it["qty"]), cell_r),
            Paragraph(_money(it["unit_cents"]), cell_r),
            Paragraph(_money(it["total_cents"]), cell_r),
        ])

    if not items:
        data.append([Paragraph("<i>Aucune épreuve facturable.</i>", cell),
                     "", "", "", "", ""])

    line_table = Table(
        data,
        colWidths=[0.4 * inch, 2.4 * inch, 2.5 * inch, 0.5 * inch, 0.6 * inch, 0.9 * inch],
        repeatRows=1,
    )
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), _BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, _BRAND),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    if items:
        for i in range(1, len(data)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), _BAND))
        if len(items) == 1 and not data[1][0]:
            pass
    line_table.setStyle(TableStyle(style))
    flow.append(line_table)
    flow.append(Spacer(1, 10))

    # Totals box
    totals = Table(
        [
            ["", Paragraph("Sous-total / Subtotal", body), Paragraph(_money(subtotal), cell_r)],
            ["", Paragraph("<b>TOTAL</b>", body_b), Paragraph(f"<b>{_money(subtotal)}</b>", cell_r)],
        ],
        colWidths=[4.5 * inch, 1.6 * inch, 1.2 * inch],
    )
    totals.setStyle(TableStyle([
        ("LINEABOVE", (1, 1), (-1, 1), 1.0, _BRAND),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
    ]))
    flow.append(totals)
    flow.append(Spacer(1, 18))
    flow.append(Paragraph(
        "Merci de votre participation. / Thank you for your participation.",
        foot))

    doc.build(flow)
    return buf.getvalue()


def generate_invoices_zip(db: Session) -> bytes:
    """Build a zip containing one PDF invoice per club that has billable items."""
    meet_cfg = db.query(AppConfig).get("meet_name")
    meet_name = meet_cfg.value if meet_cfg else "Compétition"
    issue_date = date.today()

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        clubs = (
            db.query(Club)
            .options(joinedload(Club.athletes))
            .order_by(Club.name)
            .all()
        )
        for club in clubs:
            items = _club_line_items(db, club)
            if not items:
                continue
            invoice_no = f"INV-{issue_date.strftime('%Y%m%d')}-{club.id:04d}"
            pdf = _invoice_pdf(meet_name, club, items, invoice_no, issue_date)
            z.writestr(f"{_slug(club.name)}.pdf", pdf)
    return buf.getvalue()
