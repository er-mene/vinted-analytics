from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List
import json
import logging
import threading
from datetime import datetime
from apscheduler.jobstores.base import JobLookupError
from app.db.database import (
    create_monitor,
    get_monitor,
    update_monitor,
    save_listings,
    get_monitors_list,
    delete_monitor,
    get_monitor_analytics,
    get_monitors_with_stats,
    get_verification_queue_summary,
    get_verification_queue_items,
    clear_verification_queue,
    get_recent_items,
    get_listings,
    update_monitor_last_scrape,
    scheduler,
)
from app.services.vinted_service import search_vinted

router = APIRouter()
logger = logging.getLogger(__name__)
MIN_MONITOR_INTERVAL_SECONDS = 30 * 60

_run_locks: dict[int, threading.Lock] = {}
_run_locks_guard = threading.Lock()

_progress: dict[int, dict] = {}
_progress_guard = threading.Lock()


def _set_progress(monitor_id: int, current: int, total: int):
    with _progress_guard:
        _progress[monitor_id] = {"current": current, "total": total}


def _get_progress(monitor_id: int) -> dict | None:
    with _progress_guard:
        return _progress.get(monitor_id)


def _clear_progress(monitor_id: int):
    with _progress_guard:
        _progress.pop(monitor_id, None)


def _monitor_lock(monitor_id: int) -> threading.Lock:
    with _run_locks_guard:
        if monitor_id not in _run_locks:
            _run_locks[monitor_id] = threading.Lock()
        return _run_locks[monitor_id]


def _clear_run_lock(monitor_id: int):
    with _run_locks_guard:
        _run_locks.pop(monitor_id, None)


def _normalize_monitor_interval(days: int, hours: int, minutes: int, seconds: int) -> tuple[int, int, int, int]:
    total_seconds = days * 86400 + hours * 3600 + minutes * 60 + seconds
    if total_seconds == 0:
        total_seconds = 10 * 60
    if total_seconds < MIN_MONITOR_INTERVAL_SECONDS:
        total_seconds = MIN_MONITOR_INTERVAL_SECONDS

    normalized_days, remainder = divmod(total_seconds, 86400)
    normalized_hours, remainder = divmod(remainder, 3600)
    normalized_minutes, normalized_seconds = divmod(remainder, 60)
    return normalized_days, normalized_hours, normalized_minutes, normalized_seconds


def _pearson_correlation(points: List[tuple[float, float]]) -> Optional[float]:
    if len(points) < 2:
        return None

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)

    numerator = sum((x - mean_x) * (y - mean_y) for x, y in points)
    denominator_x = sum((x - mean_x) ** 2 for x in xs) ** 0.5
    denominator_y = sum((y - mean_y) ** 2 for y in ys) ** 0.5
    if denominator_x == 0 or denominator_y == 0:
        return None
    return round(numerator / (denominator_x * denominator_y), 4)


TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def _build_dashboard_html(monitor_id: int) -> str:
    template = (TEMPLATES_DIR / "monitor_dashboard.html").read_text(encoding="utf-8")
    return template.replace("{{monitor_id}}", str(monitor_id))

class MonitorCreate(BaseModel):
    name: str
    query: str
    brand_id: Optional[int] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    status_ids: List[int] = []
    days: int = 0
    hours: int = 0
    minutes: int = 0
    seconds: int = 0
    max_pages: Optional[int] = None
    page_delay_seconds: float = 6.0
    search_time_seconds: int = 5184000
    max_age: float = 7.0
    interval_days: int = 0
    interval_hours: int = 0
    interval_minutes: int = 30
    interval_seconds: int = 0

@router.get("/")
def show_monitors():
    """Shows the existing monitors"""
    return get_monitors_list()

@router.post("/monitor")
def add_monitor(monitor: MonitorCreate):
    """Creates a new tracked search."""
    interval_days, interval_hours, interval_minutes, interval_seconds = _normalize_monitor_interval(
        monitor.days,
        monitor.hours,
        monitor.minutes,
        monitor.seconds,
    )

    page_delay = max(monitor.page_delay_seconds or 6.0, 5.0)

    id = create_monitor(
        monitor.name, monitor.query, monitor.brand_id,
        monitor.min_price, monitor.max_price, monitor.status_ids,
        monitor.max_pages, page_delay, monitor.search_time_seconds,
        monitor.max_age,
        interval_days, interval_hours, interval_minutes, interval_seconds,
    )
    
    scheduler.add_job(
        run_monitor,
        "interval",
        days=interval_days,
        hours=interval_hours,
        minutes=interval_minutes,
        seconds=interval_seconds,
        args=[id],
        id=str(id),
        replace_existing=True,
        next_run_time=datetime.now(),
        jitter=300,
        max_instances=1,
        misfire_grace_time=None,
        coalesce=True,
    )
    return {
        "message": "Monitor started",
        "monitor_id": id,
        "effective_interval": {
            "days": interval_days,
            "hours": interval_hours,
            "minutes": interval_minutes,
            "seconds": interval_seconds,
            "minimum_interval_seconds": MIN_MONITOR_INTERVAL_SECONDS,
        },
    }

