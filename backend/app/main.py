"""FastAPI application entry point."""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import engine, SessionLocal
from .models import Base
from .events import load_events
from .routers.api import router

app = FastAPI(title="Meet Manager")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
def startup():
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
