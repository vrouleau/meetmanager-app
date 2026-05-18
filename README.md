# SplashTeam

[![CI](https://github.com/vrouleau/sauvetageteam/actions/workflows/ci.yml/badge.svg)](https://github.com/vrouleau/sauvetageteam/actions/workflows/ci.yml)

Web-based registration management for lifesaving competitions. Integrates with SPLASH Meet Manager via Lenex (.lxf) import/export and uses a Splash-compatible PostgreSQL schema.

## Features

### Imports
- **Meet file** — loads event structure, sessions, age groups, fees, and pool type (LCM/SCM) from a SPLASH-exported .lxf; replaces the previous meet and resets all registrations
- **Entries file** — imports clubs, athletes, and entry-time best times from a Lenex entries .lxf in a single pass; also loads event structure if no meet has been uploaded yet
- **Results file** — imports best times from a SPLASH results .lxf; reads session dates, both individual and relay times; credits relay times to every team member

### Exports
- **Registrations bundle** — .zip with a Lenex registrations .lxf (correct SPLASH event/age-group IDs) plus `simulate_results.bat` and `simulate_results.vbs` for meet-day use
- **Entries .lxf** — all clubs, athletes, and best times exported as a Lenex entries file for backup or re-import
- **Meet template .smb** — download the SPLASH meet template; preserves combined-event definitions that Lenex exports omit

### Registration
- Per-athlete event registration with age category dropdown (10−, 11−12, 13−14, 15−18, Open, Masters)
- ±1 age group selection: athlete can register in their natural category or one step above/below
- Age computed against December 31 of the meet year
- Entry time pre-filled from the athlete's best time for the meet's pool length (LCM/SCM)
- NT (no time) registrations supported
- Relay lock: one team per club per relay event

### Best times
- Stored as JSON in `bsglobal` table (keyed by athlete ID)
- Separate LCM and SCM tracking per athlete and discipline
- Upsert logic: only overwrites when the new time is faster
- Date-stamped from SESSION date in results files
- Automatic expiry: times older than 18 months (configurable) are purged on page load

### Roles and access
| Role | Access |
|---|---|
| **admin** | Full access: uploads, exports, club/athlete CRUD, PIN management, organizer designation, flush meet, invoices |
| **organizer** | Upload meet, set closure date, send invitations, connect Stripe, view/download invoices |
| **coach** | Own club only: view athletes, register for events. Blocked after closure date. |

### Billing
- **Stripe Connect**: organizer connects their Stripe account; invoices sent directly to each club
- **PDF fallback**: reportlab PDF invoices downloadable from the UI
- Meet-level and per-entry fees resolved from the meet structure

### Email invitations
- Per-club one-time encrypted PIN link (7-day expiry, Fernet), delivered via Resend
- Bilingual (FR/EN), invite-all, and self-invite support

### Security
- Rate limiting on PIN auth (5 attempts / 60s / IP)
- `SECRET_KEY` validated at startup
- CORS restricted to `APP_BASE_URL`
- Audit log for all mutating operations

## Stack

- **Backend**: Python 3.12 / FastAPI + SQLAlchemy 2.0 + PostgreSQL 16
- **Frontend**: React 19 + Vite 6 + Tailwind CSS 4 + React Router 7
- **Deploy**: Docker Compose (backend, frontend/nginx, postgres)
- **CI/CD**: GitHub Actions — tests on push, image builds on tag
- **Registry**: GitHub Container Registry (ghcr.io)

## Database Schema

Uses the **Splash Meet Manager PostgreSQL schema** — all tables and columns match the real Splash database. The app can coexist with Splash Meet Manager on the same database.

Core tables: `swimstyle`, `club`, `athlete`, `swimsession`, `swimevent`, `agegroup`, `swimresult`, `bsglobal`

Team-specific extra columns (ignored by Splash): `club.pin`, `club.email`, `club.stripe_account_id`, `swimresult.age_code`

## Quick Start (development)

```bash
cp .env_template .env
# Edit .env — set SECRET_KEY and ADMIN_PIN at minimum
docker compose up --build -d
```

- Frontend: http://localhost:8001
- Backend API: http://localhost:8000/api
- Admin PIN: value from `.env` (default `314159`)

## Production Deployment

Images are published to ghcr.io on every tagged release.

```bash
# On the server:
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

## Releasing

```bash
git tag v2.1.0
git push origin v2.1.0
```

GitHub Actions will:
1. Run integration tests
2. Build backend + frontend Docker images
3. Push to `ghcr.io/vrouleau/sauvetageteam-backend:2.1.0` and `:latest`
4. Push to `ghcr.io/vrouleau/sauvetageteam-frontend:2.1.0` and `:latest`

## Testing

```bash
# Tests run against a real Docker stack
pip install -r tests/requirements-test.txt
pytest tests/ -v
```

Tests bring up the full stack (postgres + backend + frontend), upload fixtures, and exercise all API endpoints.

## Environment Variables

| Variable | Description |
|---|---|
| `ADMIN_PIN` | Admin login PIN (default `314159`) |
| `SECRET_KEY` | Fernet key for PIN encryption — **must be changed** |
| `RESEND_API_KEY` | Resend API key for email delivery |
| `RESEND_FROM_EMAIL` | Sender address (verified in Resend) |
| `APP_BASE_URL` | Public frontend URL (email links + CORS) |
| `STRIPE_API_KEY` | Stripe secret key for invoices |
| `TURNSTILE_SITE_KEY` | Cloudflare Turnstile public key |
| `TURNSTILE_SECRET_KEY` | Cloudflare Turnstile secret key |
| `MEET_TEMPLATE` | Path to meet template `.smb` (default `/app/templates/meet.smb`) |
| `BEST_TIME_MAX_AGE_MONTHS` | Best-time expiry in months (default `18`) |

## Structure

```
sauvetageteam/
├── backend/app/
│   ├── main.py            # FastAPI entry, CORS, startup
│   ├── models.py          # SQLAlchemy models (Splash-compatible schema)
│   ├── database.py        # DB engine + session
│   ├── routers/api.py     # All API endpoints
│   ├── meet_parser.py     # Parse SPLASH meet .lxf
│   ├── events.py          # Load events into DB
│   ├── seed.py            # Import clubs + athletes from Lenex
│   ├── best_times.py      # Best times (JSON in bsglobal)
│   ├── export.py          # Generate registrations .lxf
│   ├── export_entries.py  # Generate entries .lxf
│   └── invoices.py        # Stripe + PDF invoices
├── frontend/src/
│   ├── main.jsx           # App shell, router, nav
│   ├── i18n.jsx           # FR/EN translations
│   ├── api.js             # HTTP client
│   └── pages/             # Athletes, Register, Admin, Organizer, DataManagement, Login, ...
├── tests/                 # Integration tests
├── .github/workflows/
│   ├── ci.yml             # Tests on push/PR
│   └── release.yml        # Build + push images on tag
├── docker-compose.yml     # Development
├── docker-compose.prod.yml # Production (pulls from ghcr.io)
└── docker-compose.test.yml # Test overrides
```

## Troubleshooting

### Reset forgotten admin PIN

```bash
docker compose exec db psql -U meetmgr meetmgr -c "DELETE FROM bsglobal WHERE name='admin_pin';"
```

The app falls back to the `ADMIN_PIN` value from `.env`.
