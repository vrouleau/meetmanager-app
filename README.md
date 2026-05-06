# Meet Manager App

Full-stack webapp for lifesaving meet registration management.

## Stack
- **Backend**: Python FastAPI + SQLAlchemy + PostgreSQL
- **Frontend**: React (Vite) + TailwindCSS
- **Export**: MDB/Lenex generation (reuses ebimport_splash logic)
- **Deploy**: Docker Compose

## Structure
```
meetmanager-app/
├── backend/          # FastAPI app
│   ├── app/
│   │   ├── models.py     # SQLAlchemy models
│   │   ├── schemas.py    # Pydantic schemas
│   │   ├── crud.py       # DB operations
│   │   ├── routers/      # API endpoints
│   │   ├── export.py     # MDB/Lenex generation
│   │   └── main.py       # App entry
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/         # React app
│   ├── src/
│   ├── package.json
│   └── Dockerfile
└── docker-compose.yml
```
