import sqlite3
import json
from datetime import datetime

DB_NAME = "vinted_data.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY,
            title TEXT,
            brand TEXT,
            price REAL,
            url TEXT,
            status_id INTEGER,
            likes INTEGER,
            listed_at TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS monitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,            -- e.g. "Apple Pencil Monitor"
            query TEXT,
            brand_id INTEGER,
            min_price REAL,
            max_price REAL,
            status_ids TEXT     -- We store list "[6, 1]" as a string
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            monitor_id INTEGER,
            date DATETIME,
            total_listings_count INTEGER,
            new_listings_count INTEGER,
            FOREIGN KEY(monitor_id) REFERENCES monitors(id)
        )
    ''')
    
    conn.commit()
    conn.close()


def create_monitor(name, query, brand_id, min_price, max_price, status_ids = []):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Convert list [6, 1] to string "[6, 1]" for SQLite
    status_str = json.dumps(status_ids) if status_ids else "[]"
    
    cursor.execute('''
        INSERT INTO monitors (name, query, brand_id, min_price, max_price, status_ids)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (name, query, brand_id, min_price, max_price, status_str))
    
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

def log_stats(monitor_id, total_count, new_count):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    now = datetime.now()
    
    cursor.execute('''
        INSERT INTO stats (monitor_id, date, total_listings_count, new_listings_count)
        VALUES (?, ?, ?, ?)
    ''', (monitor_id, now, total_count, new_count))

    conn.commit()
    conn.close()

def get_monitor_history(monitor_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM stats WHERE monitor_id = ? ORDER BY date DESC", (monitor_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_monitors_list():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM monitors")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_listings(items):
    """Save scraped listing items into the `listings` table. Returns count of new inserts."""
    if not items: return 0
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    new_count = 0
    
    for item in items:
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO listings 
                (id, title, brand, price, url, status_id, likes, listed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item['id'], item['title'], item['brand'], item['price'], 
                item['url'], item.get('status_id'), item.get('likes', 0),  item.get('listed_at')
            ))
            if cursor.rowcount > 0: new_count += 1
        except Exception as e:
            pass
            
    conn.commit()
    conn.close()
    return new_count

def clear_data(monitors: bool = False, listings: bool = True, daily_stats:bool = True):
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
