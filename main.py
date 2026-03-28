from fastapi import FastAPI, HTTPException, Depends 
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional, List
import json
import logging
from database import init_db, create_monitor, get_monitor, save_listings, get_monitors_list, delete_monitor, scheduler
from vinted_service import search_vinted

#TODO: grafico che mostra l'andamento del prezzo medio giornaliero e i nuovi annunci per un monitor specifico

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

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

    #default interval
    if (monitor.days == monitor.hours == monitor.minutes == monitor.seconds == 0): 
        monitor.minutes = 10 
    
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

@app.get("/monitor/{monitor_id}/run")
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

@app.post("/monitor/delete")
def delete_monitor_from_db(monitor_id: int):
    delete_monitor(monitor_id)
    scheduler.remove_job(monitor_id)
    return {"message": f"Monitor {monitor_id} deleted"}

def main():
    pass

if __name__ == "__main__": main()

