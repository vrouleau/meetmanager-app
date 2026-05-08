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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
def startup():
    # Migrate best_times: add course column if missing
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "best_times" in insp.get_table_names():
        cols = [c["name"] for c in insp.get_columns("best_times")]
        if "course" not in cols:
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE best_times"))
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