@router.patch("/monitor/stop")
def pause_monitor(monitor_id: int):
    if not get_monitor(monitor_id): 
        raise HTTPException(status_code=404, detail="Monitor not found")
    scheduler.pause_job(f"{monitor_id}")
    return {"message": "Monitor paused", "monitor_id": monitor_id}

@router.patch("/monitor/resume")
def resume_monitor(monitor_id: int):
    if not get_monitor(monitor_id):
        raise HTTPException(status_code=404, detail="Monitor not found")
    scheduler.resume_job(f"{monitor_id}")
    return {"message": "Monitor resumed", "monitor_id": monitor_id}

# Need to move run_monitor here.
@router.get("/monitor/{monitor_id}/run")
def run_monitor(monitor_id: int):
    """
    Runs the specific monitor
    """
    lock = _monitor_lock(monitor_id)
    if not lock.acquire(blocking=False):
        msg = f"Monitor {monitor_id} is already running, skipping this invocation"
        logger.warning(msg)
        return {"message": msg}
    try:
        m = get_monitor(monitor_id)
        if not m:
            raise HTTPException(status_code=404, detail="Monitor not found")
            
        status_ids = json.loads(m["status_ids"])
        max_pages = m.get("max_pages")
        page_delay_seconds = max(m.get("page_delay_seconds") or 6.0, 5.0)
        max_age = m.get("max_age") or 7.0
        search_time_seconds = min(m.get("search_time_seconds") or 5184000, int(max_age * 86400))
        
        print(f"🔄 Running Monitor: {m['name']}...")

        def progress_cb(current: int, total: int):
            _set_progress(monitor_id, current, total)

        _set_progress(monitor_id, 0, 1)
        items = search_vinted(
            query=m["query"],
            brand_id=m["brand_id"],
            min_price=m["min_price"],
            max_price=m["max_price"],
            status_ids=status_ids,
            max_pages=max_pages,
            page_delay_seconds=page_delay_seconds,
            search_time_seconds=search_time_seconds,
            progress_callback=progress_cb,
        )

        new_count = save_listings(monitor_id, items, max_pages)
        update_monitor_last_scrape(monitor_id)

        avg_price = 0
        if items:
            total = sum(i['price'] for i in items)
            avg_price = round(total / len(items), 2)
        
        return {
            "monitor": m["name"],
            "new_items_found": new_count,
            "current_avg_price": avg_price,
            "total_active_scraped": len(items),
            "items": items
        }
    except Exception as e:
        logger.exception(f"Job {monitor_id} failed: {e}")
        raise
    finally:
        _clear_progress(monitor_id)
        lock.release()


@router.get("/monitor/{monitor_id}/progress")
def monitor_progress(monitor_id: int):
    p = _get_progress(monitor_id)
    if p is None:
        return {"current": 0, "total": 0, "running": False}
    return {**p, "running": True}


@router.get("/monitor/{monitor_id}/analytics")
def monitor_analytics(monitor_id: int):
    analytics = get_monitor_analytics(monitor_id)
    if not analytics:
        raise HTTPException(status_code=404, detail="Monitor not found")

    price_likes_points = [
        (float(item["price"]), float(item["likes"]))
        for item in analytics["price_likes"]
        if item["price"] is not None and item["likes"] is not None
    ]
    sell_speed_points = [
        (float(item["price"]), float(item["hours_to_sell"]))
        for item in analytics["sell_speed"]
        if item["price"] is not None and item["hours_to_sell"] is not None
    ]

    analytics["correlations"] = {
        "price_likes": _pearson_correlation(price_likes_points),
        "price_sell_time": _pearson_correlation(sell_speed_points),
    }
    return analytics


