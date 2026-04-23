from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import json
import logging
from app.db.database import create_monitor, get_monitor, save_listings, get_monitors_list, delete_monitor, scheduler
from app.services.vinted_service import search_vinted

router = APIRouter()
logger = logging.getLogger(__name__)

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

@router.get("/")
def show_monitors():
    """Shows the existing monitors"""
    return get_monitors_list()

@router.post("/monitor")
def add_monitor(monitor: MonitorCreate):
    """Creates a new tracked search."""
    id = create_monitor(
        monitor.name, monitor.query, monitor.brand_id, 
        monitor.min_price, monitor.max_price, monitor.status_ids
    )

    if (monitor.days == monitor.hours == monitor.minutes == monitor.seconds == 0): 
        monitor.minutes = 10 
    
    scheduler.add_job(run_monitor, "interval", days=monitor.days, hours=monitor.hours, 
                      minutes=monitor.minutes, seconds=monitor.seconds, args=[id], id=f"{id}")
    return {"message": "Monitor started", "monitor_id": id}

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
    try:
        m = get_monitor(monitor_id)
        if not m:
            raise HTTPException(status_code=404, detail="Monitor not found")
            
        status_ids = json.loads(m["status_ids"])
        
        print(f"🔄 Running Monitor: {m['name']}...")
        items = search_vinted(
            query=m["query"],
            brand_id=m["brand_id"],
            min_price=m["min_price"],
            max_price=m["max_price"],
            status_ids=status_ids
        )

        new_count = save_listings(monitor_id, items)

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

@router.post("/monitor/delete")
def delete_monitor_from_db(monitor_id: int):
    delete_monitor(monitor_id)
    scheduler.remove_job(str(monitor_id))
    return {"message": f"Monitor {monitor_id} deleted"}
