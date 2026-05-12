# Meet Manager App

[![CI](https://github.com/vrouleau/meetmanager-app/actions/workflows/ci.yml/badge.svg)](https://github.com/vrouleau/meetmanager-app/actions/workflows/ci.yml)

Web-based registration management for lifesaving competitions. Integrates with SPLASH Meet Manager via Lenex (.lxf) import/export.

## Features

### Imports
- **Meet file** — loads event structure, sessions, age groups, fees, and pool type (LCM/SCM) from a SPLASH-exported .lxf; replaces the previous meet and resets all registrations
- **Entries file** — imports clubs, athletes, and entry-time best times from a Lenex entries .lxf in a single pass
- **Results file** — imports best times from a SPLASH results .lxf; reads session dates, both individual and relay times; credits relay times to every team member

### Exports
- **Registrations bundle** — .zip with a Lenex registrations .lxf (correct SPLASH event/age-group IDs) plus `simulate_results.bat` and `simulate_results.vbs` for meet-day use
- **Entries .lxf** — all clubs, athletes, and best times exported as a Lenex entries file for backup or re-import into another system
- **Meet .lxf re-download** — retrieve the currently loaded meet file

### Registration
- Per-athlete event registration with age category dropdown (10−, 11−12, 13−14, 15−18, Open, Masters)
- Age computed against December 31 of the meet year
- Entry time pre-filled from the athlete's best time for the meet's pool length (LCM/SCM)
- Masters category gated behind the meet's masters flag — hidden when the meet has no masters events
- Relay lock: a club can only field one team per relay event; the event is locked for additional athletes once one athlete on that club registers

### Best times
- Separate LCM and SCM tracking per athlete and discipline
- Upsert logic: only overwrites an existing time when the new time is faster
- Date-stamped from the SESSION date in the results file (not the MEET element, which SPLASH does not populate)
- Automatic expiry: times older than 18 months (configurable via `BEST_TIME_MAX_AGE_MONTHS`) are purged when the registration page is opened; times with no date are never treated as expired

### Roles and access
| Role | Access |
|---|---|
| **admin** | Full access: all uploads, all exports, club/athlete CRUD, PIN management, set organizer, flush meet, invoices |
| **organizer** | A club coach designated by the admin. Can upload meet, set closure date, send invitations, connect Stripe, view/download invoices. Cannot edit other clubs' registrations. |
| **coach** | Own club only: view athletes, register for events. Blocked after the closure date. |

### Billing
- **Stripe Connect**: organizer connects their Stripe account via OAuth; invoices are sent through the connected account directly to each club's admin email
- **PDF fallback**: if Stripe is not connected, a reportlab PDF invoice is generated and downloadable from the UI
- Meet-level fees: CLUB × 1, ATHLETE × distinct registered athletes, RELAY × distinct relay events, TEAM / LATEFEE / LSCMEETFEE × 1
- Per-entry fees resolved from paired TIM/PRE event structure (fee lives on the TIM event, registrations on the PRE event)

### Email invitations
- Per-club one-time encrypted PIN link (7-day expiry, Fernet encrypted), delivered via Resend
- Bilingual invitation (FR/EN toggle per send)
- Invite-all: sends to every club that has an admin email configured

### Security
- Rate limiting on PIN auth: 5 attempts per IP per 60-second window
- PIN submitted in POST body (not URL or header on auth)
- No `/docs` or `/redoc` exposed
- `SECRET_KEY` validated at startup — app refuses to boot with the default placeholder
- CORS restricted to `APP_BASE_URL`

### Other
- Closure date: set by organizer; coaches cannot register or modify after the deadline
- Admin PIN: changeable via UI, stored in `app_config`, falls back to `.env` default
- Bulk PIN regeneration for all clubs
- Style names persisted independently of the meet file — Data Management page shows discipline names even when no meet is loaded
- Build timestamp displayed in the UI footer (`buildInfo.js` injected at build time)
- Bilingual UI: FR/EN toggle stored in localStorage; all strings go through `i18n.jsx`

## Stack

- **Backend**: Python 3.12 / FastAPI + SQLAlchemy 2.0 + PostgreSQL 16
- **Frontend**: React 18 + Vite + Tailwind CSS
- **Deploy**: Docker Compose (backend, frontend/nginx, postgres)
- **Email**: Resend API (via `httpx`)
- **Billing**: Stripe Connect + reportlab PDF invoices
- **Encryption**: Fernet (cryptography) for one-time PIN links

## Quick Start

```bash
cp .env.example .env
# Edit .env — at minimum set SECRET_KEY, ADMIN_PIN, and RESEND_API_KEY
docker compose up --build -d
```

- Frontend: http://localhost:8001
- Backend API: http://localhost:8000/api

## Environment Variables

| Variable | Description |
|---|---|
| `ADMIN_PIN` | Admin login PIN (default `314159`) |
| `SECRET_KEY` | Fernet key for encrypting PINs in one-time links — **must be changed** |
| `RESEND_API_KEY` | Resend API key for email delivery |
| `RESEND_FROM_EMAIL` | Sender address (must be verified in Resend) |
| `APP_BASE_URL` | Public frontend URL, used in email links and CORS origin |
| `STRIPE_API_KEY` | Stripe secret key for invoice generation |
| `BEST_TIME_MAX_AGE_MONTHS` | Best-time expiry in months (default `18`) |

## Workflow

See `docs/workflow_en.md` / `docs/workflow_fr.md` for the full end-to-end guide with screenshots.

1. **Before the meet**: export entries .lxf from SPLASH → upload to app (imports clubs, athletes, best times)
2. **Meet setup**: export meet invitation .lxf from SPLASH → upload to app (loads events, fees, sessions); app regenerates all club PINs
3. **Invitations**: admin designates organizer; organizer sends PIN invitation emails to all team admins
4. **Registration**: team admins log in with their PIN, register athletes for events and categories; best times pre-fill entry times
5. **Export**: admin downloads the registrations bundle (.zip) → imports registrations .lxf into SPLASH
6. **Meet day**: use `simulate_results.bat` / `simulate_results.vbs` from the bundle to simulate results in SPLASH
7. **After meet**: export results .lxf from SPLASH → upload to app (updates best times for all athletes)
8. **Billing**: organizer connects Stripe, sends invoices per club; or downloads PDF invoices

## SPLASH configuration checklist

Before exporting any file from SPLASH, make sure the fields below are set. Missing or incorrect values lead to silent failures in the import (wrong fees, athletes skipped, best times lost on first page load, etc.).

### Meet file

| SPLASH setting | What breaks if missing |
|---|---|
| Meet name | Displayed throughout the UI and stored in app config |
| Pool type (LCM / SCM) | Defaults to LCM; wrong value means entry times show in the wrong column |
| Masters flag | Masters events and category are hidden for all athletes |
| Fee types and amounts | Invoice items are missing or zero |
| Fee currency | Invoice currency defaults to nothing |
| Per-event fees on timing events | Per-entry invoice lines are zero |
| Age groups on every event | Age category dropdown has no valid options for the event |

### Entries file

This file imports clubs, athletes, and entry-time best times in a single pass.

| SPLASH setting | What breaks if missing |
|---|---|
| Club code (exact) | Club is not matched; a duplicate may be created on re-import |
| Club name and nation | Cosmetic only, but kept in sync on every import |
| Club contact email | Admin cannot receive PIN invitation emails |
| Athlete first and last name | Athlete cannot be matched; duplicate created |
| Athlete gender | Defaults to M for newly created athletes |
| Athlete birthdate | Age category cannot be computed; athlete placed in wrong group |
| Athlete license number | Primary key for matching across files — without it, re-imports create duplicates |
| Masters exception flag | Masters-eligible athletes are not auto-placed in Masters category |
| Entry times | Best times not imported from the entries file |
| Entry course per event | Entry time assigned to wrong pool length (LCM vs SCM) |

### Results file

| SPLASH setting | What breaks if missing |
|---|---|
| **Session date** (set on each session, not the meet) | Without a date, all imported best times get today as a fallback — acceptable, but imprecise. The date must be set per session; SPLASH does not export a date at the meet level. |
| Pool type (LCM / SCM) | All times stored under the wrong course |
| Athlete license number | Falls back to name matching; unmatched athletes are skipped (time lost) |
| Swim time on each result | No time to import |
| Relay roster (relay positions with athlete assignments) | Relay time not credited to individual athletes |

## Swiss Timing Quantum setup (meet day)

On meet day the timing crew runs Swiss Timing Quantum to control touchpads and the scoreboard. Lenex `stroke` is a fixed enum with no slot for lifesaving disciplines, so events imported into Quantum from a SPLASH-exported `.lxf` show **UNKNOWN** in the Style column until a custom style is assigned.

`quantum/LSTSTYLE.en-UK` is a seed file that pre-populates Quantum's style list with the lifesaving disciplines (Sauv. Combiné/Rescue Medley, Sauveteur Acier/Superlifesaver, Obstacle, Relais Obstacle, etc.) so every new Quantum session starts with the right styles available.

### Install on the timing laptop

1. On the timing laptop, locate Quantum's defaults folder. Default install path:
   ```
   C:\SwissTiming\DRC64App\Quantum\Swimming\Defaults\
   ```
2. Back up the existing file before overwriting:
   ```
   copy LSTSTYLE.en-UK LSTSTYLE.en-UK.bak
   ```
3. Copy `quantum/LSTSTYLE.en-UK` from this repo into that folder, replacing the original.
4. Restart Quantum if it is running. The new styles will appear in **new** sessions/meets created after the file is in place — existing sessions keep whatever styles they already have.

Notes:
- File format is ISO-8859 (Latin-1) with CRLF line endings — keep it as-is. Do not re-save it through a UTF-8 editor or accented characters will break.
- A Quantum software update may overwrite the Defaults folder. Keep the `.bak` copy and re-deploy the repo file after updating.
- If the timing crew uses a different display language (`fr-CH`, `de-CH`, etc.), copy the same content into the matching `LSTSTYLE.<lang>` file in the same folder.

## Troubleshooting

### Reset forgotten admin PIN

If the admin PIN was changed via the UI and forgotten, reset it to the `.env` default:

```bash
docker compose exec db psql -U postgres meetmanager -c "DELETE FROM app_config WHERE key='admin_pin';"
```

The app will fall back to the `ADMIN_PIN` value from `.env`.

## Testing

```bash
cd tests && pip install -r requirements-test.txt && pytest test_integration.py
```

Tests hit a real PostgreSQL instance — do not mock the database.

## Structure

```
meetmanager-app/
├── backend/
│   └── app/
│       ├── main.py            # FastAPI app entry, CORS, DB init, startup checks
│       ├── models.py          # Club, Athlete, Event, AgeGroup, Registration, BestTime, SecretLink, AppConfig
│       ├── database.py        # DB engine, get_db dependency
│       ├── routers/api.py     # All endpoints, PIN auth, rate limiting
│       ├── meet_parser.py     # Parse SPLASH meet .lxf → ParsedMeet dataclass
│       ├── events.py          # Load ParsedMeet events into DB
│       ├── seed.py            # Import clubs + athletes from Lenex entries .lxf
│       ├── best_times.py      # Import best times from Lenex entries/results .lxf
│       ├── export.py          # Generate registrations .lxf (Lenex output)
│       ├── export_entries.py  # Generate entries .lxf (clubs + athletes + best times)
│       └── invoices.py        # Stripe invoices + PDF generation (reportlab)
│   └── scripts/
│       ├── simulate_results.bat  # Windows launcher for VBS script
│       └── simulate_results.vbs  # Simulate results in SPLASH (included in export .zip)
├── frontend/src/
│   ├── main.jsx               # React entry, router, nav (role-based visibility)
│   ├── i18n.jsx               # Bilingual (fr/en) translations via LangProvider / useLang()
│   ├── api.js                 # Axios instance (base /api)
│   ├── pages/
│   │   ├── Admin.jsx          # Admin panel: uploads, exports, invoices, organizer, flush meet
│   │   ├── Organizer.jsx      # Organizer panel: meet upload, closure date, fee summary, invites, Stripe, PDF download
│   │   ├── Athletes.jsx       # Club coach view: athlete list
│   │   ├── Register.jsx       # Per-athlete event registration with best time columns
│   │   ├── Login.jsx          # PIN entry
│   │   └── Secret.jsx         # One-time PIN reveal page (/secret/:token)
│   └── buildInfo.js           # Build timestamp injected at build time
├── quantum/
│   └── LSTSTYLE.en-UK         # Swiss Timing Quantum style seed file
├── docs/                      # Workflow screenshots and PDFs
├── tests/                     # Integration tests (real PostgreSQL)
└── docker-compose.yml
```
