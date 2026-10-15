import os
import sqlite3
import json
import time
from datetime import datetime, timezone

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_NAME = os.path.join(BACKEND_DIR, "vinted_data.db")

try:
    from app.utils.perf_monitor import trace_connection
except ImportError:
    from backend.app.utils.perf_monitor import trace_connection

def get_db_connection(db_path: str | None = None):
    return trace_connection(sqlite3.connect(db_path or DB_NAME))

def init_db():
    conn = get_db_connection()
    conn.execute("PRAGMA journal_mode=WAL;")
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER,
            monitor_id INTEGER REFERENCES monitors(id) ON DELETE CASCADE,
            title TEXT,
            brand TEXT,
            price REAL,
            url TEXT,
            status_id INTEGER,
            is_active INTEGER,      -- boolean
            likes INTEGER,
            listed_at TIMESTAMP,
            sold_at TIMESTAMP,
            has_been_promoted INTEGER, -- boolean
            scrape_position INTEGER,
            last_seen_at TIMESTAMP,
            consecutive_misses INTEGER DEFAULT 0,
            PRIMARY KEY (id, monitor_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS monitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            query TEXT,
            brand_id INTEGER,
            min_price REAL,
            max_price REAL,
            status_ids TEXT,
            max_pages INTEGER,
            page_delay_seconds REAL DEFAULT 6.0,
            last_scrape TIMESTAMP,
            search_time_seconds INTEGER DEFAULT 5184000,
            max_age REAL DEFAULT 7.0,
            interval_days INTEGER DEFAULT 0,
            interval_hours INTEGER DEFAULT 0,
            interval_minutes INTEGER DEFAULT 30,
            interval_seconds INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        )
    ''')

    try:
        cursor.execute("ALTER TABLE monitors ADD COLUMN max_age REAL DEFAULT 7.0")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE monitors ADD COLUMN is_active INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE listings ADD COLUMN consecutive_misses INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS verification_queue (
            id INTEGER PRIMARY KEY REFERENCES listings(id) ON DELETE CASCADE,
            url TEXT UNIQUE,
            queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            scheduled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_check TIMESTAMP
        )
    ''')

    try:
        cursor.execute("ALTER TABLE verification_queue ADD COLUMN scheduled_at TIMESTAMP")
    except sqlite3.OperationalError:
        pass

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_listings_monitor_active ON listings(monitor_id, is_active)
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_queue_last_check ON verification_queue(last_check)
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_queue_scheduled_at ON verification_queue(scheduled_at)
    ''')

    conn.commit()
    conn.close()


def create_monitor(name, query, brand_id, min_price, max_price, status_ids=[], max_pages=None, page_delay_seconds=6.0, search_time_seconds=5184000, max_age=7.0, interval_days=0, interval_hours=0, interval_minutes=30, interval_seconds=0, is_active=1):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    status_str = json.dumps(status_ids) if status_ids else "[]"
    
    cursor.execute('''
        INSERT INTO monitors (name, query, brand_id, min_price, max_price, status_ids, max_pages, page_delay_seconds, search_time_seconds, max_age, interval_days, interval_hours, interval_minutes, interval_seconds, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (name, query, brand_id, min_price, max_price, status_str, max_pages, page_delay_seconds, search_time_seconds, max_age, interval_days, interval_hours, interval_minutes, interval_seconds, is_active))
    
    monitor_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return monitor_id

def update_monitor(monitor_id, name=None, query=None, brand_id=None, min_price=None, max_price=None, status_ids=None, max_pages=None, page_delay_seconds=None, search_time_seconds=None, max_age=None, interval_days=None, interval_hours=None, interval_minutes=None, interval_seconds=None, is_active=None):
    updates = {
        "name": name,
        "query": query,
        "brand_id": brand_id,
        "min_price": min_price,
        "max_price": max_price,
        "status_ids": json.dumps(status_ids) if status_ids is not None else None,
        "max_pages": max_pages,
        "page_delay_seconds": page_delay_seconds,
        "search_time_seconds": search_time_seconds,
        "max_age": max_age,
        "interval_days": interval_days,
        "interval_hours": interval_hours,
        "interval_minutes": interval_minutes,
        "interval_seconds": interval_seconds,
        "is_active": is_active,
    }

    active_updates = {col: val for col, val in updates.items() if val is not None}
    if not active_updates:
        return

    fields = [f"{col} = ?" for col in active_updates]
    values = list(active_updates.values())

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE monitors SET {', '.join(fields)} WHERE id = ?", (*values, monitor_id))
    conn.commit()
    conn.close()

