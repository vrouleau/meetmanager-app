# Meet Manager — meetmanager-app

Web application for lifesaving meet registration. Clubs log in with a PIN, register their athletes for events, and the admin manages the meet, invites clubs, and generates Stripe invoices.

## Stack

- **Backend**: FastAPI (Python 3.12) + SQLAlchemy 2.0 + PostgreSQL 16
- **Frontend**: React 18 + Vite + Tailwind CSS
- **Deployment**: Docker Compose (`docker-compose.yml` at repo root)
- **Email**: Resend API (via `httpx`)
- **Billing**: Stripe (draft invoices)

## Repo layout

```
meetmanager-app/
├── backend/
│   └── app/
│       ├── main.py            # FastAPI app, CORS, DB init
│       ├── models.py          # SQLAlchemy models (Club, Athlete, Event, Registration, BestTime, AppConfig, SecretLink)
│       ├── database.py        # DB engine, get_db dependency
│       ├── meet_parser.py     # Parse SPLASH .lxf meet export → ParsedMeet dataclass
│       ├── events.py          # Load ParsedMeet events into DB
│       ├── seed.py            # Import clubs/athletes from Lenex .lxf entries file
│       ├── best_times.py      # Import best times from Lenex entries/results .lxf
│       ├── export.py          # Generate registrations .lxf (Lenex output)
│       ├── invoices.py        # Stripe draft invoice generation
│       └── routers/
│           └── api.py         # All REST endpoints (prefix: /api)
├── frontend/src/
│   ├── main.jsx               # React entry, router
│   ├── i18n.jsx               # Bilingual (fr/en) translations via LangProvider / useLang()
│   ├── api.js                 # Axios instance (base /api)
│   ├── pages/
│   │   ├── Admin.jsx          # Admin panel (meet upload, clubs, invoices, fee summary)
│   │   ├── Athletes.jsx       # Club coach view: athlete list
│   │   ├── Register.jsx       # Per-athlete event registration
│   │   ├── Login.jsx          # PIN entry
│   │   └── Secret.jsx         # One-time PIN reveal page (/secret/:token)
│   └── buildInfo.js           # Build timestamp injected at build time
├── quantum/
│   └── LSTSTYLE.en-UK         # SPLASH Quantum style seed file
├── docs/                      # Workflow screenshots and PDFs
└── docker-compose.yml
```

## Data model

| Table | Key columns |
|---|---|
| `clubs` | id, name, code, nation, pin (6-digit), admin_email |
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
| POST | `/auth` | Validate PIN → role (admin/coach) + club info |
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
| GET | `/athletes` | List athletes (optional `?club_id=`) |
| POST | `/athletes` | Create athlete |
| PUT | `/athletes/:id` | Update athlete |
| DELETE | `/athletes/:id` | Delete athlete + registrations |
| GET | `/athletes/:id/registration` | Full registration state for athlete |
| POST | `/registrations` | Register athlete for event |
| DELETE | `/registrations/:id` | Remove registration |
| DELETE | `/registrations` | Flush all registrations |
| POST | `/upload/preview` | Preview Lenex .lxf import (count new clubs/athletes) |
| POST | `/upload/entries` | Import clubs + athletes + best times from Lenex |
| POST | `/upload/results` | Import best times from results Lenex |
| GET | `/export` | Download registrations .lxf + simulate scripts as .zip |
| GET | `/events` | List events |
| GET | `/status` | DB counts |
| POST | `/clubs/regenerate-pins` | Regenerate all club PINs |
| POST | `/admin/change-pin` | Change admin PIN |
| POST | `/invoices` | Create Stripe draft invoices for all clubs |
| POST | `/secret/:token` | Reveal PIN via one-time token |

## Key behaviours

**Meet upload**: Replaces all event data and registrations. Club PINs are regenerated. All metadata goes into `app_config`. **Do not add ALTER TABLE / migration logic** — just update the models.

**Age code routing**: `10-`, `11-12`, `13-14`, `15-18`, `Open`, `Masters`. Age is computed against Dec 31 of the meet year. Masters is never auto-suggested.

**Relay lock**: A club can only field one relay team per event. If any other athlete in the club has registered for a relay style, the style is locked for additional athletes.

**Stripe invoicing** (`invoices.py`):
- Meet-level fees (CLUB × 1, ATHLETE × distinct athletes with ≥1 reg, RELAY × distinct relay events entered, TEAM/LATEFEE/LSCMEETFEE × 1) come from `meet_fees_json` in AppConfig.
- Per-entry fees come from `Event.fee_cents`; individual events bill per athlete, relay events bill once per team.
- Fees with qty ≤ 0 or cents = 0 are skipped.
- Late fees (LATEFEE) are in the data but not conditionally gated — the user decided not to implement conditional late-fee logic.

**i18n**: `useLang()` returns `{ t, lang, toggle }`. All UI strings go through `t.key`. Both `fr` and `en` locales must be updated together in `i18n.jsx`.

**Fee summary** (Admin.jsx `FeeSummary` component): scrollable monospace box showing meet-level fees + per-event fees, rendered after the meet info banner.

## Running locally

```bash
# Start all services
docker compose up --build

# Backend available at http://localhost:8000
# Frontend available at http://localhost:8001
```

## Testing

```bash
cd tests
pip install -r requirements-test.txt
pytest test_integration.py
```

Tests use a real PostgreSQL instance (no mocks). See `tests/README.md`.
