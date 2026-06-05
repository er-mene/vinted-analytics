from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List
import json
import logging
import threading
from datetime import datetime
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


def _build_dashboard_html(monitor_id: int) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Monitor {monitor_id} Analytics</title>
  <style>
    :root {{
      --bg: #f3efe7;
      --panel: #fffaf3;
      --ink: #1f2937;
      --muted: #6b7280;
      --accent: #b45309;
      --accent-2: #0f766e;
      --line: #e5dccf;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(180,83,9,0.12), transparent 28%),
        radial-gradient(circle at top right, rgba(15,118,110,0.10), transparent 30%),
        linear-gradient(180deg, #f7f2ea 0%, var(--bg) 100%);
    }}
    .shell {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: clamp(2rem, 4vw, 3.25rem);
      line-height: 1;
    }}
    .subtitle {{
      margin: 0 0 28px;
      color: var(--muted);
      font-family: "Helvetica Neue", Arial, sans-serif;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
      margin-bottom: 24px;
    }}
    .card, .chart {{
      background: rgba(255,250,243,0.92);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 10px 30px rgba(31, 41, 55, 0.05);
      backdrop-filter: blur(6px);
    }}
    .card {{
      padding: 16px 18px;
    }}
    .label {{
      font-size: 0.85rem;
      color: var(--muted);
      font-family: "Helvetica Neue", Arial, sans-serif;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .value {{
      margin-top: 8px;
      font-size: 1.8rem;
      font-weight: 700;
    }}
    .charts {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 18px;
    }}
    .chart {{
      padding: 16px;
    }}
    .chart h2 {{
      margin: 0 0 8px;
      font-size: 1.1rem;
    }}
    .chart p {{
      margin: 0 0 14px;
      color: var(--muted);
      font-family: "Helvetica Neue", Arial, sans-serif;
      font-size: 0.95rem;
    }}
    canvas {{
      width: 100%;
      height: 280px;
      display: block;
      background: linear-gradient(180deg, rgba(255,255,255,0.55), rgba(255,255,255,0.2));
      border-radius: 12px;
    }}
    .empty {{
      padding: 48px 18px;
      text-align: center;
      color: var(--muted);
      font-family: "Helvetica Neue", Arial, sans-serif;
    }}
  </style>
</head>
<body>
  <main class="shell">
    <h1 id="title">Monitor {monitor_id} analytics</h1>
    <p class="subtitle">Three quick ways to read the market: price over time, likes vs price, and sold speed vs price.</p>
    <section class="cards" id="cards"></section>
    <section class="charts">
      <article class="chart">
        <h2>Price Distribution Over Time</h2>
        <p>Daily average price, with min/max range.</p>
        <canvas id="priceHistory" width="520" height="280"></canvas>
      </article>
      <article class="chart">
        <h2>Price / Likes Correlation</h2>
        <p>Each point is a listing. Higher points mean more likes.</p>
        <canvas id="priceLikes" width="520" height="280"></canvas>
      </article>
      <article class="chart">
        <h2>Price / Time To Sell</h2>
        <p>Sold items only. Rightward means longer to sell.</p>
        <canvas id="sellSpeed" width="520" height="280"></canvas>
      </article>
    </section>
  </main>
  <script>
    const monitorId = {monitor_id};

    function drawAxes(ctx, width, height, labels) {{
      const padding = {{ top: 20, right: 18, bottom: 34, left: 52 }};
      const innerWidth = width - padding.left - padding.right;
      const innerHeight = height - padding.top - padding.bottom;

      ctx.clearRect(0, 0, width, height);
      ctx.strokeStyle = '#cdbda9';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(padding.left, padding.top);
      ctx.lineTo(padding.left, height - padding.bottom);
      ctx.lineTo(width - padding.right, height - padding.bottom);
      ctx.stroke();

      ctx.fillStyle = '#6b7280';
      ctx.font = '12px Arial';
      if (labels.x) {{
        ctx.fillText(labels.x, width / 2 - 30, height - 10);
      }}
      if (labels.y) {{
        ctx.save();
        ctx.translate(14, height / 2 + 20);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText(labels.y, 0, 0);
        ctx.restore();
      }}

      return {{ padding, innerWidth, innerHeight }};
    }}

    function drawEmpty(canvas, message) {{
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#6b7280';
      ctx.font = '14px Arial';
      ctx.textAlign = 'center';
      ctx.fillText(message, canvas.width / 2, canvas.height / 2);
    }}

    function drawLineChart(canvas, points) {{
      if (!points.length) {{
        drawEmpty(canvas, 'Not enough dated listings yet.');
        return;
      }}

      const ctx = canvas.getContext('2d');
      const {{ padding, innerWidth, innerHeight }} = drawAxes(ctx, canvas.width, canvas.height, {{
        x: 'Date',
        y: 'Price'
      }});
      const prices = points.flatMap(point => [point.min_price, point.avg_price, point.max_price]);
      const minY = Math.min(...prices);
      const maxY = Math.max(...prices);
      const rangeY = Math.max(maxY - minY, 1);

      const xFor = index => padding.left + (innerWidth * (points.length === 1 ? 0.5 : index / (points.length - 1)));
      const yFor = value => padding.top + innerHeight - ((value - minY) / rangeY) * innerHeight;

      ctx.strokeStyle = 'rgba(180,83,9,0.2)';
      ctx.lineWidth = 8;
      ctx.lineCap = 'round';
      ctx.beginPath();
      points.forEach((point, index) => {{
        const x = xFor(index);
        ctx.moveTo(x, yFor(point.min_price));
        ctx.lineTo(x, yFor(point.max_price));
      }});
      ctx.stroke();

      ctx.strokeStyle = '#b45309';
      ctx.lineWidth = 3;
      ctx.beginPath();
      points.forEach((point, index) => {{
        const x = xFor(index);
        const y = yFor(point.avg_price);
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }});
      ctx.stroke();

      ctx.fillStyle = '#0f172a';
      ctx.font = '11px Arial';
      points.forEach((point, index) => {{
        if (index === 0 || index === points.length - 1 || index % Math.ceil(points.length / 4) === 0) {{
          ctx.fillText(point.day.slice(5), xFor(index) - 16, canvas.height - 18);
        }}
      }});
    }}

    function drawScatter(canvas, points, xKey, yKey, xLabel, yLabel, color) {{
      if (!points.length) {{
        drawEmpty(canvas, 'Not enough data yet.');
        return;
      }}

      const ctx = canvas.getContext('2d');
      const {{ padding, innerWidth, innerHeight }} = drawAxes(ctx, canvas.width, canvas.height, {{
        x: xLabel,
        y: yLabel
      }});
      const xValues = points.map(point => Number(point[xKey]));
      const yValues = points.map(point => Number(point[yKey]));
      const minX = Math.min(...xValues);
      const maxX = Math.max(...xValues);
      const minY = Math.min(...yValues);
      const maxY = Math.max(...yValues);
      const rangeX = Math.max(maxX - minX, 1);
      const rangeY = Math.max(maxY - minY, 1);

      const xFor = value => padding.left + ((value - minX) / rangeX) * innerWidth;
      const yFor = value => padding.top + innerHeight - ((value - minY) / rangeY) * innerHeight;

      ctx.fillStyle = color;
      points.forEach(point => {{
        ctx.beginPath();
        ctx.arc(xFor(Number(point[xKey])), yFor(Number(point[yKey])), 4, 0, Math.PI * 2);
        ctx.fill();
      }});
    }}

    function formatValue(value) {{
      if (value === null || value === undefined) return 'n/a';
      if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(2);
      return String(value);
    }}

    async function load() {{
      const response = await fetch(`/api/monitor/${{monitorId}}/analytics`);
      if (!response.ok) {{
        document.body.innerHTML = `<div class="empty">Unable to load analytics for monitor ${{monitorId}}.</div>`;
        return;
      }}
      const data = await response.json();
      document.getElementById('title').textContent = `${{data.summary.name}} analytics`;

      const cards = [
        ['Total listings', data.summary.total_listings],
        ['Active listings', data.summary.active_listings],
        ['Sold listings', data.summary.sold_listings],
        ['Average price', data.summary.avg_price],
        ['Average likes', data.summary.avg_likes],
        ['Price/likes corr.', data.correlations.price_likes],
        ['Price/sell-time corr.', data.correlations.price_sell_time]
      ];
      document.getElementById('cards').innerHTML = cards.map(([label, value]) => `
        <div class="card">
          <div class="label">${{label}}</div>
          <div class="value">${{formatValue(value)}}</div>
        </div>
      `).join('');

      drawLineChart(document.getElementById('priceHistory'), data.price_history);
      drawScatter(document.getElementById('priceLikes'), data.price_likes, 'price', 'likes', 'Price', 'Likes', '#0f766e');
      drawScatter(document.getElementById('sellSpeed'), data.sell_speed, 'hours_to_sell', 'price', 'Hours to sell', 'Price', '#b45309');
    }}

    load();
  </script>
</body>
</html>"""

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
    page_delay_seconds: float = 4.0
    search_time_seconds: int = 5184000
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

    id = create_monitor(
        monitor.name, monitor.query, monitor.brand_id,
        monitor.min_price, monitor.max_price, monitor.status_ids,
        monitor.max_pages, monitor.page_delay_seconds, monitor.search_time_seconds,
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
        page_delay_seconds = m.get("page_delay_seconds") or 4.0
        search_time_seconds = m.get("search_time_seconds") or 5184000
        
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
    scheduler.remove_job(str(monitor_id))
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

    update_monitor(
        monitor_id=monitor_id,
        name=monitor.name,
        query=monitor.query,
        brand_id=monitor.brand_id,
        min_price=monitor.min_price,
        max_price=monitor.max_price,
        status_ids=monitor.status_ids,
        max_pages=monitor.max_pages,
        page_delay_seconds=monitor.page_delay_seconds,
        search_time_seconds=monitor.search_time_seconds,
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
    return """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Vinted Analytics · Dashboard</title>
  <style>
    :root {
      --bg: #f3efe7;
      --panel: #fffaf3;
      --ink: #1f2937;
      --muted: #6b7280;
      --accent: #b45309;
      --accent-2: #0f766e;
      --line: #e5dccf;
      --green: #059669;
      --red: #dc2626;
      --yellow: #d97706;
      --radius: 18px;
    }
    *, *::before, *::after { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(180,83,9,0.12), transparent 28%),
        radial-gradient(circle at top right, rgba(15,118,110,0.10), transparent 30%),
        linear-gradient(180deg, #f7f2ea 0%, var(--bg) 100%);
    }
    .shell { max-width: 1280px; margin: 0 auto; padding: 24px 20px 48px; }

    /* nav */
    .nav {
      display: flex; gap: 24px; align-items: center;
      padding: 14px 0; margin-bottom: 20px;
      border-bottom: 1px solid var(--line);
    }
    .nav a {
      font-family: "Helvetica Neue", Arial, sans-serif;
      font-size: 0.95rem; color: var(--muted); text-decoration: none;
    }
    .nav a:hover { color: var(--ink); }
    .nav .brand {
      font-family: Georgia, serif; font-size: 1.2rem;
      font-weight: 700; color: var(--accent); margin-right: auto;
    }
    .nav .active { color: var(--ink); font-weight: 600; }

    /* cards */
    .cards {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px; margin-bottom: 24px;
    }
    .card {
      background: rgba(255,250,243,0.92);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: 0 10px 30px rgba(31,41,55,0.05);
      backdrop-filter: blur(6px);
      padding: 16px 18px;
    }
    .label {
      font-size: 0.8rem; color: var(--muted);
      font-family: "Helvetica Neue", Arial, sans-serif;
      text-transform: uppercase; letter-spacing: 0.08em;
    }
    .value { margin-top: 6px; font-size: 1.8rem; font-weight: 700; }

    /* table */
    .table-wrap {
      background: rgba(255,250,243,0.92);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: 0 10px 30px rgba(31,41,55,0.05);
      backdrop-filter: blur(6px);
      overflow: hidden;
    }
    table { width: 100%; border-collapse: collapse; }
    th {
      text-align: left; padding: 12px 14px;
      font-family: "Helvetica Neue", Arial, sans-serif;
      font-size: 0.8rem; color: var(--muted);
      text-transform: uppercase; letter-spacing: 0.08em;
      border-bottom: 1px solid var(--line);
      background: rgba(229,220,207,0.2);
    }
    td { padding: 10px 14px; border-bottom: 1px solid var(--line); font-size: 0.95rem; }
    tr:last-child td { border-bottom: none; }

    /* badges */
    .badge {
      display: inline-block; padding: 2px 10px; border-radius: 999px;
      font-family: "Helvetica Neue", Arial, sans-serif;
      font-size: 0.8rem; font-weight: 600;
    }
    .badge-green { background: #d1fae5; color: var(--green); }
    .badge-red { background: #fce4e4; color: var(--red); }
    .badge-yellow { background: #fef3c7; color: var(--yellow); }
    .badge-gray { background: #e5e7eb; color: var(--muted); }

    .actions a {
      font-family: "Helvetica Neue", Arial, sans-serif;
      font-size: 0.82rem; color: var(--accent-2); text-decoration: none;
      margin-right: 8px;
    }
    .actions a:hover { text-decoration: underline; }

    .empty {
      padding: 48px; text-align: center; color: var(--muted);
      font-family: "Helvetica Neue", Arial, sans-serif;
    }
    .section-title {
      margin: 28px 0 12px; font-size: 1.3rem;
    }
  </style>
</head>
<body>
  <div class="shell">
    <nav class="nav">
      <span class="brand">Vinted Analytics</span>
      <a href="/api/dashboard" class="active">Dashboard</a>
      <a href="/api/queue/dashboard">Queue</a>
    </nav>

    <section class="cards" id="summary-cards"></section>

    <h2 class="section-title">Monitors</h2>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Query</th>
            <th>Schedule</th>
            <th>Last Scrape</th>
            <th>Listings</th>
            <th>Avg Price</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody id="monitors-body"></tbody>
      </table>
    </div>
  </div>
  <script>
    (async () => {
      const resp = await fetch("/api/overview?_=" + Date.now());
      if (!resp.ok) { document.body.innerHTML = '<div class="shell"><p class="empty">Failed to load data.</p></div>'; return; }
      const data = await resp.json();

      // summary cards
      const totalMon = data.monitors.length;
      const totalList = data.monitors.reduce((s, m) => s + (m.active_listings || 0), 0);
      document.getElementById("summary-cards").innerHTML = [
        ["Monitors", totalMon],
        ["Active Listings", totalList],
        ["Queue Size", data.queue.total],
        ["Oldest Queued", data.queue.oldest_queued ? data.queue.oldest_queued.slice(0, 10) : "—"]
      ].map(([label, value]) =>
        `<div class="card"><div class="label">${label}</div><div class="value">${value}</div></div>`
      ).join("");

      // monitors table
      const tbody = document.getElementById("monitors-body");
      if (!data.monitors.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty">No monitors yet.</td></tr>';
        return;
      }
      for (const m of data.monitors) {
        const status = m.paused
          ? '<span class="badge badge-yellow">Paused</span>'
          : m.next_run_time
            ? '<span class="badge badge-green">Active</span>'
            : '<span class="badge badge-gray">Stopped</span>';
        const nextRun = m.next_run_time ? m.next_run_time.slice(0, 19).replace("T", " ") : "—";
        const lastScrape = m.last_scrape ? m.last_scrape.slice(0, 19).replace("T", " ") : "—";
        const avgP = m.avg_price !== null ? "\\u20AC" + Number(m.avg_price).toFixed(2) : "—";
        const row = document.createElement("tr");
        row.innerHTML =
          `<td><strong>${m.name}</strong></td>` +
          `<td>${m.query}</td>` +
          `<td>${status}<br><span style="font-size:0.8rem;color:var(--muted)">${nextRun}</span></td>` +
          `<td><span style="font-size:0.85rem;color:var(--muted)">${lastScrape}</span></td>` +
          `<td>${m.active_listings ?? 0} active / ${m.sold_listings ?? 0} sold</td>` +
          `<td>${avgP}</td>` +
          `<td class="actions">
            <a href="/api/monitor/${m.id}/run">Run</a>
            <a href="/api/monitor/${m.id}/analytics">Data</a>
            <a href="/api/monitor/${m.id}/dashboard">Chart</a>
          </td>`;
        tbody.appendChild(row);
      }
    })();
  </script>
</body>
</html>
"""


def _build_queue_html() -> str:
    return """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Vinted Analytics · Queue</title>
  <style>
    :root {
      --bg: #f3efe7;
      --panel: #fffaf3;
      --ink: #1f2937;
      --muted: #6b7280;
      --accent: #b45309;
      --accent-2: #0f766e;
      --line: #e5dccf;
      --green: #059669;
      --red: #dc2626;
      --yellow: #d97706;
      --radius: 18px;
    }
    *, *::before, *::after { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(180,83,9,0.12), transparent 28%),
        radial-gradient(circle at top right, rgba(15,118,110,0.10), transparent 30%),
        linear-gradient(180deg, #f7f2ea 0%, var(--bg) 100%);
    }
    .shell { max-width: 1280px; margin: 0 auto; padding: 24px 20px 48px; }

    .nav {
      display: flex; gap: 24px; align-items: center;
      padding: 14px 0; margin-bottom: 20px;
      border-bottom: 1px solid var(--line);
    }
    .nav a {
      font-family: "Helvetica Neue", Arial, sans-serif;
      font-size: 0.95rem; color: var(--muted); text-decoration: none;
    }
    .nav a:hover { color: var(--ink); }
    .nav .brand {
      font-family: Georgia, serif; font-size: 1.2rem;
      font-weight: 700; color: var(--accent); margin-right: auto;
    }
    .nav .active { color: var(--ink); font-weight: 600; }

    .cards {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px; margin-bottom: 24px;
    }
    .card {
      background: rgba(255,250,243,0.92);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: 0 10px 30px rgba(31,41,55,0.05);
      backdrop-filter: blur(6px);
      padding: 16px 18px;
    }
    .label {
      font-size: 0.8rem; color: var(--muted);
      font-family: "Helvetica Neue", Arial, sans-serif;
      text-transform: uppercase; letter-spacing: 0.08em;
    }
    .value { margin-top: 6px; font-size: 1.8rem; font-weight: 700; }

    .table-wrap {
      background: rgba(255,250,243,0.92);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: 0 10px 30px rgba(31,41,55,0.05);
      backdrop-filter: blur(6px);
      overflow: hidden;
    }
    table { width: 100%; border-collapse: collapse; }
    th {
      text-align: left; padding: 12px 14px;
      font-family: "Helvetica Neue", Arial, sans-serif;
      font-size: 0.8rem; color: var(--muted);
      text-transform: uppercase; letter-spacing: 0.08em;
      border-bottom: 1px solid var(--line);
      background: rgba(229,220,207,0.2);
    }
    td { padding: 10px 14px; border-bottom: 1px solid var(--line); font-size: 0.95rem; }

    .badge {
      display: inline-block; padding: 2px 10px; border-radius: 999px;
      font-family: "Helvetica Neue", Arial, sans-serif;
      font-size: 0.8rem; font-weight: 600;
    }
    .badge-green { background: #d1fae5; color: var(--green); }
    .badge-red { background: #fce4e4; color: var(--red); }
    .badge-yellow { background: #fef3c7; color: var(--yellow); }
    .badge-gray { background: #e5e7eb; color: var(--muted); }

    .item-title { color: var(--ink); text-decoration: none; }
    .item-title:hover { text-decoration: underline; }

    .empty {
      padding: 48px; text-align: center; color: var(--muted);
      font-family: "Helvetica Neue", Arial, sans-serif;
    }
    .section-title { margin: 28px 0 12px; font-size: 1.3rem; }
  </style>
</head>
<body>
  <div class="shell">
    <nav class="nav">
      <span class="brand">Vinted Analytics</span>
      <a href="/api/dashboard">Dashboard</a>
      <a href="/api/queue/dashboard" class="active">Queue</a>
    </nav>

    <section class="cards" id="summary-cards"></section>

    <h2 class="section-title">Verification Queue <span style="font-size:0.9rem;color:var(--muted);font-weight:400">(oldest first)</span></h2>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Item</th>
            <th>Brand</th>
            <th>Price</th>
            <th>Monitor</th>
            <th>Queued</th>
            <th>Last Check</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody id="queue-body"></tbody>
      </table>
    </div>
  </div>
  <script>
    (async () => {
      const resp = await fetch("/api/queue");
      if (!resp.ok) { document.body.innerHTML = '<div class="shell"><p class="empty">Failed to load queue.</p></div>'; return; }
      const data = await resp.json();

      document.getElementById("summary-cards").innerHTML = [
        ["Queue Size", data.total],
        ["Oldest Queued", data.oldest_queued ? data.oldest_queued.slice(0, 10) : "—"]
      ].map(([label, value]) =>
        `<div class="card"><div class="label">${label}</div><div class="value">${value}</div></div>`
      ).join("");

      const tbody = document.getElementById("queue-body");
      if (!data.items.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty">Queue is empty.</td></tr>';
        return;
      }
      for (const item of data.items) {
        const title = item.title || "(deleted)";
        const url = item.url || "#";
        const brand = item.brand || "—";
        const price = item.price !== null ? "\\u20AC" + Number(item.price).toFixed(2) : "—";
        const mon = item.monitor_name || "—";

        let statusBadge;
        if (item.is_active === 0 && item.sold_at) {
          statusBadge = '<span class="badge badge-red">Sold</span>';
        } else if (item.is_active === 0) {
          statusBadge = '<span class="badge badge-yellow">Removed</span>';
        } else if (item.is_active === 1) {
          statusBadge = '<span class="badge badge-green">Active</span>';
        } else {
          statusBadge = '<span class="badge badge-gray">Unknown</span>';
        }

        const queued = item.queued_at ? item.queued_at.slice(0, 19).replace("T", " ") : "—";
        const lastCheck = item.last_check ? item.last_check.slice(0, 19).replace("T", " ") : "—";

        const row = document.createElement("tr");
        row.innerHTML =
          `<td><a href="${url}" class="item-title" target="_blank">${title}</a></td>` +
          `<td>${brand}</td>` +
          `<td>${price}</td>` +
          `<td>${mon}</td>` +
          `<td>${queued}</td>` +
          `<td>${lastCheck}</td>` +
          `<td>${statusBadge}</td>`;
        tbody.appendChild(row);
      }
    })();
  </script>
</body>
</html>
"""


# ── HTML endpoints ───────────────────────────────────────────────────────────


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(_build_overview_html())


@router.get("/queue/dashboard", response_class=HTMLResponse)
def queue_dashboard():
    return HTMLResponse(_build_queue_html())
