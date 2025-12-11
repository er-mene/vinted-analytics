# main.py updates
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import json

# Import our new DB functions
from database import create_monitor, get_monitor, log_daily_stats, get_monitor_history, save_listings
from vinted_service import search_vinted

app = FastAPI()

# 1. Define the Data Model for creating a monitor
class MonitorCreate(BaseModel):
    name: str
    query: str
    brand_id: Optional[int] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    status_ids: Optional[List[int]] = []

@app.post("/monitor")
def add_monitor(monitor: MonitorCreate):
    """Creates a new tracked search."""
    id = create_monitor(
        monitor.name, monitor.query, monitor.brand_id, 
        monitor.min_price, monitor.max_price, monitor.status_ids
    )
    return {"message": "Monitor created", "monitor_id": id}

@app.post("/monitor/{monitor_id}/run")
def run_monitor(monitor_id: int):
    """
    Runs the specific monitor:
    1. Fetches the saved query settings.
    2. Scrapes Vinted.
    3. Saves new items.
    4. Calculates 'New Items Today' and 'Average Price'.
    5. Saves to history.
    """
    # A. Get Settings
    m = get_monitor(monitor_id)
    if not m:
        raise HTTPException(status_code=404, detail="Monitor not found")
        
    # Parse the status IDs back from string to list
    status_ids = json.loads(m["status_ids"])
    
    # B. Run Scraper
    print(f"🔄 Running Monitor: {m['name']}...")
    items = search_vinted(
        query=m["query"],
        brand_id=m["brand_id"],
        min_price=m["min_price"],
        max_price=m["max_price"],
        status_ids=status_ids
    )
    
    # C. Save to DB
    new_count = save_listings(items)
    
    # D. Calculate Stats (Analytics)
    # Average price of the items we just found
    avg_price = 0
    if items:
        total = sum(i['price'] for i in items)
        avg_price = round(total / len(items), 2)
    
    # E. Log History
    log_daily_stats(monitor_id, new_count, avg_price)
    
    return {
        "monitor": m["name"],
        "new_items_found": new_count,
        "current_avg_price": avg_price,
        "total_active_scraped": len(items)
    }

@app.get("/monitor/{monitor_id}/history")
def view_history(monitor_id: int):
    """Returns the chart data for this monitor."""
    return get_monitor_history(monitor_id)