# Meet Manager — meetmanager-app

Web application for lifesaving meet registration. Clubs log in with a PIN, register their athletes for events. The admin manages the meet, designates an organizer, and generates Stripe invoices. The organizer handles day-to-day meet ops (upload, invites, closure date).

## Stack

- **Backend**: FastAPI (Python 3.12) + SQLAlchemy 2.0 + PostgreSQL 16
- **Frontend**: React 18 + Vite + Tailwind CSS
- **Deployment**: Docker Compose (`docker-compose.yml` at repo root)
- **Email**: Resend API (via `httpx`)
- **Billing**: Stripe Connect + reportlab PDF invoices

## Repo layout

```
meetmanager-app/
├── backend/
│   └── app/
│       ├── main.py            # FastAPI app, CORS, DB init
│       ├── models.py          # SQLAlchemy models
│       ├── database.py        # DB engine, get_db dependency
│       ├── meet_parser.py     # Parse SPLASH .lxf meet export → ParsedMeet dataclass
│       ├── events.py          # Load ParsedMeet events into DB
│       ├── seed.py            # Import clubs/athletes from Lenex .lxf entries file
│       ├── best_times.py      # Import best times from Lenex entries/results .lxf
│       ├── export.py          # Generate registrations .lxf (Lenex output)
│       ├── invoices.py        # Stripe invoices + PDF generation (reportlab)
│       └── routers/
│           └── api.py         # All REST endpoints (prefix: /api)
│   └── scripts/
│       ├── simulate_results.bat  # Windows launcher for VBS script
│       └── simulate_results.vbs  # Simulate results in SPLASH (included in export .zip)
├── frontend/src/
│   ├── main.jsx               # React entry, router, nav (role-based visibility)
│   ├── i18n.jsx               # Bilingual (fr/en) translations via LangProvider / useLang()
│   ├── api.js                 # Axios instance (base /api)
│   ├── pages/
│   │   ├── Admin.jsx          # Admin panel (entries upload, results upload, export, invoices, set organizer, flush meet)
│   │   ├── Organizer.jsx      # Organizer panel (meet upload, closure date, fee summary, team invites, Stripe connect/disconnect, invoice PDF download)
│   │   ├── Athletes.jsx       # Club coach view: athlete list
│   │   ├── Register.jsx       # Per-athlete event registration
│   │   ├── Login.jsx          # PIN entry
│   │   └── Secret.jsx         # One-time PIN reveal page (/secret/:token)
│   └── buildInfo.js           # Build timestamp injected at build time
├── quantum/
│   └── LSTSTYLE.en-UK         # Swiss Timing Quantum style seed file
├── docs/                      # Documentation (markdown + generated PDFs)
│   ├── assets/                # Screenshots used in docs
│   ├── workflow_en.md/pdf     # Quick-start workflow (English)
│   ├── workflow_fr.md/pdf     # Quick-start workflow (French)
│   ├── manual_en.md/pdf       # Full user manual (English)
│   ├── manual_fr.md/pdf       # Full user manual (French)
│   └── pdf-header.tex         # Pandoc LaTeX header for PDF generation
├── tests/                     # Integration tests (real PostgreSQL)
└── docker-compose.yml
```

## Roles

| Role | Access |
|---|---|
| **admin** | Full access: all pages, set organizer, flush meet, invoices, change admin PIN |
| **organizer** | A club coach whose club is flagged as organizer. Sees Athletes + Organizer pages. Can upload meet, set closure date, send invitations, invite all. Cannot edit other clubs' registrations. |
| **coach** | Standard club login. Sees Athletes page (own club only). |

## Data model

| Table | Key columns |
|---|---|
| `clubs` | id, name, code (unique — import key), nation, pin (6-digit), admin_email, stripe_account_id |
| `athletes` | id, first_name, last_name, gender, birthdate, license, exception ('X'=Masters), club_id |
| `events` | id, splash_event_id, style_uid, style_name, distance, relay_count, gender, event_number, round, masters, fee_cents, session_id |
| `age_groups` | id, event_id, splash_agegroup_id, age_min, age_max |
| `registrations` | id, athlete_id, event_id, age_code, entry_time_ms |
| `best_times` | id, athlete_id, style_uid, time_ms, course (LCM/SCM) |
| `secret_links` | id, token (UUID), club_id, pin_encrypted, expires_at, viewed, lang |
| `app_config` | key (PK), value — key-value store for meet metadata |

### AppConfig keys

| Key | Value |
|---|---|
| `meet_filename` | original .lxf filename |
| `meet_uploaded_at` | ISO datetime |
| `meet_name` | meet name from Lenex |
| `meet_course` | LCM / SCM |
| `meet_masters` | T / F |
| `meet_currency` | currency code (CAD, etc.) |
| `meet_fees_json` | JSON: `{"CLUB": cents, "ATHLETE": cents, ...}` |
| `closure_date` | ISO date or "" |
| `admin_pin` | admin PIN override |
| `organizer_club_id` | club.id of the designated organizer |

## Environment variables (`.env`)

```
ADMIN_PIN=          # default 314159
RESEND_API_KEY=     # for invite emails
RESEND_FROM_EMAIL=
APP_BASE_URL=       # public URL for links in emails
SECRET_KEY=         # Fernet encryption key for PIN in secret links
STRIPE_API_KEY=     # Stripe secret key for invoice generation
DATABASE_URL=       # set automatically by Docker Compose
```

