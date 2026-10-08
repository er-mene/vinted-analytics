import os
import sqlite3
import json
import time
from datetime import datetime

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
            queued_at TIMESTAMP,
            last_check TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_listings_monitor_active ON listings(monitor_id, is_active)
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_queue_last_check ON verification_queue(last_check)
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

def get_active_positions_for_monitor(monitor_id: int) -> dict[int, dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, scrape_position, price, last_seen_at, has_been_promoted, consecutive_misses
        FROM listings
        WHERE monitor_id = ? AND is_active = 1
    """, (monitor_id,))
    rows = cursor.fetchall()
    conn.close()
    return {
        row[0]: {
            "position": row[1],
            "price": row[2],
            "last_seen_at": row[3],
            "has_been_promoted": row[4] or 0,
            "consecutive_misses": row[5] or 0,
        }
        for row in rows
    }


# Configuration for absence confirmation and queueing
MISS_CONFIRMATION_THRESHOLD = 2
MISS_HOURS_THRESHOLD = 3.0
QUEUE_ZOMBIE_THRESHOLD_DAYS = 2


def _is_item_older_than(item: dict, now_ts: float, max_age_seconds: float) -> bool:
    ts = item.get("listed_at_ts")
    if ts is not None:
        return (now_ts - ts) > max_age_seconds
    listed_at_str = item.get("listed_at")
    if listed_at_str:
        try:
            dt = datetime.strptime(listed_at_str, "%Y-%m-%d %H:%M:%S")
            return (now_ts - dt.timestamp()) > max_age_seconds
        except Exception:
            pass
    return False


def _calculate_scrape_pivot(
    items: list,
    prev_data: dict[int, dict],
    max_pages: int | None = None
) -> int:
    """
    Computes the depth watermark (pivot) in previous scrape positions.
    Only organic (non-promoted) listings with unchanged prices and consistent
    downward/monotonic shifts are used as anchors to prevent promoted items
    or outliers from corrupting the watermark.
    """
    if not items or not prev_data:
        return -1

    curr_item_count = len(items)
    anchors = []

    for curr_pos, item in enumerate(items):
        item_id = item["id"]
        if item_id not in prev_data:
            continue

        prev_info = prev_data[item_id]
        # Ignore promoted items in either previous or current scrape
        if item.get("has_been_promoted") or prev_info.get("has_been_promoted"):
            continue

        # Ignore items whose price changed (could be bumped/re-ranked)
        if prev_info["price"] != item["price"]:
            continue

        old_pos = prev_info.get("position")
        if old_pos is None:
            continue

        # Plausibility check: in newest-first feeds, older items shift down (curr_pos >= old_pos).
        # We allow a small upward drift (up to 15 positions) for deletions ahead of it,
        # but an item jumping dozens of positions toward the top is an outlier (relisted/bumped).
        # Also, old_pos cannot be substantially deeper than the total scrape depth.
        if curr_pos < old_pos - 15:
            continue
        if old_pos > curr_item_count + 15:
            continue

        anchors.append(old_pos)

    if not anchors:
        # Fallback: check all non-promoted common items with plausible positions
        for curr_pos, item in enumerate(items):
            item_id = item["id"]
            if item_id in prev_data:
                prev_info = prev_data[item_id]
                if item.get("has_been_promoted") or prev_info.get("has_been_promoted"):
                    continue
                old_pos = prev_info.get("position")
                if old_pos is not None and curr_pos >= old_pos - 15 and old_pos <= curr_item_count + 15:
                    anchors.append(old_pos)

    if not anchors:
        return -1

    pivot = max(anchors)

    # Scrape depth protection: cap pivot to the items actually fetched (+ buffer for deletions)
    max_allowed_pivot = curr_item_count + 15
    if pivot > max_allowed_pivot:
        pivot = max_allowed_pivot

    return pivot


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

    prev_data = get_active_positions_for_monitor(monitor_id)
    new_ids_set = {item["id"] for item in items}
    new_count = 0

    # Clean up verification_queue for any listings that reappeared in the current scrape (false positives)
    if new_ids_set:
        ph = ", ".join(["?"] * len(new_ids_set))
        cursor.execute(f"DELETE FROM verification_queue WHERE id IN ({ph})", list(new_ids_set))

    # Calculate depth watermark (pivot) using organic, non-promoted anchor items
    pivot = _calculate_scrape_pivot(items, prev_data, max_pages)

    # Save listings with their scrape position and reset consecutive_misses to 0
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

    immediate = []
    deferred = []

    for prev_id, info in prev_data.items():
        if prev_id in new_ids_set:
            continue

        p = info["position"]
        last_seen_at = info.get("last_seen_at")
        misses = info.get("consecutive_misses", 0) + 1

        cursor.execute(
            "UPDATE listings SET consecutive_misses = ? WHERE id = ? AND monitor_id = ?",
            (misses, prev_id, monitor_id)
        )

        if pivot >= 0 and p is not None and p <= pivot:
            is_confirmed = (misses >= MISS_CONFIRMATION_THRESHOLD)
            if not is_confirmed and last_seen_at:
                try:
                    dt = datetime.strptime(last_seen_at, "%Y-%m-%d %H:%M:%S")
                    hours_absent = (datetime.now() - dt).total_seconds() / 3600.0
                    if hours_absent >= MISS_HOURS_THRESHOLD:
                        is_confirmed = True
                except Exception:
                    pass

            if is_confirmed:
                immediate.append(prev_id)
        else:
            deferred.append(prev_id)

    # Enqueue immediate items (within pivot, confirmed absent)
    if immediate:
        ph = ", ".join(["?"] * len(immediate))
        cursor.execute(f"""
            INSERT INTO verification_queue(id, url, queued_at, last_check)
            SELECT id, url, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM listings
            WHERE id IN ({ph})
            ON CONFLICT(id) DO NOTHING
        """, immediate)

    # Enqueue deferred items (past pivot or unanchored) only if absent for threshold days
    if deferred:
        ph = ", ".join(["?"] * len(deferred))
        cursor.execute(f"""
            INSERT INTO verification_queue(id, url, queued_at, last_check)
            SELECT id, url, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM listings
            WHERE id IN ({ph})
            AND (julianday('now') - julianday(last_seen_at)) >= ?
            ON CONFLICT(id) DO NOTHING
        """, deferred + [QUEUE_ZOMBIE_THRESHOLD_DAYS])

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
        ORDER BY last_check
    '''
    if max_items is not None:
        query += ' LIMIT ?'
        cursor.execute(query, (max_items,))
    else:
        cursor.execute(query)
    rows = cursor.fetchall()
    items = [{"id":row["id"], "url":row["url"]} for row in rows]
    
    if items:
        ids = [item["id"] for item in items]
        placeholders = ', '.join(['?'] * len(ids))
        cursor.execute(f'''
            UPDATE verification_queue
            SET last_check = CURRENT_TIMESTAMP
            WHERE id IN ({placeholders})
        ''', ids)
    
    conn.commit()
    conn.close()
    return items

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

def update_listing_listed_at(item_id: int, listed_at: str):
    if not listed_at:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE listings
        SET listed_at = ?
        WHERE id = ?
    ''', (listed_at, item_id))
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

def delete_from_queue(item_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM verification_queue WHERE id = ?", (item_id,))
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
    cursor.execute("SELECT COUNT(*) AS total, MIN(queued_at) AS oldest_queued FROM verification_queue")
    row = cursor.fetchone()
    conn.close()
    return {"total": row[0], "oldest_queued": row[1]}


def get_verification_queue_items(limit: int | None = None):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    query = """
        SELECT vq.id, vq.url, vq.queued_at, vq.last_check,
               l.title, l.brand, l.price, l.is_active, l.sold_at, l.monitor_id,
               m.name AS monitor_name
        FROM verification_queue vq
        LEFT JOIN listings l ON l.id = vq.id
        LEFT JOIN monitors m ON m.id = l.monitor_id
        ORDER BY vq.last_check ASC
    """
    if limit is not None:
        query += " LIMIT ?"
        cursor.execute(query, (limit,))
    else:
        cursor.execute(query)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows
