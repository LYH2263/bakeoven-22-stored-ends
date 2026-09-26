from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.services.migrate import backfill_batch_ends, ensure_batch_end_columns
from app.services.seed import seed_if_empty


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_batch_end_columns(engine)
    db = SessionLocal()
    try:
        backfill_batch_ends(db)
        if settings.seed_on_empty:
            seed_if_empty(db)
    finally:
        db.close()
    yield


app = FastAPI(title="BakeOven", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api")
