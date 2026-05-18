# SplashTeam — AI Context

## What this app is
Web-based registration portal for lifesaving competitions. Coaches log in with a PIN, register athletes for events, and manage entry times. Integrates with SPLASH Meet Manager via Lenex (.lxf) import/export.

## How to run
```bash
cp .env_template .env   # set SECRET_KEY
docker compose up --build -d
# Frontend: http://localhost:8001  Admin PIN: 314159
```

## Stack
- **Backend**: Python 3.12 / FastAPI + SQLAlchemy 2.0 + PostgreSQL 16
- **Frontend**: React 19 + Vite 6 + Tailwind CSS 4 + React Router 7
- **Deploy**: Docker Compose (backend uvicorn, frontend nginx, postgres)
- **CI/CD**: GitHub Actions → ghcr.io (tag-triggered)

## Database Schema

Uses the **full Splash Meet Manager PostgreSQL schema** — every column matches the real Splash database so the app can coexist with Splash on the same DB.

### Core tables
| Table | Purpose |
|---|---|
| `swimstyle` | Stroke/distance definitions (swimstyleid PK) |
| `club` | Teams/clubs (clubid PK) + extra: pin, email, stripe_account_id |
| `athlete` | Competitors (athleteid PK, FK→club) |
| `swimsession` | Competition sessions |
| `swimevent` | Events (FK→swimsession, FK→swimstyle) |
| `agegroup` | Age categories per event (FK→swimevent) |
| `swimresult` | Entries/results (FK→athlete, FK→swimevent) |
| `bsglobal` | Key-value config (name PK, data TEXT) |
| `secret_links` | One-time PIN reveal links (team-specific) |

### Registration model
A registration = a `swimresult` row. Key fields:
- `athleteid` — who
- `swimeventid` — which event
- `agegroupid` — which age category (nullable)
- `entrytime` — entry time in ms (NULL = NT, still a valid registration)
- `swimtime` — result time (NULL = not swum yet)
- `qttime/qtcourse/qtdate/qtname` — qualifying time from previous meet
- `age_code` — team-specific: "10-", "11-12", "13-14", "15-18", "Open", "Masters"

### Best times storage
Stored as JSON in `bsglobal` rows keyed `bt_{athlete_id}`:
```json
{"506": {"LCM": {"time_ms": 65430, "source": "results.lxf", "date": "2025-03-15"}}}
```

### Key encoding conventions
- Gender: 1=M, 2=F, 3=Mixed (smallint)
- Course: 1=LCM(50m), 2=SCY(25yd), 3=SCM(25m)
- Round: 1=PRE, 2=SEM, 4=FIN, 5=TIM/DirectFinal
- Times: integer milliseconds
- Booleans: char(1) 'T'/'F'
- Fee: double precision (dollars) on swimevent

### Team-specific columns (not in Splash)
- `club.pin`, `club.email`, `club.stripe_account_id`, `club.invite_send_count`, `club.stripe_send_count`
- `swimresult.age_code`, `swimresult.created_at`
- `athlete.exception` ('X' for Masters)

## Project structure
```
backend/app/
  main.py            — FastAPI app, CORS, startup, audit middleware
  models.py          — SQLAlchemy models (full Splash schema + extras)
  database.py        — Engine + get_db()
  routers/api.py     — All endpoints (~1200 lines)
  meet_parser.py     — Parse .lxf → ParsedMeet dataclass
  events.py          — Load events from ParsedMeet into DB
  seed.py            — Import clubs + athletes from Lenex
  best_times.py      — Best times (JSON in bsglobal, import from Lenex)
  export.py          — Generate registrations .lxf
  export_entries.py  — Generate entries .lxf (clubs + athletes + BT)
  invoices.py        — Stripe Connect + PDF invoices

frontend/src/
  main.jsx           — App shell (dark title bar, tab nav, file menu)
  i18n.jsx           — FR/EN translations
  api.js             — fetch wrapper with X-Club-Pin header
  pages/
    Athletes.jsx     — Compact table, club filter, inline add
    Register.jsx     — Athlete header + event tables (checkbox + times)
    Admin.jsx        — Uploads, PIN mgmt, organizer, club CRUD
    Organizer.jsx    — Meet upload, closure, invites, Stripe, fees
    DataManagement.jsx — Club/style merge, entries export
    Login.jsx        — PIN dialog
    Secret.jsx       — One-time PIN reveal
    SelfInvite.jsx   — Public self-invite
```

## API contract (key endpoints)

| Endpoint | Returns |
|---|---|
| `POST /api/auth` | `{role, club_id, club_name}` |
| `GET /api/athletes` | `[{id, first_name, last_name, gender, birthdate, license, club, club_id}]` |
| `GET /api/clubs` | `[{id, name, code, athlete_count, pin?, email?, ...}]` |
| `GET /api/events` | `[{id, style_uid, style_name, distance, relay_count, gender, event_number, round, masters}]` |
| `GET /api/athletes/{id}/registration` | `{athlete, suggested_age_code, meet_course, individual_events, relay_events, club_athletes}` |
| `POST /api/registrations` | `{id, updated}` — body: `{athlete_id, event_id, age_code, entry_time_ms}` |
| `DELETE /api/registrations/{id}` | `{deleted: true}` |
| `GET /api/status` | `{clubs, athletes, events, registrations, best_times}` |

## Business rules
- **±1 age group**: athlete can register in natural category ±1 step (frontend enforces)
- **Relay lock**: one athlete per club per relay event (backend enforces, returns 409)
- **Closure date**: coaches blocked after deadline (admin/organizer bypass)
- **NT registrations**: entry_time_ms=NULL is valid — row existence = registration
- **Best time expiry**: times older than BEST_TIME_MAX_AGE_MONTHS purged on page load

## Testing
```bash
pip install -r tests/requirements-test.txt
pytest tests/ -v   # 80 integration tests, hits real Docker stack
```

## Releasing
```bash
git tag v2.1.0 && git push origin v2.1.0
# GitHub Actions: test → build → push to ghcr.io
```

## UI style
Matches sauvetagemeet (SplashMeet desktop app):
- Dark gray-800 title bar + gray-700 tab navigation
- Compact text-xs data tables with sticky headers
- Modal dialogs (gray-700 header, white body)
- Tailwind utility classes throughout
