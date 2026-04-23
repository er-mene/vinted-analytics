import sqlite3
import json
import pandas as pd
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
            name TEXT,            -- e.g. "Apple Pencil Monitor"
            query TEXT,
            brand_id INTEGER,
            min_price REAL,
            max_price REAL,
            status_ids TEXT     -- We store list "[6, 1]" as a string
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

def get_monitors_list():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM monitors")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_listings(monitor_id, items):
    """Save scraped listing items into the `listings` table. Returns count of new inserts."""
    if not items: return 0
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    new_count = 0

    items_id = [item['id'] for item in items]
    placeholders = ', '.join(['?'] * len(items_id))

    cursor.execute(f'''
        UPDATE listings
        SET is_active = 0, sold_at = ?
        WHERE monitor_id = ? AND id NOT IN ({placeholders})
    ''', (datetime.now(), monitor_id, *items_id)
    )

    for item in items:
        cursor.execute('''
            INSERT INTO listings 
            (id, monitor_id, title, brand, price, url, status_id, is_active, likes, listed_at, has_been_promoted)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id, monitor_id) DO UPDATE SET
            price = excluded.price,
            likes = excluded.likes,
            is_active = 1,
            sold_at = null,
            has_been_promoted = MAX(listings.has_been_promoted, excluded.has_been_promoted)
        ''', (
            item['id'], monitor_id, item['title'], item['brand'], item['price'], item['url'],
            item.get('status_id'), 1, item.get('likes'),  item.get('listed_at'), item.get('has_been_promoted')
        ))
        if cursor.rowcount > 0: new_count += 1
            
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

def delete_monitor(monitor_id: int):
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''PRAGMA foreign_keys = ON;''')
    cursor = conn.cursor()
    cursor.execute('''DELETE FROM monitors WHERE id = ?''', (monitor_id,))
    conn.commit()
    conn.close()

def get_listings_df(monitor_id):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM listings WHERE monitor_id = ?", conn, params=(monitor_id,))
    conn.close()
    return df