## API endpoints (all `/api/...`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth` | Validate PIN → role (admin/organizer/coach) + club info |
| POST | `/upload/meet` | Upload SPLASH meet .lxf → load event structure |
| GET | `/meet-info` | Meet metadata, fees, event list |
| PUT | `/closure-date` | Set entry deadline |
| GET | `/clubs` | List clubs |
| POST | `/clubs` | Create club |
| PUT | `/clubs/:id` | Update club (admin_email) |
| DELETE | `/clubs/:id` | Delete club + athletes + registrations |
| POST | `/clubs/:id/reset-pin` | Reset single club PIN |
| POST | `/clubs/:id/send-pin` | Send invite email with one-time PIN link |
| POST | `/clubs/:id/create-invoice` | Create Stripe draft invoice for one club |
| GET | `/clubs/:id/invoice-total` | Get invoice total (cents) for one club |
| GET | `/clubs/:id/invoice-pdf` | Download PDF invoice for one club |
| POST | `/clubs/:id/invoice` | Send Stripe invoice to one club (via connected account) |
| GET | `/stripe/status` | Check if organizer Stripe account is connected |
| POST | `/stripe/connect` | Start Stripe Connect OAuth flow |
| POST | `/stripe/disconnect` | Disconnect organizer Stripe account |
| GET | `/athletes` | List athletes (optional `?club_id=`) |
| POST | `/athletes` | Create athlete |
| PUT | `/athletes/:id` | Update athlete |
| DELETE | `/athletes/:id` | Delete athlete + registrations |
| GET | `/athletes/:id/registration` | Full registration state for athlete |
| POST | `/registrations` | Register athlete for event |
| DELETE | `/registrations/:id` | Remove registration |
| DELETE | `/registrations` | **Flush meet**: delete registrations + events + meet config + organizer designation |
| POST | `/upload/preview` | Preview Lenex .lxf import (count new clubs/athletes) |
| POST | `/upload/entries` | Import clubs + athletes + best times from Lenex |
| POST | `/upload/results` | Import best times from results Lenex |
| GET | `/export` | Download registrations .lxf + simulate scripts as .zip |
| GET | `/events` | List events |
| GET | `/status` | DB counts |
| POST | `/clubs/regenerate-pins` | Regenerate all club PINs |
| POST | `/admin/change-pin` | Change admin PIN |
| POST | `/admin/set-organizer` | Designate a club as organizer (body: `{club_id}`) |
| GET | `/admin/organizer` | Return current organizer club info |
| POST | `/invoices` | Create Stripe draft invoices for all clubs |
| POST | `/organizer/clubs/invite-all` | Send invitation to all clubs with email set (body: `{lang}`) |
| POST | `/secret/:token` | Reveal PIN via one-time token |

## Key behaviours and design rules

**Meet upload**: Replaces all event data and registrations. All metadata goes into `app_config`. **Do not add ALTER TABLE / migration logic** — just update the models directly, SQLAlchemy creates the table fresh on first run.

**Flush meet** (`DELETE /registrations`): Deletes registrations, events, and meet-related AppConfig keys (meet_filename, meet_uploaded_at, meet_name, meet_course, meet_masters, meet_currency, meet_fees_json, closure_date, organizer_club_id). Keeps clubs, athletes, best times, PINs intact.

**Organizer role**: A club whose `id` matches AppConfig `organizer_club_id`. Auth returns `role: "organizer"`. Organizer can upload meet, set closure date, send invitations, and invite all clubs. Cannot edit other clubs' registrations. Flush meet clears the organizer designation — it never carries over.

**Age code routing**: `10-`, `11-12`, `13-14`, `15-18`, `Open`, `Masters`. Age computed against Dec 31 of the meet year. Masters is never auto-suggested.

**Relay lock**: A club can only field one relay team per event. If any other athlete in the club has registered for a relay style, the style is locked for additional athletes.

**Stripe invoicing** (`invoices.py`):
- Meet-level fees: CLUB × 1, ATHLETE × distinct athletes with ≥1 registration, RELAY × distinct relay events entered, TEAM/LATEFEE/LSCMEETFEE × 1. Source: `meet_fees_json` AppConfig key.
- Per-entry fees: resolved from paired TIM/PRE event structure. Fee events (round=1, masters=True) have `fee_cents > 0` but no registrations. Athletes register in the paired PRE event (round=2, masters=False, fee_cents=0). The fee is looked up from `event_number - 1`. Individual events bill per athlete; relay events bill once per team.
- Items with qty ≤ 0 or cents = 0 are skipped.
- Late fees (LATEFEE) exist in the data but are NOT conditionally gated.
- PDF fallback: `generate_invoice_pdf()` produces a reportlab PDF when Stripe is not connected.
- Stripe Connect: organizer connects their Stripe account via OAuth. Invoices are sent through the connected account.

**i18n**: `useLang()` returns `{ t, lang, toggle }`. All UI strings must go through `t.key`. Both `fr` and `en` locales must be updated together in `i18n.jsx`.

**Fee summary**: `FeeSummary` component in `Organizer.jsx` — scrollable monospace box showing meet-level fees + per-event fees.

**Export**: `/export` returns a .zip containing the registrations .lxf plus `simulate_results.bat` and `simulate_results.vbs` (scripts for simulating results in SPLASH on meet day).

## Running locally

```bash
docker compose up --build
# Backend: http://localhost:8000
# Frontend: http://localhost:8001
```

## Testing

```bash
cd tests && pip install -r requirements-test.txt && pytest test_integration.py
```

Tests hit a real PostgreSQL instance — do not mock the database.
