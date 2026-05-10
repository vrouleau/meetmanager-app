# Meet Manager App

[![CI](https://github.com/vrouleau/meetmanager-app/actions/workflows/ci.yml/badge.svg)](https://github.com/vrouleau/meetmanager-app/actions/workflows/ci.yml)

Web-based registration management for lifesaving competitions. Integrates with SPLASH Meet Manager via Lenex (.lxf) import/export.

## Features

- **Upload-driven**: meet .lxf (events), entries .lxf (clubs + athletes), results .lxf (best times)
- **PIN-based access**: 6-digit PIN per club, admin PIN (changeable)
- **Registration**: editable athlete info, category dropdown (15-18 / Open / Masters), best time columns (50m + 25m), entry time pre-filled from meet pool size
- **Masters support**: conditional — only shown when meet has masters flag
- **Lenex export**: generates .lxf with correct SPLASH event IDs
- **Best times**: separate LCM/SCM tracking, considers entry time vs result time (keeps fastest)
- **Email invites**: per-club admin email, one-time encrypted PIN link (7-day expiry), sent via Resend
- **Bilingual**: FR/EN toggle (localStorage persisted)
- **Security**: rate limiting, TLS-ready, PIN in POST body, no /docs exposed

## Stack

- **Backend**: Python FastAPI + SQLAlchemy + PostgreSQL
- **Frontend**: React (Vite) + TailwindCSS
- **Deploy**: Docker Compose (backend, frontend/nginx, postgres)
- **Email**: Resend API
- **Encryption**: Fernet (cryptography) for one-time PIN links

## Quick Start

```bash
cp .env.example .env
# Edit .env with your values (RESEND_API_KEY, etc.)
docker compose up --build -d
```

- Frontend: http://localhost:8001
- Backend API: http://localhost:8000/api

## Environment Variables

See `.env.example`:

| Variable | Description |
|----------|-------------|
| `ADMIN_PIN` | Admin login PIN |
| `RESEND_API_KEY` | Resend API key for email delivery |
| `RESEND_FROM_EMAIL` | Sender email (must be verified in Resend) |
| `APP_BASE_URL` | Public frontend URL (used in email links) |
| `SECRET_KEY` | Key for encrypting PINs in one-time links |

## Workflow

See `docs/workflow_en.md` / `docs/workflow_fr.md` for the full end-to-end guide with screenshots.

1. Export meet invitation from SPLASH → upload to app
2. Send PIN invitations to team admins
3. Team admins register athletes (events, categories, times)
4. Admin exports registrations → import into SPLASH
5. After meet: export results from SPLASH → upload to update best times

## Swiss Timing Quantum setup (meet day)

On meet day the timing crew runs Swiss Timing Quantum to control touchpads and the scoreboard. Lenex `stroke` is a fixed enum that has no slot for lifesaving disciplines, so events imported into Quantum from a SPLASH-exported `.lxf` show **UNKNOWN** in the Style column until a custom style is assigned.

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

## Structure

```
meetmanager-app/
├── backend/
│   └── app/
│       ├── models.py        # Club, Athlete, Event, Registration, BestTime, SecretLink
│       ├── routers/api.py   # All endpoints, PIN auth, rate limiting
│       ├── meet_parser.py   # Parse SPLASH meet .lxf
│       ├── seed.py          # Parse entries .lxf → clubs + athletes
│       ├── best_times.py    # Parse results .lxf → best times (LCM/SCM)
│       ├── events.py        # Load events from parsed meet
│       ├── export.py        # Generate Lenex .lxf with SPLASH event IDs
│       └── main.py          # FastAPI app entry
├── frontend/
│   └── src/
│       ├── pages/           # Login, Athletes, Register, Admin, Secret
│       ├── i18n.jsx         # FR/EN translations
│       └── buildInfo.js     # Build timestamp
├── docs/                    # Workflow guides + screenshots
├── quantum/                 # Swiss Timing Quantum seed files (LSTSTYLE.<lang>)
├── docker-compose.yml
└── .env.example
```
