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
├── docker-compose.yml
└── .env.example
```
