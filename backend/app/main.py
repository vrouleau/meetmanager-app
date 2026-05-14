"""FastAPI application entry point."""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import engine, SessionLocal
from .models import Base
from .events import load_events
from .routers.api import router

app = FastAPI(title="Meet Manager", docs_url=None, redoc_url=None)

_cors_origin = os.environ.get("APP_BASE_URL", "http://localhost:8001")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_cors_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
def startup():
    # Refuse to start with the default insecure SECRET_KEY
    if os.environ.get("SECRET_KEY", "change-me-to-a-random-string") == "change-me-to-a-random-string":
        raise RuntimeError("SECRET_KEY must be changed from the default value")

    Base.metadata.create_all(bind=engine)

    # Load events from stored meet .lxf if available and events table is empty
    meet_path = Path(os.environ.get("MEET_STORAGE", "/app/data/meet.lxf"))
    if meet_path.exists():
        db = SessionLocal()
        try:
            count = load_events(db, meet_path)
            if count:
                print(f"Loaded {count} events from {meet_path}")
        finally:
            db.close()
