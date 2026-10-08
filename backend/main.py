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

class PollingEndpointFilter(logging.Filter):
    """Filters out high-frequency UI polling endpoints from uvicorn access logs."""

    EXCLUDED_PATTERNS = (
        "/api/overview",
        "/progress",
        "/top",
        "/queue",
        "/performance",
        "/dashboard",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        # Check uvicorn args format: (client_addr, method, full_path, http_version, status_code)
        if isinstance(record.args, tuple) and len(record.args) >= 5:
            path = str(record.args[2])
            status_code = record.args[4]
            if any(pattern in path for pattern in self.EXCLUDED_PATTERNS) and status_code in (200, 304):
                return False

        # Fallback check formatted message
        msg = record.getMessage()
        if any(pattern in msg for pattern in self.EXCLUDED_PATTERNS):
            if " 200 " in msg or " 304 " in msg or msg.endswith(" 200"):
                return False

        return True


def setup_access_log_filter():
    access_logger = logging.getLogger("uvicorn.access")
    filt = PollingEndpointFilter()
    access_logger.addFilter(filt)
    for handler in access_logger.handlers:
        handler.addFilter(filt)

    if os.getenv("UVICORN_ACCESS_LOG", "").lower() in ("0", "false", "no", "off"):
        access_logger.setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_access_log_filter()
    init_db()
    vinted_worker.start()
    yield
    vinted_worker.stop()

app = FastAPI(lifespan=lifespan)
app.include_router(api_router, prefix="/api")

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
setup_access_log_filter()

