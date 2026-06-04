# Vinted Monitor and Analytics

FastAPI service for tracking Vinted search results, storing listing history in SQLite, verifying listings in the background, and exposing simple analytics charts.

## What It Does

- Creates search monitors for Vinted queries.
- Runs each monitor on a schedule with APScheduler.
- Stores listings in SQLite.
- Keeps a background verification queue to detect removed and sold items.
- Exposes analytics for price history, price/likes correlation, and price/time-to-sell correlation.
- Includes a built-in dashboard page rendered directly by the API.

## Current Behavior

- Monitor jobs start immediately after creation.
- Monitor frequency has a minimum interval of 30 minutes.
- If no interval is provided, the request defaults to 10 minutes, then is clamped to the 30-minute minimum.
- A background verification worker runs for the whole lifetime of the server.
- The verification worker checks queued listings, removes disappeared items, and marks sold items with `sold_at`.

## Stack

- FastAPI
- APScheduler
- SQLite
- curl_cffi
- BeautifulSoup

## Project Layout

- [backend/main.py](/Users/ermene/projects/vinted%20market%20analyzer/vinted-analytics/backend/main.py): app startup, scheduler startup, verification worker lifecycle.
- [backend/app/api/endpoints.py](/Users/ermene/projects/vinted%20market%20analyzer/vinted-analytics/backend/app/api/endpoints.py): API routes, monitor scheduling, analytics JSON, dashboard HTML.
- [backend/app/db/database.py](/Users/ermene/projects/vinted%20market%20analyzer/vinted-analytics/backend/app/db/database.py): schema creation and all database operations.
- [backend/app/services/vinted_service.py](/Users/ermene/projects/vinted%20market%20analyzer/vinted-analytics/backend/app/services/vinted_service.py): Vinted requests and item status checks.
- [backend/app/tasks/verification_worker.py](/Users/ermene/projects/vinted%20market%20analyzer/vinted-analytics/backend/app/tasks/verification_worker.py): background verification loop.
- [frontend/](/Users/ermene/projects/vinted%20market%20analyzer/vinted-analytics/frontend/): Vite + React + TypeScript frontend.

## Database

### `monitors`

Stores one saved search per row.

Important fields:
- `id`
- `name`
- `query`
- `brand_id`
- `min_price`
- `max_price`
- `status_ids`

### `listings`

Stores scraped listing snapshots keyed by `(id, monitor_id)`.

Important fields:
- `id`
- `monitor_id`
- `title`
- `brand`
- `price`
- `url`
- `likes`
- `is_active`
- `listed_at`
- `sold_at`
- `has_been_promoted`

### `verification_queue`

Stores listing ids that still need background verification.

Important fields:
- `id`
- `url`
- `queued_at`
- `last_check`

## API

All routes are mounted under `/api`.

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/` | List all monitors |
| `POST` | `/api/monitor` | Create a monitor and schedule it |
| `PATCH` | `/api/monitor/stop` | Pause one monitor job |
| `PATCH` | `/api/monitor/resume` | Resume one monitor job |
| `POST` | `/api/monitor/delete` | Delete one monitor and remove its job |
| `GET` | `/api/monitor/{monitor_id}/run` | Run one monitor immediately |
| `GET` | `/api/monitor/{monitor_id}/analytics` | Return analytics JSON |
| `GET` | `/api/monitor/{monitor_id}/dashboard` | Show the built-in charts page |

## Analytics

The analytics endpoint currently returns:

- monitor summary
- price history grouped by day
- listing-level price and likes points
- sold listing points with hours-to-sell
- Pearson correlations for:
  - price vs likes
  - price vs time to sell

The dashboard visualizes:

- price distribution over time
- price / likes correlation
- price / time-to-sell correlation

Note: the sell-time chart will be empty until some listings are marked as sold.

## Running Locally

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

Or from the project root:

```bash
.venv/bin/uvicorn backend.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Then open:

- `http://127.0.0.1:8000/docs` - API docs
- `http://127.0.0.1:5173` - Frontend

## Notes

- The scraper uses Vinted's default page size (typically 48 items) and paginates through multiple pages with configurable delays between requests to reduce rate-limiting risk.
- A `jitter=300` (5 min) is applied to scheduled monitor intervals so they don't fire at exact clockwork intervals.
- The `max_pages` parameter (default: unlimited) caps how many pages are fetched per monitor run. Lowering this reduces request volume.
- The `page_delay_seconds` parameter (default: 4.0) controls the base delay between page requests. Actual delay varies by ±30% per request.
- The 30-minute minimum interval was added to reduce request pressure.
- The verification worker uses random per-item delays, but it still contributes traffic.
- This project currently uses SQLite and a local file `vinted_data.db`.
