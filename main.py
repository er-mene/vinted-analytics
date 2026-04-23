from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging
from app.db.database import init_db, scheduler
from app.api import router as api_router
from app.api.endpoints import run_monitor
from app.tasks.verification_worker import verification_worker

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.start()
    verification_worker.start()
    yield
    verification_worker.stop()
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)
app.include_router(api_router, prefix="/api")

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
