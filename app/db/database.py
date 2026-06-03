import sqlite3
import json
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

DB_NAME = "vinted_data.db"
scheduler = BackgroundScheduler()

def init_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA journal_mode=WAL;")
    scheduler.add_jobstore("sqlalchemy", url=f"sqlite:///{DB_NAME}")
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
            page_delay_seconds REAL DEFAULT 4.0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS verification_queue (
            id INTEGER PRIMARY KEY,
            url TEXT UNIQUE,
            queued_at TIMESTAMP,
            last_check TIMESTAMP
        )
    ''')

    try:
        cursor.execute("ALTER TABLE listings ADD COLUMN scrape_position INTEGER")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE listings ADD COLUMN last_seen_at TIMESTAMP")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE monitors ADD COLUMN last_scrape TIMESTAMP")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


def create_monitor(name, query, brand_id, min_price, max_price, status_ids=[], max_pages=None, page_delay_seconds=4.0):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    status_str = json.dumps(status_ids) if status_ids else "[]"
    
    cursor.execute('''
        INSERT INTO monitors (name, query, brand_id, min_price, max_price, status_ids, max_pages, page_delay_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (name, query, brand_id, min_price, max_price, status_str, max_pages, page_delay_seconds))
    
    monitor_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return monitor_id

def get_monitor(monitor_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row # Allows accessing columns by name
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_monitors_list():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM monitors")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_active_positions_for_monitor(monitor_id: int) -> dict[int, dict]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, scrape_position, price
        FROM listings
        WHERE monitor_id = ? AND is_active = 1
    """, (monitor_id,))
    rows = cursor.fetchall()
    conn.close()
    return {
        row[0]: {"position": row[1], "price": row[2]}
        for row in rows if row[1] is not None
    }


def save_listings(monitor_id: int, items: list) -> int:
    if not items:
        return 0

    prev_data = get_active_positions_for_monitor(monitor_id)

    new_ids_set = {item["id"] for item in items}

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    new_count = 0

    # Find pivot: among items present in both scrapes with same price,
    # the one with the highest old position
    pivot = -1
    for position, item in enumerate(items):
        item_id = item["id"]
        if item_id in prev_data and prev_data[item_id]["price"] == item["price"]:
            old_pos = prev_data[item_id]["position"]
            if old_pos is not None and old_pos > pivot:
                pivot = old_pos

    # Fallback: no unmodified item → use any common item
    if pivot == -1:
        for position, item in enumerate(items):
            item_id = item["id"]
            if item_id in prev_data:
                old_pos = prev_data[item_id]["position"]
                if old_pos is not None and old_pos > pivot:
                    pivot = old_pos

    # Clear queue for items that reappeared (false positives)
    if new_ids_set:
        ph = ", ".join(["?"] * len(new_ids_set))
        cursor.execute(f"DELETE FROM verification_queue WHERE id IN ({ph})", list(new_ids_set))

    # Save listings with their scrape position
    for position, item in enumerate(items):
        cursor.execute("""
            INSERT INTO listings
            (id, monitor_id, title, brand, price, url, status_id, is_active, likes, listed_at, has_been_promoted, scrape_position, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id, monitor_id) DO UPDATE SET
            price = excluded.price,
            likes = excluded.likes,
            is_active = 1,
            sold_at = null,
            has_been_promoted = MAX(listings.has_been_promoted, excluded.has_been_promoted),
            scrape_position = excluded.scrape_position,
            last_seen_at = CURRENT_TIMESTAMP
        """, (
            item["id"], monitor_id, item["title"], item["brand"], item["price"],
            item["url"], item.get("status_id"), 1, item.get("likes"),
            item.get("listed_at"), item.get("has_been_promoted"), position,
        ))
        if cursor.rowcount > 0:
            new_count += 1

    # Add disappeared items (within boundary, not in new scrape) to queue
    if pivot >= 0:
        disappeared = []
        for prev_id, info in prev_data.items():
            if prev_id not in new_ids_set:
                p = info["position"]
                if p is not None and p <= pivot:
                    disappeared.append(prev_id)
        if disappeared:
            ph = ", ".join(["?"] * len(disappeared))
            cursor.execute(f"""
                INSERT INTO verification_queue(id, url, queued_at, last_check)
                SELECT id, url, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                FROM listings
                WHERE id IN ({ph})
                ON CONFLICT(id) DO UPDATE SET
                last_check = CURRENT_TIMESTAMP
            """, disappeared)

    conn.commit()
    conn.close()
    return new_count

QUEUE_EXPIRATION = 7

def clear_queue():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        DELETE FROM listings
        WHERE id IN (
            SELECT id
            FROM verification_queue
            WHERE julianday('now') - julianday(queued_at) >= ?
        )
    ''', (QUEUE_EXPIRATION,))
    cursor.execute('''
        DELETE FROM verification_queue
        WHERE id IN (
            SELECT id
            FROM verification_queue
            WHERE julianday('now') - julianday(queued_at) >= ?
        )
    ''', (QUEUE_EXPIRATION,))
    conn.commit()
    conn.close()

def clear_data(monitors: bool = False, listings: bool = True, daily_stats: bool = True):
    conn = sqlite3.connect(DB_NAME)
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
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''PRAGMA foreign_keys = ON;''')
    cursor = conn.cursor()
    cursor.execute('''DELETE FROM monitors WHERE id = ?''', (monitor_id,))
    conn.commit()
    conn.close()

def get_items_to_verify(max_items: int):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, url
        FROM verification_queue
        ORDER BY last_check
        LIMIT ?
    ''', (max_items,))
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

def mark_item_as_sold(item_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        DELETE FROM verification_queue
        WHERE id = ?
    ''', (item_id,))
    cursor.execute('''
        UPDATE listings
        SET is_active = 0,
            sold_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (item_id,))
    conn.commit()
    conn.close()

def delete_listing(item_id: int):
    conn = sqlite3.connect(DB_NAME)
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
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM verification_queue WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()

def update_monitor_last_scrape(monitor_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE monitors SET last_scrape = CURRENT_TIMESTAMP WHERE id = ?", (monitor_id,))
    conn.commit()
    conn.close()

def get_recent_items(monitor_id: int, limit: int = 10):
    conn = sqlite3.connect(DB_NAME)
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

def get_monitor_analytics(monitor_id: int):
    conn = sqlite3.connect(DB_NAME)
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
    conn = sqlite3.connect(DB_NAME)
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
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS total, MIN(queued_at) AS oldest_queued FROM verification_queue")
    row = cursor.fetchone()
    conn.close()
    return {"total": row[0], "oldest_queued": row[1]}


def get_verification_queue_items(limit: int = 100):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT vq.id, vq.url, vq.queued_at, vq.last_check,
               l.title, l.brand, l.price, l.is_active, l.sold_at, l.monitor_id,
               m.name AS monitor_name
        FROM verification_queue vq
        LEFT JOIN listings l ON l.id = vq.id
        LEFT JOIN monitors m ON m.id = l.monitor_id
        ORDER BY vq.last_check ASC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows
