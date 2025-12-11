# vinted_service.py
from curl_cffi import requests
from datetime import datetime
import time
import random

def search_vinted(query: str, brand_id: int = None, min_price: float = None, max_price: float = None, status_ids: list = None):
    session = requests.Session(impersonate="chrome")
    
    print(f"🕵️  Scraping Vinted for: {query}...")

    # 1. Get Cookies
    try:
        session.get("https://www.vinted.it/")
    except Exception as e:
        print(f"❌ Connection Error (Cookies): {e}")
        return []

    # 2. Build Params
    params = {
        "search_text": query,
        "currency": "EUR",
        "order": "newest_first",
        "per_page": 500
    }

    if brand_id: params["brand_ids[]"] = brand_id
    if min_price: params["price_from"] = min_price
    if max_price: params["price_to"] = max_price
    if status_ids: params["status_ids[]"] = status_ids

    # 3. Request Data
    try:
        response = session.get("https://www.vinted.it/api/v2/catalog/items", params=params)
    except Exception as e:
        print(f"❌ Connection Error (API): {e}")
        return []

    # 4. Debug: Check if Vinted gave us data
    if response.status_code != 200:
        print(f"❌ BLOCK DETECTED: Status Code {response.status_code}")
        return []

    try:
        data = response.json()
        raw_items = data.get("items", [])
        print(f"✅ Vinted found {len(raw_items)} raw items. Starting parse...")
    except Exception as e:
        print(f"❌ JSON Error: {e}")
        return []

    # 5. Parse (Clean the data)
    clean_items = []
    
    for item in raw_items:
        try:
            # Safe Price Logic
            price_info = item.get('total_item_price') or {}
            
            # Safe Date Logic
            photo = item.get("photo") or {} 
            high_res = photo.get("high_resolution") or {}
            unix_time = high_res.get("timestamp")
            
            listing_date = None
            if unix_time:
                listing_date = datetime.fromtimestamp(unix_time).strftime('%Y-%m-%d %H:%M:%S')

            clean_item = {
                "id": item.get("id"),
                "title": item.get("title"),
                "brand": item.get("brand_title"),
                "price": float(price_info.get("amount", 0)), 
                "currency": price_info.get("currency_code"),
                "url": item.get("url"),
                "status": item.get("status"),
                "listed_at": listing_date,
            }
            clean_items.append(clean_item)
            
        except Exception as e:
            # If a specific item fails, print why, but keep going!
            print(f"⚠️ skipped item {item.get('id')} due to error: {e}")
            continue
            
    print(f"🏁 Finished parsing. Returning {len(clean_items)} valid items.")
    return clean_items