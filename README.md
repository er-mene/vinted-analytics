# Vinted Monitor & Analytics Engine

A modular Python-based tool designed to track Vinted listings in real-time, monitor price fluctuations, and collect historical data for sales trend analysis.

## 🚀 Key Features

* **Automated Background Scraper**: Utilizes `APScheduler` to run multiple search monitors concurrently at user-defined intervals.
* **Intelligent Data Persistence**: Uses SQLite with **Write-Ahead Logging (WAL)** to handle concurrent read/write operations efficiently.
* **Anti-Bot Bypass**: Implements `curl_cffi` with Safari impersonation to mimic browser fingerprints and avoid TLS-based blocking.
* **Tracking Logic**: 
    * **Upsert System**: New items are inserted, while existing ones have their price and likes updated.
    * **Automated Sold Detection**: Items no longer appearing in search results are marked as inactive (`is_active = 0`) and assigned a `sold_at` timestamp.
    * **Sticky Promotion Flag**: Features a persistent "promoted" status to track if an item was boosted at any point during its listing.

## 🛠 Tech Stack

* **Framework**: FastAPI (Asynchronous API management).
* **Database**: SQLite (Relational storage for monitors and listings).
* **Task Scheduling**: APScheduler (Background job management).
* **HTTP Client**: `curl_cffi` (Advanced scraping and browser impersonation).

## 📂 Project Structure

* **`main.py`**: The entry point. Manages the FastAPI application lifespan, defines REST endpoints, and orchestrates the scheduler.
* **`database.py`**: The data layer. Handles table creation, CRUD operations for monitors, and the logic for saving/updating listings.
* **`vinted_service.py`**: The networking layer. Manages session/cookie acquisition and interacts with the Vinted API to fetch raw item data.

## 📊 Database Schema

### Monitors Table
Stores search configurations:
* `query`: Search keywords.
* `min_price` / `max_price`: Budget filters.
* `status_ids`: Filter for item condition.

### Listings Table
Tracks individual items across multiple scans:
* `id` & `monitor_id`: Composite Primary Key to track items uniquely across different monitors.
* `is_active`: Boolean indicating if the item is currently for sale.
* `has_been_promoted`: Tracks if the item was ever featured via paid promotion.
* `listed_at` / `sold_at`: Timestamps used to calculate the **Average Time to Sell**.

## 🔌 API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Returns a list of all existing monitors. |
| `POST` | `/monitor` | Creates a new monitor and schedules the background job. |
| `PATCH` | `/monitor/stop` | Pauses a specific background monitor. |
| `PATCH` | `/monitor/resume` | Resumes a paused monitor. |
| `POST` | `/monitor/delete` | Deletes a monitor and its associated data from the DB. |
| `GET` | `/monitor/{monitor_id}/run` | Runs a monitor and returns the average price and the items found. |

## 📈 Future Roadmap

* **Analytics Module**: SQL-based queries to visualize price distributions and "Likes vs. Sale Speed" correlations.
* **Proxy Rotation**: Integration of a proxy pool to handle higher request volumes.

---
*Note: This project is part of a software engineering learning path, focusing on system design, database integrity, and network protocols without the use of AI code generation.*