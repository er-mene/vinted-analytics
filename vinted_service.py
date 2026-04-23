# vinted_service.py
from curl_cffi import requests
from datetime import datetime
from typing import List
from analytics import save_graph

def search_vinted(query: str, brand_id: int = None, min_price: float = None, max_price: float = None, status_ids: List[int] = None):
    session = requests.Session(impersonate="safari")

    print(f"🕵️  Scraping Vinted for: {query}...")

    # Get Cookies
    try:
        session.get("https://www.vinted.it/")
    except Exception as e:
        print(f"❌ Connection Error (Cookies): {e}")
        return []

    params = {"per_page": 300}
    
    if query: params["search_text"] = query
    if brand_id: params["brand_ids[]"] = brand_id
    if min_price: params["price_from"] = min_price
    if max_price: params["price_to"] = max_price
    if status_ids: params["status_ids[]"] = status_ids

    # Request Data
    try:
        response = session.get("https://www.vinted.it/api/v2/catalog/items", params=params)
    except Exception as e:
        print(f"❌ Connection Error (API): {e}")
        return []

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

    clean_items = []
    
    for item in raw_items:
        try:
            price_info = item.get('total_item_price') or {}
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
                "url": item.get("url"),
                "status_id": item.get("status"),
                "likes": int(item.get("favourite_count", 0)),
                "listed_at": listing_date,
                "has_been_promoted": 1 if item.get("promoted") else 0
            }
            clean_items.append(clean_item)
            
        except Exception as e:
            # Skip invalid items and continue parsing
            print(f"⚠️ skipped item {item.get('id')} due to error: {e}")
            continue
            
    print(f"🏁 Finished parsing. Returning {len(clean_items)} valid items.")
    save_graph(query, clean_items)
    return clean_items