@router.get("/monitor/{monitor_id}/listings")
def monitor_listings(monitor_id: int, sort_by: str = "likes", order: str = "desc", limit: int = 200, offset: int = 0):
    if not get_monitor(monitor_id):
        raise HTTPException(status_code=404, detail="Monitor not found")
    return JSONResponse(
        get_listings(monitor_id, sort_by=sort_by, order=order, limit=limit, offset=offset),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )

@router.get("/monitor/{monitor_id}/dashboard", response_class=HTMLResponse)
def monitor_dashboard(monitor_id: int):
    if not get_monitor(monitor_id):
        raise HTTPException(status_code=404, detail="Monitor not found")
    return HTMLResponse(_build_dashboard_html(monitor_id))

@router.post("/monitor/delete")
def delete_monitor_from_db(monitor_id: int):
    delete_monitor(monitor_id)
    try:
        scheduler.remove_job(str(monitor_id))
    except JobLookupError:
        pass
    except Exception as e:
        logger.warning(f"Could not remove job for monitor {monitor_id} from scheduler: {e}")
    _clear_run_lock(monitor_id)
    _clear_progress(monitor_id)
    return {"message": f"Monitor {monitor_id} deleted"}


@router.put("/monitor/{monitor_id}")
def edit_monitor(monitor_id: int, monitor: MonitorCreate):
    existing = get_monitor(monitor_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Monitor not found")

    interval_days, interval_hours, interval_minutes, interval_seconds = _normalize_monitor_interval(
        monitor.days,
        monitor.hours,
        monitor.minutes,
        monitor.seconds,
    )

    page_delay = max(monitor.page_delay_seconds, 5.0) if monitor.page_delay_seconds is not None else None

    update_monitor(
        monitor_id=monitor_id,
        name=monitor.name,
        query=monitor.query,
        brand_id=monitor.brand_id,
        min_price=monitor.min_price,
        max_price=monitor.max_price,
        status_ids=monitor.status_ids,
        max_pages=monitor.max_pages,
        page_delay_seconds=page_delay,
        search_time_seconds=monitor.search_time_seconds,
        max_age=monitor.max_age,
        interval_days=interval_days,
        interval_hours=interval_hours,
        interval_minutes=interval_minutes,
        interval_seconds=interval_seconds,
    )

    scheduler.reschedule_job(
        str(monitor_id),
        trigger="interval",
        days=interval_days,
        hours=interval_hours,
        minutes=interval_minutes,
        seconds=interval_seconds,
    )

    return {
        "message": "Monitor updated",
        "monitor_id": monitor_id,
        "effective_interval": {
            "days": interval_days,
            "hours": interval_hours,
            "minutes": interval_minutes,
            "seconds": interval_seconds,
        },
    }


# ── JSON endpoints ──────────────────────────────────────────────────────────


@router.get("/overview")
def overview():
    monitors = get_monitors_with_stats()
    jobs = {j.id: j for j in scheduler.get_jobs()}
    for m in monitors:
        j = jobs.get(str(m["id"]))
        m["next_run_time"] = str(j.next_run_time) if j and j.next_run_time else None
        m["paused"] = j and j.next_run_time is None
    return JSONResponse(
        {"monitors": monitors, "queue": get_verification_queue_summary()},
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@router.get("/queue")
def queue_items():
    summary = get_verification_queue_summary()
    items = get_verification_queue_items()
    return JSONResponse(
        {**summary, "items": items},
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@router.post("/queue/clear")
@router.delete("/queue")
def clear_queue_items():
    deleted = clear_verification_queue()
    return {"message": "Verification queue cleared", "deleted": deleted}


@router.get("/monitor/{monitor_id}/top")
def monitor_top_items(monitor_id: int):
    if not get_monitor(monitor_id):
        raise HTTPException(status_code=404, detail="Monitor not found")
    return JSONResponse(
        get_recent_items(monitor_id, limit=10),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


# ── HTML helpers ─────────────────────────────────────────────────────────────


def _build_overview_html() -> str:
    return (TEMPLATES_DIR / "overview_dashboard.html").read_text(encoding="utf-8")


def _build_queue_html() -> str:
    return (TEMPLATES_DIR / "queue_dashboard.html").read_text(encoding="utf-8")


# ── HTML endpoints ───────────────────────────────────────────────────────────


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(_build_overview_html())


@router.get("/queue/dashboard", response_class=HTMLResponse)
def queue_dashboard():
    return HTMLResponse(_build_queue_html())
