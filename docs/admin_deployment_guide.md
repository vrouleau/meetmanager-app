# Admin Deployment Guide

This guide walks through deploying Meet Manager from scratch on a Linux server with Docker.

## Prerequisites

- Linux server (Ubuntu 22.04+ recommended) with Docker and Docker Compose installed
- A domain name pointing to the server (e.g. `meetmanager.example.com`)
- A reverse proxy (Caddy, nginx, Traefik) handling HTTPS termination in front of port 8001

## 1. Clone the repository

```bash
git clone git@github.com:vrouleau/meetmanager-app.git
cd meetmanager-app
```

## 2. Create the `.env` file

```bash
cp .env_template .env
```

Edit `.env` and fill in every value. The sections below explain how to obtain each one.

### Required variables

| Variable | Description |
|----------|-------------|
| `ADMIN_PIN` | 6-digit PIN to log in as admin. Change from the default. |
| `SECRET_KEY` | Fernet encryption key for one-time PIN links. **Must be changed.** |
| `APP_BASE_URL` | Public URL of the frontend (e.g. `https://meetmanager.example.com`). Used in email links and CORS. |
| `DATABASE_URL` | Set automatically by docker-compose — do not override unless using an external DB. |

### Email (Resend)

| Variable | Description |
|----------|-------------|
| `RESEND_API_KEY` | API key from Resend |
| `RESEND_FROM_EMAIL` | Verified sender address in Resend |

### CAPTCHA (Cloudflare Turnstile)

| Variable | Description |
|----------|-------------|
| `TURNSTILE_SITE_KEY` | Public site key (rendered in the browser) |
| `TURNSTILE_SECRET_KEY` | Secret key (validated server-side) |

### Billing (Stripe) — optional

| Variable | Description |
|----------|-------------|
| `STRIPE_API_KEY` | Stripe secret key (`sk_test_...` or `sk_live_...`) |

### Other (optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `MEET_TEMPLATE` | `/app/templates/meet.smb` | Path to the SPLASH meet template served to organizers |
| `BEST_TIME_MAX_AGE_MONTHS` | `18` | Best times older than this are purged on page load |

## 3. Generate the SECRET_KEY

The key must be a valid Fernet key (base64-encoded 32-byte key):

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the output into `SECRET_KEY` in `.env`.

If you don't have `cryptography` installed locally:

```bash
docker run --rm python:3.12-slim sh -c "pip -q install cryptography && python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
```

## 4. Set up Resend (email delivery)

1. Create an account at https://resend.com
2. Add and verify your sending domain (DNS records: SPF, DKIM, DMARC)
3. Go to **API Keys** → create a new key with "Sending access"
4. Copy the key into `RESEND_API_KEY`
5. Set `RESEND_FROM_EMAIL` to an address on your verified domain (e.g. `noreply@meetmanager.example.com`)

## 5. Set up Cloudflare Turnstile (CAPTCHA)

Turnstile protects the public self-invite page from abuse. If left blank, the self-invite page works without CAPTCHA.

1. Log in to https://dash.cloudflare.com
2. Go to **Turnstile** in the sidebar
3. Click **Add site**
4. Enter your domain and choose **Managed** widget mode
5. Copy the **Site Key** → `TURNSTILE_SITE_KEY`
6. Copy the **Secret Key** → `TURNSTILE_SECRET_KEY`

## 6. Set up Stripe (optional — for invoicing)

If you want the organizer to send invoices via Stripe Connect:

1. Create a Stripe account at https://dashboard.stripe.com
2. Go to **Developers** → **API keys**
3. Copy the **Secret key** → `STRIPE_API_KEY`
4. For testing, use the `sk_test_...` key. Switch to `sk_live_...` for production.

The organizer will connect their own Stripe account via OAuth from the app UI.

## 7. Deploy

```bash
docker compose up --build -d
```

The app starts three containers:
- `db` — PostgreSQL 16
- `backend` — FastAPI (Python 3.12)
- `frontend` — nginx serving the React build on port 8001

Verify it's running:

```bash
docker compose ps
curl -s http://localhost:8001 | head -5
```

## 8. Reverse proxy (HTTPS)

The app listens on port 8001 (HTTP). Put a reverse proxy in front for HTTPS.

### Caddy (simplest)

```
meetmanager.example.com {
    reverse_proxy localhost:8001
}
```

### nginx

```nginx
server {
    listen 443 ssl;
    server_name meetmanager.example.com;

    ssl_certificate     /etc/letsencrypt/live/meetmanager.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/meetmanager.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 9. Verify deployment

1. Open `https://meetmanager.example.com` — you should see the login page
2. Enter the `ADMIN_PIN` — you should land on the admin panel
3. Upload a test meet file to confirm the backend and database work
4. Send a test invitation to verify Resend is configured correctly
5. Visit `/self-invite` to confirm Turnstile renders the CAPTCHA widget

## 10. Backups

The PostgreSQL data lives in a Docker volume (`pgdata`). Back it up regularly:

```bash
docker compose exec db pg_dump -U meetmgr meetmgr > backup_$(date +%Y%m%d).sql
```

Restore:

```bash
cat backup_20250101.sql | docker compose exec -T db psql -U meetmgr meetmgr
```

## 11. Updates

```bash
cd meetmanager-app
git pull
docker compose up --build -d
```

The database schema auto-migrates on startup (SQLAlchemy `create_all`).

## 12. Troubleshooting

### App refuses to start

Check logs:

```bash
docker compose logs backend
```

Common causes:
- `SECRET_KEY` is still the default placeholder → generate a real Fernet key
- Database not ready → the healthcheck should handle this, but check `docker compose logs db`

### Emails not sending

- Verify domain DNS records in Resend dashboard (SPF, DKIM)
- Check that `RESEND_FROM_EMAIL` uses the verified domain
- Check backend logs for Resend API errors

### Turnstile not showing

- Confirm `TURNSTILE_SITE_KEY` is set in `.env`
- The frontend container must be restarted after changing this value (it's injected at container start)

### Reset admin PIN

If the admin PIN was changed via the UI and forgotten:

```bash
docker compose exec db psql -U meetmgr meetmgr -c "DELETE FROM app_config WHERE key='admin_pin';"
```

The app falls back to the `ADMIN_PIN` value from `.env`.