def set_monitor_active(monitor_id: int, is_active: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE monitors SET is_active = ? WHERE id = ?", (1 if is_active else 0, monitor_id))
    conn.commit()
    conn.close()

def get_monitor(monitor_id):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row # Allows accessing columns by name
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_monitors_list():
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM monitors")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def _is_item_older_than(item: dict, now_ts: float, max_age_seconds: float) -> bool:
    ts = item.get("listed_at_ts")
    if ts is not None:
        return (now_ts - ts) > max_age_seconds
    listed_at_str = item.get("listed_at")
    if listed_at_str:
        try:
            dt = datetime.strptime(listed_at_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            return (now_ts - dt.timestamp()) > max_age_seconds
        except Exception:
            pass
    return False


def calculate_schedule_delay_hours(position: int) -> float:
    """
    Tiered verification delay based on listing position in search:
    - Positions 0-9 (Top 10 hottest): 6 hours
    - Positions 10-29 (Page 1 top): 12 hours
    - Positions 30-47 (Page 1 bottom): 18 hours
    - Positions 48-95 (Page 2): 24 hours
    - Positions 96+ (Page 3+): 36 hours
    """
    if position < 10:
        return 6.0
    elif position < 30:
        return 12.0
    elif position < 48:
        return 18.0
    elif position < 96:
        return 24.0
    else:
        return 36.0


def save_listings(monitor_id: int, items: list, max_pages: int | None = None) -> int:
    if not items:
        return 0

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT max_age FROM monitors WHERE id = ?", (monitor_id,))
    row = cursor.fetchone()
    max_age = row[0] if row and row[0] is not None else 7.0

    if max_age is not None:
        now_ts = time.time()
        max_age_seconds = float(max_age) * 86400.0
        items = [i for i in items if not _is_item_older_than(i, now_ts, max_age_seconds)]

    if not items:
        conn.close()
        return 0

    new_count = 0

    # Save listings with scrape position and schedule verification based on position tier
    for position, item in enumerate(items):
        cursor.execute("""
            INSERT INTO listings
            (id, monitor_id, title, brand, price, url, status_id, is_active, likes, listed_at, has_been_promoted, scrape_position, last_seen_at, consecutive_misses)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 0)
            ON CONFLICT(id, monitor_id) DO UPDATE SET
            price = excluded.price,
            likes = excluded.likes,
            has_been_promoted = MAX(listings.has_been_promoted, excluded.has_been_promoted),
            scrape_position = excluded.scrape_position,
            is_active = excluded.is_active,
            sold_at = NULL,
            last_seen_at = CURRENT_TIMESTAMP,
            consecutive_misses = 0
        """, (
            item["id"], monitor_id, item["title"], item["brand"], item["price"],
            item["url"], item.get("status_id"), 1, item.get("likes"),
            item.get("listed_at"), item.get("has_been_promoted", 0), position,
        ))
        if cursor.rowcount > 0:
            new_count += 1

        delay_hours = calculate_schedule_delay_hours(position)
        # Insert into queue with scheduled_at, or advance scheduled_at if the item improved position
        cursor.execute("""
            INSERT INTO verification_queue (id, url, queued_at, scheduled_at, last_check)
            VALUES (?, ?, CURRENT_TIMESTAMP, datetime('now', ?), NULL)
            ON CONFLICT(id) DO UPDATE SET
                scheduled_at = MIN(COALESCE(verification_queue.scheduled_at, excluded.scheduled_at), excluded.scheduled_at)
        """, (item["id"], item["url"], f"+{delay_hours:.1f} hours"))

    conn.commit()
    conn.close()
    return new_count

QUEUE_EXPIRATION = 7.0

def clear_queue(max_age: float | None = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        DELETE FROM verification_queue
        WHERE id IN (
            SELECT vq.id
            FROM verification_queue vq
            JOIN listings l ON l.id = vq.id
            WHERE (julianday('now') - julianday(l.listed_at)) >= COALESCE(
                (SELECT max_age FROM monitors WHERE id = l.monitor_id),
                ?
            )
        )
    ''', (max_age or QUEUE_EXPIRATION,))
    cursor.execute('''
        DELETE FROM verification_queue
        WHERE id NOT IN (
            SELECT id
            FROM listings
        )
    ''')
    conn.commit()
    conn.close()

def clear_verification_queue() -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM verification_queue")
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count

def clear_data(monitors: bool = False, listings: bool = True, daily_stats: bool = True):
    conn = get_db_connection()
    cursor = conn.cursor()
    if monitors:
        cursor.execute('''DELETE FROM monitors''')
        print("Monitors table clear")
    if listings: 
        cursor.execute('''DELETE FROM listings''')
        print("Listings table clear")
    if daily_stats:
        cursor.execute('''DELETE FROM daily_stats''')
        print("Daily stats table clear")
    conn.commit()
    conn.execute("VACUUM")
    conn.close()

def delete_monitor(monitor_id: int):
    conn = get_db_connection()
    conn.execute('''PRAGMA foreign_keys = ON;''')
    cursor = conn.cursor()
    cursor.execute('''DELETE FROM monitors WHERE id = ?''', (monitor_id,))
    conn.commit()
    conn.close()

def get_items_to_verify(max_items: int | None = None):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    query = '''
        SELECT id, url
        FROM verification_queue
        WHERE scheduled_at IS NULL OR scheduled_at <= CURRENT_TIMESTAMP
        ORDER BY COALESCE(scheduled_at, queued_at) ASC
    '''
    if max_items is not None:
        query += ' LIMIT ?'
        cursor.execute(query, (max_items,))
    else:
        cursor.execute(query)
    rows = cursor.fetchall()
    items = [{"id": row["id"], "url": row["url"]} for row in rows]
    
    if items:
        ids = [item["id"] for item in items]
        placeholders = ', '.join(['?'] * len(ids))
        cursor.execute(f'''
            UPDATE verification_queue
            SET last_check = CURRENT_TIMESTAMP,
                scheduled_at = datetime('now', '+15 minutes')
            WHERE id IN ({placeholders})
        ''', ids)
    
    conn.commit()
    conn.close()
    return items


def reschedule_verification(item_id: int, delay_hours: float = 24.0):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE verification_queue
        SET scheduled_at = datetime('now', ?),
            last_check = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (f"+{delay_hours:.1f} hours", item_id))
    conn.commit()
    conn.close()


def reschedule_or_expire_active_listing(item_id: int, listed_at: str | None = None, delay_hours: float = 24.0) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    if listed_at:
        cursor.execute("UPDATE listings SET listed_at = ? WHERE id = ?", (listed_at, item_id))

    cursor.execute("""
        SELECT l.listed_at, m.max_age
        FROM listings l
        LEFT JOIN monitors m ON m.id = l.monitor_id
        WHERE l.id = ?
    """, (item_id,))
    row = cursor.fetchone()
    item_listed_at = row[0] if row and row[0] is not None else None
    max_age = row[1] if row and row[1] is not None else 7.0

    is_expired = False
    if item_listed_at and max_age:
        try:
            dt = datetime.strptime(item_listed_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
            if age_days >= max_age:
                is_expired = True
        except Exception:
            pass

    if is_expired:
        cursor.execute("DELETE FROM verification_queue WHERE id = ?", (item_id,))
        conn.commit()
        conn.close()
        return False

    cursor.execute("""
        UPDATE verification_queue
        SET scheduled_at = datetime('now', ?),
            last_check = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (f"+{delay_hours:.1f} hours", item_id))
    conn.commit()
    conn.close()
    return True

def mark_item_as_sold(item_id: int, listed_at: str | None = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        DELETE FROM verification_queue
        WHERE id = ?
    ''', (item_id,))
    if listed_at:
        cursor.execute('''
            UPDATE listings
            SET is_active = 0,
                sold_at = CURRENT_TIMESTAMP,
                listed_at = ?
            WHERE id = ?
        ''', (listed_at, item_id))
    else:
        cursor.execute('''
            UPDATE listings
            SET is_active = 0,
                sold_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (item_id,))
    conn.commit()
    conn.close()

def delete_listing(item_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        DELETE FROM verification_queue
        WHERE id = ?
    ''', (item_id,))
    cursor.execute('''
        DELETE FROM listings
        WHERE id = ?
    ''', (item_id,))
    conn.commit()
    conn.close()

def update_monitor_last_scrape(monitor_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE monitors SET last_scrape = CURRENT_TIMESTAMP WHERE id = ?", (monitor_id,))
    conn.commit()
    conn.close()

def get_recent_items(monitor_id: int, limit: int = 10):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, brand, price, url, likes, listed_at, last_seen_at
        FROM listings
        WHERE monitor_id = ?
        ORDER BY likes DESC
        LIMIT ?
    """, (monitor_id, limit))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_listings(monitor_id: int, sort_by: str = "likes", order: str = "DESC", limit: int = 200, offset: int = 0):
    allowed_sort = {"likes", "price", "listed_at"}
    if sort_by not in allowed_sort:
        sort_by = "likes"
    order = "ASC" if order.upper() == "ASC" else "DESC"
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT id, title, brand, price, url, likes, listed_at, is_active, sold_at
        FROM listings
        WHERE monitor_id = ?
        ORDER BY {sort_by} {order}, id
        LIMIT ? OFFSET ?
    """, (monitor_id, limit, offset))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_monitor_analytics(monitor_id: int):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT m.id, m.name, COUNT(l.id) AS total_listings,
               SUM(CASE WHEN l.is_active = 1 THEN 1 ELSE 0 END) AS active_listings,
               SUM(CASE WHEN l.sold_at IS NOT NULL THEN 1 ELSE 0 END) AS sold_listings,
               ROUND(AVG(l.price), 2) AS avg_price,
               ROUND(AVG(l.likes), 2) AS avg_likes
        FROM monitors m
        LEFT JOIN listings l ON l.monitor_id = m.id
        WHERE m.id = ?
        GROUP BY m.id, m.name
    ''', (monitor_id,))
    summary_row = cursor.fetchone()
    if not summary_row:
        conn.close()
        return None

    cursor.execute('''
        SELECT date(listed_at) AS day,
               COUNT(*) AS listings_count,
               ROUND(AVG(price), 2) AS avg_price,
               MIN(price) AS min_price,
               MAX(price) AS max_price
        FROM listings
        WHERE monitor_id = ? AND listed_at IS NOT NULL AND price IS NOT NULL
        GROUP BY date(listed_at)
        ORDER BY day
    ''', (monitor_id,))
    price_history = [dict(row) for row in cursor.fetchall()]

    cursor.execute('''
        SELECT id, title, url, price, likes, listed_at, sold_at, is_active
        FROM listings
        WHERE monitor_id = ? AND price IS NOT NULL AND likes IS NOT NULL
        ORDER BY listed_at, id
    ''', (monitor_id,))
    price_likes = [dict(row) for row in cursor.fetchall()]

    cursor.execute('''
        SELECT id, title, url, price, likes, listed_at, sold_at,
               ROUND((julianday(sold_at) - julianday(listed_at)) * 24, 2) AS hours_to_sell
        FROM listings
        WHERE monitor_id = ?
          AND price IS NOT NULL
          AND listed_at IS NOT NULL
          AND sold_at IS NOT NULL
          AND julianday(sold_at) >= julianday(listed_at)
        ORDER BY sold_at, id
    ''', (monitor_id,))
    sell_speed = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return {
        "summary": dict(summary_row),
        "price_history": price_history,
        "price_likes": price_likes,
        "sell_speed": sell_speed,
    }


def get_monitors_with_stats():
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.*,
               COUNT(l.id) AS total_listings,
               SUM(CASE WHEN l.is_active = 1 THEN 1 ELSE 0 END) AS active_listings,
               SUM(CASE WHEN l.sold_at IS NOT NULL THEN 1 ELSE 0 END) AS sold_listings,
               ROUND(AVG(l.price), 2) AS avg_price,
               ROUND(AVG(l.likes), 2) AS avg_likes
        FROM monitors m
        LEFT JOIN listings l ON l.monitor_id = m.id
        GROUP BY m.id
        ORDER BY m.id
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    for row in rows:
        row["status_ids"] = json.loads(row["status_ids"]) if isinstance(row.get("status_ids"), str) else []
    return rows


def get_verification_queue_summary():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN scheduled_at IS NULL OR scheduled_at <= CURRENT_TIMESTAMP THEN 1 ELSE 0 END) AS ready,
               MIN(scheduled_at) AS next_scheduled,
               MIN(queued_at) AS oldest_queued
        FROM verification_queue
    """)
    row = cursor.fetchone()
    conn.close()
    return {
        "total": row[0] or 0,
        "ready": row[1] or 0,
        "next_scheduled": row[2],
        "oldest_queued": row[3],
    }


def get_verification_queue_items(limit: int | None = None):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    query = """
        SELECT vq.id, vq.url, vq.queued_at, vq.scheduled_at, vq.last_check,
               l.title, l.brand, l.price, l.is_active, l.sold_at, l.monitor_id,
               m.name AS monitor_name
        FROM verification_queue vq
        LEFT JOIN listings l ON l.id = vq.id
        LEFT JOIN monitors m ON m.id = l.monitor_id
        ORDER BY COALESCE(vq.scheduled_at, vq.queued_at) ASC
    """
    if limit is not None:
        query += " LIMIT ?"
        cursor.execute(query, (limit,))
    else:
        cursor.execute(query)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows
