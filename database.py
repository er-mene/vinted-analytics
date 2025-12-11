import sqlite3
import json
from datetime import datetime, date

DB_NAME = "vinted_data.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. Listings Table (Existing)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY,
            title TEXT,
            brand TEXT,
            price REAL,
            currency TEXT,
            url TEXT,
            status_id INTEGER,
            likes INTEGER,
            is_sold BOOLEAN,
            listed_at TIMESTAMP
        )
    ''')
    
    # 2. Monitors Table (NEW - Saves your "Queries")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS monitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,            -- e.g. "Apple Pencil Monitor"
            query TEXT,
            brand_id INTEGER,
            min_price REAL,
            max_price REAL,
            status_ids TEXT,      -- We store list "[6, 1]" as a string
            last_run TIMESTAMP
        )
    ''')
    
    # 3. Daily Stats Table (NEW - Saves the History)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            monitor_id INTEGER,
            date DATE,
            new_listings_count INTEGER,
            avg_price REAL,
            FOREIGN KEY(monitor_id) REFERENCES monitors(id)
        )
    ''')
    
    conn.commit()
    conn.close()

# --- Saving Monitors ---
def create_monitor(name, query, brand_id, min_price, max_price, status_ids):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Convert list [6, 1] to string "[6, 1]" for SQLite
    status_str = json.dumps(status_ids) if status_ids else "[]"
    
    cursor.execute('''
        INSERT INTO monitors (name, query, brand_id, min_price, max_price, status_ids, last_run)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (name, query, brand_id, min_price, max_price, status_str, None))
    
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

# --- Saving Stats ---
def log_daily_stats(monitor_id, new_count, avg_price):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = date.today()
    
    cursor.execute('''
        INSERT INTO daily_stats (monitor_id, date, new_listings_count, avg_price)
        VALUES (?, ?, ?, ?)
    ''', (monitor_id, today, new_count, avg_price))
    
    conn.commit()
    conn.close()

def get_monitor_history(monitor_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM daily_stats WHERE monitor_id = ? ORDER BY date DESC", (monitor_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# Keep the existing save_listings function!
def save_listings(items):
    # (Paste your existing save_listings function here from the previous step)
    # ...
    if not items: return 0
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    new_count = 0
    
    for item in items:
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO listings 
                (id, title, brand, price, currency, url, status_id, likes, is_sold, listed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item['id'], item['title'], item['brand'], item['price'], item['currency'], 
                item['url'], item.get('status_id'), item.get('likes', 0), 
                item.get('is_sold', False), item.get('listed_at')
            ))
            if cursor.rowcount > 0: new_count += 1
        except Exception as e:
            pass
            
    conn.commit()
    conn.close()
    return new_count