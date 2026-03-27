from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
import json
import logging
from database import create_monitor, get_monitor, log_stats, get_monitor_history, save_listings, get_monitors_list
from vinted_service import search_vinted
from apscheduler.schedulers.background import BackgroundScheduler

DB_NAME = "vinted_data.db"
#TODO: grafico che mostra l'andamento del prezzo medio giornaliero e i nuovi annunci per un monitor specifico
app = FastAPI()
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()
scheduler.add_jobstore("sqlalchemy", url=f"sqlite:///{DB_NAME}")
scheduler.start()

class MonitorCreate(BaseModel):
    name: str
    query: str
    brand_id: Optional[int] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    status_ids: Optional[List[int]] = []
    days: Optional[int] = 0
    hours: Optional[int] = 0
    minutes: Optional[int] = 0
    seconds: Optional[int] = 0

@app.get("/")
def show_monitors():
    """Shows the existing monitors"""
    return get_monitors_list()

@app.post("/monitor")
def add_monitor(monitor: MonitorCreate = Depends()):
    """Creates a new tracked search."""
    id = create_monitor(
        monitor.name, monitor.query, monitor.brand_id, 
        monitor.min_price, monitor.max_price, monitor.status_ids
    )
    scheduler.add_job(run_monitor, "interval", days=monitor.days, hours=monitor.hours, 
                      minutes=monitor.minutes, seconds=monitor.seconds, args=[id], id=f"{id}")
    return {"message": "Monitor started", "monitor_id": id}

@app.patch("/monitor/stop")
def pause_monitor(monitor_id: int):
    if not get_monitor(monitor_id): 
        raise HTTPException(status_code=404, detail="Monitor not found")
    scheduler.pause_job(f"{monitor_id}")
    return {"message": "Monitor paused", "monitor_id": monitor_id}

@app.patch("/monitor/resume")
def resume_monitor(monitor_id: int):
    if not get_monitor(monitor_id):
        raise HTTPException(status_code=404, detail="Monitor not found")
    scheduler.resume_job(f"{monitor_id}")
    return {"message": "Monitor resumed", "monitor_id": monitor_id}

def run_monitor(monitor_id: int):
    """
    Runs the specific monitor:
    1. Fetches the saved query settings.
    2. Scrapes Vinted.
    3. Saves new items.
    4. Calculates 'New Items Today' and 'Average Price'.
    5. Saves to history.
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
        
        new_count = save_listings(items)

        avg_price = 0
        if items:
            total = sum(i['price'] for i in items)
            avg_price = round(total / len(items), 2)
        
        log_stats(monitor_id, len(items), new_count)
        
        return {
            "monitor": m["name"],
            "new_items_found": new_count,
            "current_avg_price": avg_price,
            "total_active_scraped": len(items)
        }
    except Exception as e:
        logger.exception(f"Job {monitor_id} failed: {e}")
        raise

@app.get("/monitor/{monitor_id}/history")
def view_history(monitor_id: int):
    """Returns the chart data for this monitor."""
    return get_monitor_history(monitor_id)