import os
import sys

_backend_dir = os.path.dirname(os.path.abspath(__file__))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging
from app.db.database import init_db
from app.api import router as api_router
from app.tasks.vinted_worker import vinted_worker

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    vinted_worker.start()
    yield
    vinted_worker.stop()

app = FastAPI(lifespan=lifespan)
app.include_router(api_router, prefix="/api")

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
